"""Regression coverage for hackathon trend discovery and response semantics."""

import json
import unittest
from concurrent.futures import Future
from datetime import date
from unittest.mock import patch

from resolve_signals import QlooClient
from trending import discover_trending, normalize_records

TODAY = date(2026, 10, 28)
SEED = {"entity_id": "brand-1", "name": "Erewhon", "subtype": "urn:entity:brand"}
PLACE = {"entity_id": "place-1", "name": "Coffee", "subtype": "urn:entity:place"}
WINDOW = {"start_date": "2026-10-01", "end_date": "2026-10-28"}


def response(rows=None, status=200):
    return {
        "http_status": status,
        "payload": {"results": {"trending": rows or []}},
        "error": None,
    }


def row(day="2026-10-27"):
    return {
        "date": day,
        "population_rank": "11991",
        "population_percentile": 0.8784,
        "population_rank_velocity": 0,
        "velocity_fold_change": 0,
        "population_percent_delta": 0,
    }


class Client:
    base_url = "https://hackathon.api.qloo.com"

    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get_detailed(self, path, params):
        self.calls.append((path, dict(params)))
        return next(self.responses)


def artist(eid, score=0.9, links=None):
    return {
        "name": eid,
        "entity_id": eid,
        "subtype": "urn:entity:artist",
        "query": {
            "affinity": score,
            "explainability": {
                "signal.interests.entities": (
                    links
                    if links is not None
                    else [{"entity_id": "brand-1", "score": 1}]
                )
            },
        },
    }


def run(client, seeds=None, artists=None, cache=None, events=None):
    future = Future()
    future.set_result((artists or [], []))
    return discover_trending(
        client,
        {
            "seed_entities": seeds if seeds is not None else [PLACE, SEED],
            "location_query": "New York, NY",
        },
        artists_future=future,
        cache=cache,
        on_event=events.append if events is not None else None,
        today=TODAY,
    )


class TrendingTests(unittest.TestCase):
    def test_unsupported_place_skipped_then_broader_seed_history(self):
        client = Client([response(), response([row()])])
        events = []
        result, notes = run(client, artists=[artist("graph")], events=events)
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["entity"]["source"], "selected_seed")
        self.assertTrue(result["broader_window_used"])
        self.assertEqual(result["recent_record_count"], 1)
        self.assertEqual(client.calls[1][1]["filter.start_date"], "2020-01-01")
        self.assertEqual(result["records"][0]["population_rank"], 11991)
        self.assertEqual(result["records"][0]["velocity_fold_change"], 0)
        self.assertEqual(result["skipped_entities"][0]["entity_id"], "place-1")
        self.assertEqual(len({n["call_id"] for n in notes}), 2)
        self.assertEqual(events[-1]["artifact"], "trending")

    def test_graph_fallback_requires_seed_connection_and_deduplicates(self):
        client = Client([response(), response(), response([row()])])
        result, _ = run(
            client,
            artists=[
                artist("unrelated", 1, []),
                artist("graph", 0.8),
                artist("graph", 0.9),
            ],
        )
        self.assertEqual(result["entity"]["entity_id"], "graph")
        self.assertEqual(result["entity"]["affinity"], 0.9)
        self.assertEqual(result["entity"]["source_seeds"], [SEED])
        self.assertEqual(result["entity"]["discovery_location"], "New York, NY")

    def test_max_four_entities_eight_attempts(self):
        client = Client([response()] * 8)
        seeds = [dict(SEED, entity_id=f"seed{i}") for i in range(5)]
        artists = [
            artist(f"graph{i}", links=[{"entity_id": "seed0", "score": 1}])
            for i in range(5)
        ]
        result, notes = run(client, seeds=seeds, artists=artists)
        self.assertEqual(len(notes), 8)
        self.assertEqual(result["status"], "no_data")

    def test_errors_stop_and_do_not_become_empty(self):
        for status in (400, 401, 403, 404, 429, 500, None):
            with self.subTest(status=status):
                client = Client([response(status=status)])
                result, notes = run(client)
                self.assertEqual(result["status"], "error")
                self.assertEqual(len(notes), 1)
                self.assertEqual(notes[0]["http_status"], status)

    def test_contract_errors_and_no_supported_entities(self):
        result, _ = run(
            Client([{"http_status": 200, "payload": {"results": {}}, "error": None}])
        )
        self.assertEqual(result["reason"], "response_contract_error")
        result, _ = run(Client([]), seeds=[PLACE])
        self.assertEqual(result["status"], "unsupported")

    def test_rejected_entity_does_not_hide_next_valid_seed(self):
        client = Client([response(status=400), response([row()])])
        result, notes = run(client, seeds=[SEED, dict(SEED, entity_id="brand-2")])
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["entity"]["entity_id"], "brand-2")
        self.assertEqual(notes[0]["status"], "error")

    def test_cache_reuses_global_data_but_not_attempt_ids(self):
        cache = {}
        client = Client([response(), response([row()])])
        first, _ = run(client, cache=cache)
        second, notes = run(client, cache=cache)
        self.assertEqual(len(client.calls), 2)
        self.assertTrue(all(n["cached"] for n in notes))
        self.assertNotEqual(first["attempts"][0]["call_id"], notes[0]["call_id"])
        self.assertEqual(first["records"], second["records"])

    def test_historical_only_and_invalid_configuration(self):
        result, _ = run(Client([response(), response([row("2025-01-01")])]))
        self.assertEqual(result["reason"], "historical_only")
        with patch("trending._config_value", return_value="bad-date"):
            result, notes = run(Client([]))
            self.assertEqual(result["status"], "error")
            self.assertEqual(notes, [])

    def test_invalid_dates_missing_values_and_duplicates(self):
        rows, rejected = normalize_records(
            {
                "results": {
                    "trending": [
                        row(),
                        row(),
                        row("bad"),
                        row("2027-01-01"),
                        {"date": "2026-10-26", "population_rank": "4"},
                    ]
                }
            },
            WINDOW,
            WINDOW,
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rejected, 2)
        self.assertIsNone(rows[-1]["velocity_fold_change"])
        with self.assertRaises(ValueError):
            normalize_records({"results": {"trending": [row("bad")]}}, WINDOW, WINDOW)


class DetailedClientTests(unittest.TestCase):
    def test_400_preserves_diagnostics_without_changing_legacy_get(self):
        with QlooClient("secret", base_url=Client.base_url) as client:
            body = json.dumps({"errors": [{"message": "bad secret"}]})
            with patch.object(
                client, "_http_get", return_value=(400, "Bad Request", {}, body)
            ), patch.object(client._limiter, "wait"):
                detailed = client.get_detailed("/v2/trending", {})
                self.assertEqual(detailed["http_status"], 400)
                self.assertNotIn("secret", json.dumps(detailed))
                self.assertIsNotNone(detailed["payload"])
                self.assertIsNone(client.get("/v2/trending", {}))

    def test_retries_share_existing_transport_policy(self):
        with QlooClient("key", base_url=Client.base_url) as client:
            with patch.object(
                client,
                "_http_get",
                side_effect=[
                    (429, "busy", {}, "busy"),
                    (200, "OK", {}, json.dumps({"results": {"trending": []}})),
                ],
            ) as request, patch.object(client._limiter, "wait"), patch.object(
                client, "_sleep_before_retry"
            ) as retry:
                self.assertEqual(
                    client.get_detailed("/v2/trending", {})["http_status"], 200
                )
                self.assertEqual(request.call_count, 2)
                retry.assert_called_once()
