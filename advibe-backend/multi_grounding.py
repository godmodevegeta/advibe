"""Ground each city independently, then assemble campaign-level tribe concepts."""

from __future__ import annotations

import copy
import time
from collections.abc import Callable
from typing import Any

from build_grounding import (
    PACKET_META,
    _public_result,
    build_grounding,
    generate_strategies,
)
from campaign_locations import locations_from


class CityGroundingError(RuntimeError):
    def __init__(self, location_query: str, cause: Exception):
        self.location_query = location_query
        super().__init__(f"{location_query}: {cause}")


_SHARED_ANGLES = {
    "tribe_1": "This tribe converts through familiar cultural crossover signals, with creative localized to each city's venues and tastes. One assigned territory per city and a shared cultural lane distinguish it from the other tribes.",
    "tribe_2": "This tribe converts through high-affinity subcultures and less saturated cultural references in each city. Its own territory and creative direction in every city limit overlap with the core and conquest tribes.",
    "tribe_3": "This tribe converts by reframing the competitor's category around cultural identity and locally grounded reasons to switch. A separate competitor-adjacent territory in each city keeps its audience lane distinct from the other tribes.",
}


def _assemble(cities: list[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
    if scope == "per_location":
        return [
            {
                **strategy,
                "id": f"{city['location_id']}:{strategy['id']}",
                "location_query": city["location_query"],
                "packet": packet,
            }
            for city in cities
            for strategy, packet in zip(city["strategies"], city["_packets"])
        ]
    parents = []
    for index, meta in enumerate(PACKET_META):
        variants = [
            {
                **city["strategies"][index],
                "location_id": city["location_id"],
                "location_query": city["location_query"],
                "packet": city["_packets"][index],
            }
            for city in cities
        ]
        if not variants:
            continue
        parents.append(
            {
                "id": meta["strategy_id"],
                "tribe_name": meta["label"],
                "strategic_angle": _SHARED_ANGLES[meta["strategy_id"]],
                "qloo_grounding_summary": "City-specific Qloo grounding is available for "
                + "; ".join(v["location_query"] for v in variants)
                + ".",
                "location_variants": variants,
            }
        )
    return parents


def build_multi_grounding(
    resolved: dict[str, Any],
    *,
    api_key: str,
    on_event: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    locations = locations_from(resolved)
    if not locations:
        raise ValueError("provide at least one target location")
    scope = (
        "per_location" if resolved.get("tribe_scope") == "per_location" else "overall"
    )
    collected: list[dict[str, Any]] = []
    generated: list[dict[str, Any]] = []
    trending_cache = {}

    def city_emit(location_id: str, query: str):
        def emit(event: dict[str, Any]) -> None:
            # Only the campaign-wide orchestrator may declare completion.
            if event["type"] not in ("checkpoint", "complete"):
                on_event({**event, "location_id": location_id, "location_query": query})

        return emit

    for index, location in enumerate(locations):
        query = location["location_query"]
        location_id = f"city_{index + 1}"
        local = copy.deepcopy(resolved)
        local.update(location)
        local["locations"] = [location]
        raw = local.setdefault("raw_signals", {})
        raw.update({"location": query, **location, "locations": [location]})
        try:
            result = build_grounding(
                local,
                api_key=api_key,
                location_override=query,
                on_event=city_emit(location_id, query),
                generate=False,
                trending_cache=trending_cache,
            )
            result["location_id"] = location_id
            collected.append(result)
        except Exception as exc:
            raise CityGroundingError(query, exc) from exc

    for result in collected:
        query = result["location_query"]

        def emit_generation(event: dict[str, Any]) -> None:
            if event.get("artifact") != "strategies":
                city_emit(result["location_id"], query)(event)

        try:
            strategies, metadata = generate_strategies(
                campaign=result["_campaign"],
                demographics=result["demographics"],
                packets=result["_packets"],
                trending=result["_meta"]["trending"],
                on_event=emit_generation,
            )
            result["strategies"] = strategies
            result["_meta"]["generation"] = metadata
            generated.append(result)
            city_emit(result["location_id"], query)(
                {
                    "type": "artifact_patch",
                    "timestamp": time.time(),
                    "artifact": "strategies",
                    "data": strategies,
                }
            )
            on_event(
                {
                    "type": "artifact_patch",
                    "timestamp": time.time(),
                    "artifact": "strategies",
                    "data": _assemble(generated, scope),
                }
            )
        except Exception as exc:
            raise CityGroundingError(query, exc) from exc

    output = {
        **_public_result(collected[0]),
        "location_query": "; ".join(l["location_query"] for l in locations),
        "locations": locations,
        "tribe_scope": scope,
        "strategies": _assemble(generated, scope),
        "heatmap_pins": [
            {**pin, "location_query": city["location_query"]}
            for city in collected
            for pin in city["heatmap_pins"]
        ],
        "city_outputs": {
            city["location_id"]: _public_result(city) for city in collected
        },
    }
    on_event(
        {
            "type": "checkpoint",
            "timestamp": time.time(),
            "checkpoint_id": "strategy_selection",
            "spinner_verb": f"Select from {len(output['strategies'])} tribes across {len(locations)} cities.",
            "data": output,
        }
    )
    return output
