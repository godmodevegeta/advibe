"""Bounded, evidence-backed trend history discovery on the configured Qloo host."""

from __future__ import annotations

import copy
import math
import time
from datetime import date, timedelta
from typing import Any, Literal, TypedDict
from uuid import uuid4

from resolve_signals import _config_value, _read_dotenv

PATH = "/v2/trending"
SUPPORTED_TYPES = {
    f"urn:entity:{kind}"
    for kind in ("actor", "artist", "brand", "movie", "person", "podcast", "tv_show")
}
METRICS = (
    "population_percentile",
    "population_rank",
    "population_rank_velocity",
    "velocity_fold_change",
    "population_percent_delta",
)


class TrendingResult(TypedDict):
    status: Literal["available", "no_data", "unsupported", "error"]
    reason: str
    scope: str
    entity: dict[str, Any] | None
    recent_window: dict[str, str]
    attempts: list[dict[str, Any]]
    records: list[dict[str, Any]]
    skipped_entities: list[dict[str, Any]]
    returned_date_range: dict[str, str] | None
    recent_record_count: int
    broader_window_used: bool


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def normalize_records(payload: Any, window: dict[str, str], recent: dict[str, str]):
    if not isinstance(payload, dict) or payload.get("success") is False:
        raise ValueError("Invalid trending payload")
    results = payload.get("results")
    rows = results.get("trending") if isinstance(results, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Missing or malformed results.trending")
    by_date = {}
    rejected = 0
    for row in rows:
        try:
            day = date.fromisoformat(row["date"]).isoformat()
        except (ValueError, TypeError, KeyError):
            rejected += 1
            continue
        if not window["start_date"] <= day <= window["end_date"]:
            rejected += 1
            continue
        record = {key: _number(row.get(key)) for key in METRICS}
        rank = record["population_rank"]
        record["population_rank"] = (
            int(rank) if rank is not None and rank.is_integer() and rank >= 1 else None
        )
        if all(v is None for v in record.values()):
            rejected += 1
            continue
        record.update(
            date=day, is_recent=recent["start_date"] <= day <= recent["end_date"]
        )
        by_date.setdefault(day, record)
    if rows and not by_date:
        raise ValueError("No valid in-window trend records")
    return sorted(by_date.values(), key=lambda r: r["date"], reverse=True), rejected


def discover_trending(
    client, campaign, *, artists_future=None, cache=None, on_event=None, today=None
) -> tuple[TrendingResult, list[dict[str, Any]]]:
    """Try two supported seeds, then two explained graph artists, two windows each."""
    today = today or date.today()
    recent = {
        "start_date": (today - timedelta(days=27)).isoformat(),
        "end_date": today.isoformat(),
    }
    result: TrendingResult = {
        "status": "no_data",
        "reason": "no_records",
        "scope": "global",
        "entity": None,
        "recent_window": recent,
        "attempts": [],
        "records": [],
        "skipped_entities": [],
        "returned_date_range": None,
        "recent_record_count": 0,
        "broader_window_used": False,
    }
    notes = result["attempts"]
    cache = cache if cache is not None else {}

    def emit(kind, **kwargs):
        if on_event:
            try:
                on_event({"type": kind, "timestamp": time.time(), **kwargs})
            except Exception:
                pass

    def finish():
        emit("artifact_patch", artifact="trending", data=copy.deepcopy(result))
        return result, notes

    try:
        history_start = date.fromisoformat(
            _config_value(
                "QLOO_TRENDING_HISTORY_START_DATE", _read_dotenv(), "2020-01-01"
            )
        )
        if history_start >= date.fromisoformat(recent["start_date"]):
            raise ValueError("History start must precede the recent window")
    except (TypeError, ValueError):
        result.update(status="error", reason="invalid_history_configuration")
        return finish()
    windows = [
        recent,
        {"start_date": history_start.isoformat(), "end_date": today.isoformat()},
    ]
    seeds = campaign.get("seed_entities") or []
    seed_ids = {s.get("entity_id") for s in seeds}
    competitor_ids = {
        s.get("entity_id") for s in campaign.get("competitor_entities") or []
    }
    supported = []
    seen = set()
    for seed in seeds:
        eid = seed.get("entity_id")
        if not eid or eid in seen or eid in competitor_ids:
            continue
        seen.add(eid)
        if seed.get("subtype") not in SUPPORTED_TYPES:
            result["skipped_entities"].append(
                {**seed, "reason": "unsupported_entity_type"}
            )
            continue
        supported.append({**seed, "source": "selected_seed"})

    def try_entity(entity):
        for index, window in enumerate(windows):
            params = {
                "filter.type": entity["subtype"],
                "signal.interests.entities": entity["entity_id"],
                "filter.start_date": window["start_date"],
                "filter.end_date": window["end_date"],
                "take": 10,
            }
            call_id = str(uuid4())
            attempt = {
                "call_id": call_id,
                "name": "trending",
                "path": PATH,
                "entity": entity,
                "window": dict(window),
                "window_kind": "history" if index else "recent",
                "params": params,
                "scope": "global",
            }
            emit("qloo_call", **attempt, status="running")
            started = time.monotonic()
            key = (client.base_url, PATH, tuple(sorted(params.items())))
            cached = key in cache
            try:
                response = (
                    copy.deepcopy(cache[key])
                    if cached
                    else client.get_detailed(PATH, params)
                )
                if not cached:
                    cache[key] = copy.deepcopy(response)
            except Exception:
                response = {
                    "http_status": None,
                    "payload": None,
                    "error": "Trend transport failed",
                }
            attempt.update(
                http_status=response.get("http_status"),
                error=response.get("error"),
                cached=cached,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            status = response.get("http_status")
            records = []
            if status is None or status in (401, 403, 429) or status >= 500:
                outcome, reason = "error", "service_or_authentication_error"
            elif not 200 <= status < 300:
                outcome, reason = "error", "request_rejected"
            else:
                try:
                    records, rejected = normalize_records(
                        response.get("payload"), window, recent
                    )
                    attempt["rejected_row_count"] = rejected
                    outcome, reason = (
                        ("ok", "history_available")
                        if records
                        else ("empty", "no_records")
                    )
                except ValueError as exc:
                    outcome, reason = "error", "response_contract_error"
                    attempt["error"] = str(exc)
            attempt.update(status=outcome, reason=reason, record_count=len(records))
            notes.append(attempt)
            emit("qloo_call", **attempt)
            if outcome == "error":
                result.update(status="error", reason=reason, entity=entity)
                # Entity-specific rejection must not hide other valid references.
                return reason == "service_or_authentication_error"
            if records:
                count = sum(r["is_recent"] for r in records)
                result.update(
                    status="available",
                    reason="recent_history" if count else "historical_only",
                    entity=entity,
                    records=records,
                    recent_record_count=count,
                    broader_window_used=index > 0,
                    returned_date_range={
                        "start_date": records[-1]["date"],
                        "end_date": records[0]["date"],
                    },
                )
                return True
        return False

    for entity in supported[:2]:
        if try_entity(entity):
            return finish()

    try:
        raw_artists = artists_future.result()[0] if artists_future is not None else []
    except Exception:
        result.update(status="error", reason="graph_discovery_failed")
        return finish()
    candidates = []
    for artist in raw_artists:
        eid = artist.get("entity_id")
        if (
            not eid
            or eid in seen
            or eid in competitor_ids
            or artist.get("subtype") != "urn:entity:artist"
        ):
            continue
        query = artist.get("query") or {}
        if not isinstance(query, dict):
            continue
        affinity = _number(query.get("affinity"))
        explanation = query.get("explainability") or {}
        if not isinstance(explanation, dict):
            continue
        explain = explanation.get("signal.interests.entities") or []
        if not isinstance(explain, list):
            continue
        links = [
            link
            for link in explain
            if isinstance(link, dict)
            and link.get("entity_id") in seed_ids
            and (_number(link.get("score")) or 0) > 0
        ]
        if affinity is None or not 0 <= affinity <= 1 or not links:
            continue
        candidates.append(
            {
                "name": artist.get("name", eid),
                "entity_id": eid,
                "subtype": "urn:entity:artist",
                "source": "related_reference",
                "affinity": affinity,
                "source_seeds": [
                    s
                    for s in seeds
                    if s.get("entity_id") in {l["entity_id"] for l in links}
                ],
                "explainability": links,
                "discovery_location": campaign.get("location_query"),
            }
        )
    candidates.sort(key=lambda a: -a["affinity"])
    selected = []
    for candidate in candidates:
        if candidate["entity_id"] not in seen:
            seen.add(candidate["entity_id"])
            selected.append(candidate)
        if len(selected) == 2:
            break
    for entity in selected:
        if try_entity(entity):
            return finish()
    if not notes:
        result.update(status="unsupported", reason="no_supported_connected_entities")
    return finish()
