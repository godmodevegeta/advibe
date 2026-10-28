import threading
import unittest
from unittest.mock import Mock, patch

import resolve_signals as rs


class JudgeTests(unittest.TestCase):
    def test_judge_resolution_runs_entity_and_tag_tasks_in_parallel(
        self,
    ) -> None:
        barrier = threading.Barrier(2)

        def fake_entities(payload: dict) -> dict:
            barrier.wait(timeout=2)
            return {"entities": {"seed": [], "competitors": []}}

        def fake_tags(payload: dict) -> dict:
            barrier.wait(timeout=2)
            return {"tags": [], "insights_tag_ids": []}

        payload = {
            "padding": "x" * 9000,
            "entities": {
                "seed": [
                    {
                        "query": "Ghia",
                        "candidates": [{"entity_id": "urn:entity:brand:ghia"}],
                    }
                ],
                "competitors": [],
            },
            "tags": [
                {
                    "query": "aperitif",
                    "candidates": [{"tag_id": "urn:tag:cuisine:qloo:aperitif"}],
                }
            ],
        }

        with (
            patch.object(
                rs, "_judge_entities", side_effect=fake_entities
            ),
            patch.object(rs, "_judge_tags", side_effect=fake_tags),
        ):
            result = rs._judge_resolution(payload)

        self.assertEqual(
            result,
            {
                "entities": {"seed": [], "competitors": []},
                "tags": [],
                "insights_tag_ids": [],
            },
        )

    def test_judge_resolution_uses_combined_call_for_small_payload(
        self,
    ) -> None:
        expected = {
            "entities": {"seed": [], "competitors": []},
            "tags": [],
            "insights_tag_ids": [],
        }
        payload = {
            "entities": {
                "seed": [
                    {
                        "query": "Ghia",
                        "candidates": [{"entity_id": "urn:entity:brand:ghia"}],
                    }
                ],
                "competitors": [],
            },
            "tags": [
                {
                    "query": "aperitif",
                    "candidates": [{"tag_id": "urn:tag:cuisine:qloo:aperitif"}],
                }
            ],
        }
        with (
            patch.object(
                rs,
                "_judge_resolution_combined",
                return_value=expected,
            ) as combined,
            patch.object(rs, "_judge_entities") as entities,
            patch.object(rs, "_judge_tags") as tags,
        ):
            result = rs._judge_resolution(payload)

        self.assertEqual(result, expected)
        combined.assert_called_once()
        entities.assert_not_called()
        tags.assert_not_called()

    def test_judge_resolution_skips_llm_without_candidates(self) -> None:
        payload = {
            "entities": {
                "seed": [{"query": "Ghia", "candidates": []}],
                "competitors": [{"query": "Aperol", "candidates": []}],
            },
            "tags": [{"query": "aperitif", "candidates": []}],
        }
        with (
            patch.object(rs, "complete_json") as complete,
            patch.object(rs, "_judge_entities") as entities,
            patch.object(rs, "_judge_tags") as tags,
            patch.object(rs, "_judge_resolution_combined") as combined,
        ):
            result = rs._judge_resolution(payload)

        self.assertEqual(
            result,
            {
                "entities": {"seed": [], "competitors": []},
                "tags": [],
                "insights_tag_ids": [],
            },
        )
        complete.assert_not_called()
        entities.assert_not_called()
        tags.assert_not_called()
        combined.assert_not_called()

    def test_judge_resolution_retry_round_only_judges_tags(self) -> None:
        payload = {
            "entities": {
                "seed": [{"query": "Ghia", "candidates": []}],
                "competitors": [],
            },
            "tags": [
                {
                    "query": "aperitif",
                    "candidates": [{"tag_id": "urn:tag:cuisine:qloo:aperitif"}],
                }
            ],
            "retry_round": True,
        }
        with (
            patch.object(rs, "_judge_entities") as entities,
            patch.object(
                rs,
                "_judge_tags",
                return_value={"tags": [], "insights_tag_ids": []},
            ) as tags,
            patch.object(rs, "_judge_resolution_combined") as combined,
        ):
            result = rs._judge_resolution(payload)

        self.assertEqual(
            result,
            {
                "entities": {"seed": [], "competitors": []},
                "tags": [],
                "insights_tag_ids": [],
            },
        )
        entities.assert_not_called()
        tags.assert_called_once_with(payload)
        combined.assert_not_called()

    def test_judge_resolution_entities_only_skips_tag_pass(self) -> None:
        payload = {
            "entities": {
                "seed": [
                    {
                        "query": "Ghia",
                        "candidates": [{"entity_id": "urn:entity:brand:ghia"}],
                    }
                ],
                "competitors": [],
            },
            "tags": [],
        }
        expected_entities = {
            "seed": [{"query": "Ghia", "selected_entity_id": None}],
            "competitors": [],
        }
        with (
            patch.object(
                rs,
                "_judge_entities",
                return_value={"entities": expected_entities},
            ) as entities,
            patch.object(rs, "_judge_tags") as tags,
            patch.object(rs, "_judge_resolution_combined") as combined,
        ):
            result = rs._judge_resolution(payload)

        self.assertEqual(
            result,
            {
                "entities": expected_entities,
                "tags": [],
                "insights_tag_ids": [],
            },
        )
        entities.assert_called_once_with(payload)
        tags.assert_not_called()
        combined.assert_not_called()

    def test_judge_entities_defaults_missing_entity_schema(self) -> None:
        with patch.object(rs, "complete_json", return_value={}):
            result = rs._judge_entities({})

        self.assertEqual(
            result, {"entities": {"seed": [], "competitors": []}}
        )

    def test_judge_entities_coerces_top_level_lists(self) -> None:
        seed = [
            {
                "query": "Ghia",
                "selected_entity_id": "urn:entity:brand:ghia",
                "retry_query": None,
            }
        ]
        with patch.object(
            rs,
            "complete_json",
            return_value={"seed": seed, "competitors": []},
        ):
            result = rs._judge_entities({})

        self.assertEqual(
            result, {"entities": {"seed": seed, "competitors": []}}
        )

    def test_judge_entities_coerces_entity_list(self) -> None:
        seed = [{"query": "Ghia", "selected_entity_id": None}]
        with patch.object(
            rs, "complete_json", return_value={"entities": seed}
        ):
            result = rs._judge_entities({})

        self.assertEqual(
            result, {"entities": {"seed": seed, "competitors": []}}
        )

    def test_judge_entities_filters_malformed_decisions(self) -> None:
        with patch.object(
            rs,
            "complete_json",
            return_value={
                "entities": {
                    "seed": [
                        {"query": "Ghia", "selected_entity_id": None},
                        "not a decision",
                        {"query": "   "},
                    ],
                    "competitors": "not a list",
                }
            },
        ):
            result = rs._judge_entities({})

        self.assertEqual(
            result,
            {
                "entities": {
                    "seed": [
                        {"query": "Ghia", "selected_entity_id": None}
                    ],
                    "competitors": [],
                }
            },
        )

    def test_judge_tags_defaults_missing_insights(self) -> None:
        with patch.object(
            rs, "complete_json", return_value={"tags": []}
        ):
            result = rs._judge_tags({})

        self.assertEqual(result, {"tags": [], "insights_tag_ids": []})

    def test_judge_tags_filters_malformed_decisions(self) -> None:
        with patch.object(
            rs,
            "complete_json",
            return_value={
                "tags": [
                    {"query": "aperitif", "selected_tag_id": None},
                    "not a decision",
                ],
                "insights_tag_ids": "not a list",
            },
        ):
            result = rs._judge_tags({})

        self.assertEqual(
            result,
            {
                "tags": [{"query": "aperitif", "selected_tag_id": None}],
                "insights_tag_ids": [],
            },
        )

    def test_combined_judge_coerces_missing_entities(self) -> None:
        with patch.object(
            rs,
            "complete_json",
            return_value={"tags": [], "insights_tag_ids": []},
        ):
            result = rs._judge_resolution_combined({})

        self.assertEqual(
            result,
            {
                "entities": {"seed": [], "competitors": []},
                "tags": [],
                "insights_tag_ids": [],
            },
        )


class LifecycleTests(unittest.TestCase):
    def test_resolve_signals_closes_client_when_processing_fails(
        self,
    ) -> None:
        client = Mock()
        with (
            patch.object(rs, "_QlooClient", return_value=client),
            patch.object(
                rs,
                "_build_initial_groups",
                side_effect=RuntimeError("boom"),
            ),
            self.assertRaises(RuntimeError),
        ):
            rs.resolve_signals(
                {
                    "seed_brands": ["Ghia"],
                    "competitor_brands": ["Aperol"],
                    "seed_tags": ["aperitif"],
                },
                api_key="key",
            )

        client.close.assert_called_once()


class TransportTests(unittest.TestCase):
    def test_scheduled_rate_limiter_spaces_request_slots(self) -> None:
        now = [100.0]
        sleeps: list[float] = []
        limiter = rs._ScheduledRateLimiter(
            0.22,
            clock=lambda: now[0],
            sleeper=sleeps.append,
        )

        limiter.wait()
        limiter.wait()
        limiter.wait()

        self.assertEqual(len(sleeps), 2)
        self.assertAlmostEqual(sleeps[0], 0.22)
        self.assertAlmostEqual(sleeps[1], 0.44)

    def test_connection_pool_reuses_and_discards_connections(self) -> None:
        first = Mock()
        second = Mock()
        factory = Mock(side_effect=[first, second])
        pool = rs._HttpConnectionPool(factory, max_connections=1)

        acquired = pool.acquire()
        self.assertIs(acquired, first)
        pool.release(acquired)
        reused = pool.acquire()
        self.assertIs(reused, first)
        pool.discard(reused)
        first.close.assert_called_once()

        replacement = pool.acquire()
        self.assertIs(replacement, second)
        pool.release(replacement)
        pool.close()
        second.close.assert_called_once()
        with self.assertRaises(RuntimeError):
            pool.acquire()

    def test_request_retries_rate_limit_with_retry_after(self) -> None:
        client = rs._QlooClient(
            "key", base_url="https://example.com"
        )
        responses = [
            (429, "Too Many Requests", {"retry-after": "2"}, "busy"),
            (200, "OK", {}, '{"ok": true}'),
        ]
        with (
            patch.object(client._limiter, "wait"),
            patch.object(
                client, "_http_get", side_effect=responses
            ),
            patch.object(rs.time, "sleep") as sleep,
        ):
            payload = client._request("/x", {})
            client.close()

        self.assertEqual(payload, {"ok": True})
        sleep.assert_called_once_with(2.0)

    def test_request_returns_none_for_not_found(self) -> None:
        client = rs._QlooClient(
            "key", base_url="https://example.com"
        )
        with (
            patch.object(client._limiter, "wait"),
            patch.object(
                client,
                "_http_get",
                return_value=(404, "Not Found", {}, "missing"),
            ),
        ):
            payload = client._request("/x", {})
            client.close()

        self.assertIsNone(payload)


class PlaceOnlyClient:
    def search_entities(self, name, *, types=None, take=5):
        if types == "urn:entity:brand":
            return []
        return [
            {
                "name": name,
                "entity_id": "place-1",
                "subtype": "urn:entity:place",
            }
        ]


class MixedCompetitorClient:
    def search_entities(self, name, *, types=None, take=5):
        if types == "urn:entity:brand":
            return []
        return [
            {
                "name": name,
                "entity_id": "brand-1",
                "subtype": "urn:entity:brand",
            },
            {
                "name": name,
                "entity_id": "place-1",
                "subtype": "urn:entity:place",
            },
        ]


class SeedBrandClient:
    def search_entities(self, name, *, types=None, take=5):
        if types == "urn:entity:brand":
            return [
                {
                    "name": name,
                    "entity_id": "brand-1",
                    "subtype": "urn:entity:brand",
                    "popularity": 0.5,
                },
                {
                    "name": "Unrelated Brand",
                    "entity_id": "brand-unrelated",
                    "subtype": "urn:entity:brand",
                    "popularity": 0.99,
                },
            ]
        return [
            {
                "name": name,
                "entity_id": "place-1",
                "subtype": "urn:entity:place",
                "popularity": 0.9,
            }
        ]


class SuffixBrandClient:
    def search_entities(self, name, *, types=None, take=5):
        if types == "urn:entity:brand":
            return [
                {
                    "name": "ST-GERMAIN® Liqueur",
                    "entity_id": "stgermain-brand",
                    "subtype": "urn:entity:brand",
                    "popularity": 0.7,
                }
            ]
        return [
            {
                "name": "St. Germain",
                "entity_id": "stgermain-artist",
                "subtype": "urn:entity:artist",
                "popularity": 0.9,
            }
        ]


class JungsikClient:
    def search_entities(self, name, *, types=None, take=5):
        if name == "Jungsik":
            return [
                {
                    "name": "Jungsik",
                    "entity_id": "jungsik-place",
                    "subtype": "urn:entity:place",
                }
            ]
        return []


class StaticTrioClient:
    def __init__(self):
        self.results = {
            ("Dom Pérignon", "urn:entity:brand"): [
                {
                    "name": "Dom Pérignon",
                    "entity_id": "dom-brand",
                    "subtype": "urn:entity:brand",
                }
            ],
            ("Aesop", "urn:entity:brand"): [
                {
                    "name": "Aesop",
                    "entity_id": "aesop-brand",
                    "subtype": "urn:entity:brand",
                }
            ],
            ("Ryuichi Sakamoto", "urn:entity:artist"): [
                {
                    "name": "Ryuichi Sakamoto",
                    "entity_id": "ryuichi-artist",
                    "subtype": "urn:entity:artist",
                }
            ],
        }

    def search_entities(self, name, *, types=None, take=5):
        if types is None:
            return []
        return self.results.get((name, types), [])


class CompetitorResolutionTests(unittest.TestCase):
    def test_place_only_competitor_is_rejected(self) -> None:
        candidates, mode = rs._fetch_entity_candidates(
            PlaceOnlyClient(), "Hakkaisan", competitor=True
        )

        self.assertEqual(candidates, [])
        self.assertEqual(mode, "untyped")

    def test_untyped_brand_competitor_is_kept(self) -> None:
        candidates, mode = rs._fetch_entity_candidates(
            MixedCompetitorClient(), "Chamisul", competitor=True
        )

        self.assertEqual(mode, "untyped")
        self.assertEqual(
            [candidate["subtype"] for candidate in candidates],
            ["urn:entity:brand"],
        )

    def test_seed_search_prefers_exact_brand_candidate(self) -> None:
        candidates, mode = rs._fetch_entity_candidates(
            SeedBrandClient(), "Blue Bottle Coffee", competitor=False
        )

        self.assertEqual(mode, "untyped+brand")
        self.assertEqual(
            [candidate["entity_id"] for candidate in candidates],
            ["brand-1", "place-1"],
        )

    def test_seed_search_matches_brand_with_suffix(self) -> None:
        candidates, mode = rs._fetch_entity_candidates(
            SuffixBrandClient(), "St. Germain", competitor=False
        )

        self.assertEqual(mode, "untyped+brand")
        self.assertEqual(
            [candidate["entity_id"] for candidate in candidates],
            ["stgermain-brand", "stgermain-artist"],
        )

    def test_candidate_name_matching_rejects_wrong_brand(self) -> None:
        self.assertTrue(
            rs._candidate_matches_query(
                "ST-GERMAIN® Liqueur", "St. Germain"
            )
        )
        self.assertFalse(
            rs._candidate_matches_query(
                "Toronto Blue Jays", "Blue Bottle Coffee"
            )
        )
        self.assertFalse(
            rs._candidate_matches_query("Aime", "Aimé Leon Dore")
        )


class EntityBackfillTests(unittest.TestCase):
    def test_backfill_prefers_exact_brand_over_popular_place(self) -> None:
        groups = [
            {
                "query": "Blue Bottle Coffee",
                "candidates": [
                    {
                        "name": "Blue Bottle Coffee",
                        "entity_id": "place-1",
                        "subtype": "urn:entity:place",
                        "popularity": 0.99,
                    },
                    {
                        "name": "Blue Bottle Coffee",
                        "entity_id": "brand-1",
                        "subtype": "urn:entity:brand",
                        "popularity": 0.5,
                    },
                ],
            }
        ]
        selections = []

        rs._backfill_entity_selections(groups, selections)

        self.assertEqual(selections[0]["candidate"]["entity_id"], "brand-1")

    def test_backfill_prefers_suffix_brand_over_same_name_artist(self) -> None:
        groups = [
            {
                "query": "St. Germain",
                "candidates": [
                    {
                        "name": "St. Germain",
                        "entity_id": "artist-1",
                        "subtype": "urn:entity:artist",
                        "popularity": 0.99,
                    },
                    {
                        "name": "ST-GERMAIN® Liqueur",
                        "entity_id": "brand-1",
                        "subtype": "urn:entity:brand",
                        "popularity": 0.7,
                    },
                ],
            }
        ]
        selections = []

        rs._backfill_entity_selections(groups, selections)

        self.assertEqual(selections[0]["candidate"]["entity_id"], "brand-1")

    def test_backfill_does_not_override_judge_selection(self) -> None:
        existing = {
            "query": "A24",
            "candidate": {
                "name": "A24",
                "entity_id": "judge-brand",
                "subtype": "urn:entity:brand",
            },
        }
        groups = [
            {
                "query": "A24",
                "candidates": [
                    {
                        "name": "A24",
                        "entity_id": "other-brand",
                        "subtype": "urn:entity:brand",
                    }
                ],
            }
        ]
        selections = [existing]

        rs._backfill_entity_selections(groups, selections)

        self.assertEqual(selections, [existing])

    def test_backfill_respects_excluded_entity_ids(self) -> None:
        groups = [
            {
                "query": "Momofuku",
                "candidates": [
                    {
                        "name": "Momofuku",
                        "entity_id": "shared-id",
                        "subtype": "urn:entity:place",
                    }
                ],
            }
        ]
        selections = []

        rs._backfill_entity_selections(
            groups, selections, excluded_ids={"shared-id"}
        )

        self.assertEqual(selections, [])

    def test_competitor_backfill_requires_brand(self) -> None:
        groups = [
            {
                "query": "Hakkaisan",
                "candidates": [
                    {
                        "name": "Hakkaisan",
                        "entity_id": "place-1",
                        "subtype": "urn:entity:place",
                    }
                ],
            }
        ]
        selections = []

        rs._backfill_entity_selections(
            groups, selections, brand_only=True
        )

        self.assertEqual(selections, [])


class RescueTests(unittest.TestCase):
    def test_static_trio_selection(self) -> None:
        self.assertEqual(
            rs._select_static_rescue_trio(
                {"raw_input": "high luxury makgeolli"}, {}
            ),
            rs._STATIC_RESCUE_TRIOS["luxury"],
        )
        self.assertEqual(
            rs._select_static_rescue_trio(
                {"raw_input": "streetwear capsule drop"}, {}
            ),
            rs._STATIC_RESCUE_TRIOS["streetwear_culture"],
        )
        self.assertEqual(
            rs._select_static_rescue_trio(
                {"raw_input": "wellness cafe with matcha"}, {}
            ),
            rs._STATIC_RESCUE_TRIOS["wellness_cafe"],
        )
        self.assertEqual(
            rs._select_static_rescue_trio(
                {"raw_input": "a new fintech app"}, {}
            ),
            rs._STATIC_RESCUE_TRIOS["default"],
        )

    def test_self_brand_rescue_resolves_place(self) -> None:
        campaign = {
            "raw_input": "i own Jungsik in NYC, high luxury makgeolli",
            "brand_name": "Jungsik",
            "product_description": "makgeolli",
            "location": "New York, NY",
            "location_query": "New York, NY",
        }
        raw_signals = {
            "seed_brands": [],
            "competitor_brands": ["Chamisul"],
            "seed_tags": ["makgeolli", "luxury"],
        }

        with patch(
            "resolve_signals.complete_json",
            side_effect=AssertionError("LLM should not be called"),
        ):
            groups, selections = rs._rescue_seed_entities(
                JungsikClient(),
                campaign,
                raw_signals,
                existing_entity_ids=set(),
            )

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["query"], "Jungsik")
        self.assertEqual(len(selections), 1)
        self.assertEqual(
            selections[0]["candidate"]["subtype"], "urn:entity:place"
        )

    def test_static_rescue_fills_three_seeds(self) -> None:
        campaign = {
            "raw_input": "i own Jungsik in NYC, high luxury makgeolli",
            "brand_name": "Jungsik",
            "product_description": "makgeolli",
            "location": "New York, NY",
            "location_query": "New York, NY",
        }
        raw_signals = {
            "seed_brands": [],
            "competitor_brands": ["Chamisul"],
            "seed_tags": ["makgeolli", "luxury"],
        }

        with patch(
            "resolve_signals.complete_json",
            side_effect=rs.SeedExtractionError("forced rescue failure"),
        ):
            _groups, selections = rs._rescue_seed_entities(
                StaticTrioClient(),
                campaign,
                raw_signals,
                existing_entity_ids=set(),
            )

        self.assertEqual(len(selections), 3)
        self.assertEqual(
            {selection["query"] for selection in selections},
            {"Dom Pérignon", "Aesop", "Ryuichi Sakamoto"},
        )

    def test_rescue_rejects_excluded_competitor_name(self) -> None:
        candidate = rs._search_rescue_candidate(
            StaticTrioClient(),
            "Dom Pérignon",
            "urn:entity:brand",
            existing_ids=set(),
            excluded_names={"dom pérignon"},
        )

        self.assertIsNone(candidate)


class EventHookTests(unittest.TestCase):
    def test_emit_payload_and_timestamp(self) -> None:
        events: list[dict] = []
        rs._emit(
            events.append,
            "phase_change",
            phase="candidate_search",
        )
        self.assertEqual(events[0]["type"], "phase_change")
        self.assertEqual(events[0]["phase"], "candidate_search")
        self.assertIsInstance(events[0]["timestamp"], float)

    def test_emit_swallows_callback_errors(self) -> None:
        def broken_callback(event: dict) -> None:
            raise RuntimeError("callback boom")

        rs._emit(broken_callback, "phase_change", phase="candidate_search")

    def test_resolve_signals_emits_phase_and_artifact_events(self) -> None:
        client = Mock()
        events: list[dict] = []
        group = {
            "query": "Ghia",
            "candidates": [{"entity_id": "urn:entity:brand:ghia"}],
        }
        retry_group = {
            "query": "Ghia",
            "candidates": [{"entity_id": "urn:entity:brand:ghia"}],
        }
        first_judgment = {
            "entities": {"seed": [], "competitors": []},
            "tags": [],
            "insights_tag_ids": [],
        }
        retry_judgment = {
            "entities": {"seed": [], "competitors": []},
            "tags": [],
            "insights_tag_ids": [],
        }

        with (
            patch.object(rs, "_QlooClient", return_value=client),
            patch.object(
                rs,
                "_build_initial_groups",
                return_value=([group], [], []),
            ),
            patch.object(
                rs,
                "_judge_resolution",
                side_effect=[first_judgment, retry_judgment],
            ),
            patch.object(
                rs,
                "_apply_entity_judgments",
                side_effect=[
                    ([], ["retry"]),
                    ([], []),
                    ([], []),
                    ([], []),
                ],
            ),
            patch.object(
                rs,
                "_apply_tag_judgments",
                side_effect=[([], ["retry"]), ([], [])],
            ),
            patch.object(rs, "_build_resolved_tags", return_value=[]),
            patch.object(
                rs,
                "_build_retry_groups",
                return_value=([retry_group], [], []),
            ),
            patch.object(rs, "_build_resolved_entities", return_value=[]),
            patch.object(
                rs, "_rescue_seed_entities", return_value=([], [])
            ),
            patch.object(rs, "_validate_insights", return_value=[]),
            patch.object(
                rs,
                "_ensure_insights_in_resolved_tags",
                return_value=[],
            ),
        ):
            result = rs.resolve_signals(
                {
                    "brand_name": "Ghia",
                    "seed_brands": ["Ghia"],
                    "seed_tags": [],
                    "location_query": "Austin, TX",
                },
                api_key="key",
                on_event=events.append,
            )

        self.assertEqual(result["location_query"], "Austin, TX")
        phases = [
            event["phase"]
            for event in events
            if event["type"] == "phase_change"
        ]
        self.assertEqual(
            phases,
            ["candidate_search", "llm_judge", "llm_judge_retry"],
        )
        self.assertEqual(events[-1]["type"], "artifact_patch")
        self.assertEqual(events[-1]["artifact"], "resolved_signals")
        self.assertIs(events[-1]["data"], result)
        client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
