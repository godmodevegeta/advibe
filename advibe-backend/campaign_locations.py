"""Canonical campaign locations and backwards-compatible location state."""

from __future__ import annotations

from typing import Any

from resolve_signals import _derive_neighborhood_hints, _normalize_location_query

_ALIASES = {
    "sf": "San Francisco, CA",
    "san francisco": "San Francisco, CA",
    "san francisco, ca": "San Francisco, CA",
    "london": "London, UK",
    "london, uk": "London, UK",
    "nyc": "New York, NY",
    "new york": "New York, NY",
    "new york, ny": "New York, NY",
}


def normalize_locations(values: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values if isinstance(values, list) else []:
        raw = value.get("location_query") if isinstance(value, dict) else value
        if not isinstance(raw, str) or not raw.strip():
            continue
        query = (
            _ALIASES.get(raw.strip().casefold())
            or _normalize_location_query(raw)
            or raw.strip()
        )
        key = query.casefold()
        if key in seen:
            continue
        seen.add(key)
        hints = value.get("neighborhood_hints") if isinstance(value, dict) else None
        hints = (
            [h.strip() for h in hints if isinstance(h, str) and h.strip()]
            if isinstance(hints, list)
            else []
        )
        output.append(
            {
                "location_query": query,
                "neighborhood_hints": hints or _derive_neighborhood_hints(query),
            }
        )
    return output


def locations_from(value: dict[str, Any]) -> list[dict[str, Any]]:
    if "locations" in value:
        return normalize_locations(value["locations"])
    query = value.get("location_query") or value.get("location")
    return normalize_locations(
        [
            {
                "location_query": query,
                "neighborhood_hints": value.get("neighborhood_hints"),
            }
        ]
    )


def sync_location_fields(state: dict[str, Any]) -> None:
    first = state["locations"][0] if state["locations"] else {}
    state["location"] = state["location_query"] = first.get("location_query")
    state["neighborhood_hints"] = list(first.get("neighborhood_hints") or [])


def apply_location_turn(
    state: dict[str, Any], scoped: dict[str, Any], selected: str | None
) -> None:
    operation = scoped.get("location_operation")
    incoming = normalize_locations(scoped.get("locations"))
    # Old extraction responses expressed a city change with a scalar field.
    if not incoming and operation is None and scoped.get("location_query"):
        incoming = normalize_locations(
            [
                {
                    "location_query": scoped["location_query"],
                    "neighborhood_hints": scoped.get("neighborhood_hints"),
                }
            ]
        )
        operation = "replace"
    if selected:
        incoming = normalize_locations([*incoming, selected])
        operation = "add"
    if operation == "remove":
        removed = {v["location_query"].casefold() for v in incoming}
        state["locations"] = [
            v
            for v in state["locations"]
            if v["location_query"].casefold() not in removed
        ]
    elif operation == "replace":
        state["locations"] = incoming
    elif incoming:
        state["locations"] = normalize_locations([*state["locations"], *incoming])
    scope = scoped.get("tribe_scope")
    if scope in ("overall", "per_location"):
        state["tribe_scope"] = scope
        state["tribe_scope_explicit"] = True
    sync_location_fields(state)
