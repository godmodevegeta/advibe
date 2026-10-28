"""Offline tests for the SSE stream harness."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

try:
    import stream_harness as sh
except ModuleNotFoundError as exc:
    if exc.name not in {"fastapi", "pydantic"}:
        raise
    sh = None

_REQUIRES_DEPS = unittest.skipIf(
    sh is None,
    "stream harness dependencies are not installed",
)


@_REQUIRES_DEPS
class StreamGeneratorTests(unittest.TestCase):
    def _result(self) -> dict:
        return {
            "brand_name": "Humo Santo",
            "location_query": "Austin, TX",
            "demographics": {"aggregate": {}},
            "taste_vocabulary": [],
            "heatmap_pins": [],
            "strategies": [
                {"id": "tribe_1", "tribe_name": "Eastside Crate"},
                {"id": "tribe_2", "tribe_name": "Warehouse Archive"},
                {"id": "tribe_3", "tribe_name": "Downtown Switchers"},
            ],
        }

    def _events(self, frames: list[str]) -> list[dict]:
        events = []
        for frame in frames:
            self.assertTrue(frame.startswith("data: "))
            self.assertTrue(frame.endswith("\n\n"))
            events.append(json.loads(frame[len("data: ") :].strip()))
        return events

    def test_stream_emits_sse_events_and_complete(self) -> None:
        extracted = {
            "brand_name": "Humo Santo",
            "seed_brands": ["Casamigos"],
            "location": "Austin, Texas",
            "location_query": "Austin, TX",
        }
        seen: dict[str, dict] = {}

        def fake_extract(prompt: str) -> dict:
            seen["prompt"] = prompt
            return dict(extracted)

        def fake_resolve(extracted_input, api_key, *, on_event=None):
            seen["resolved_input"] = extracted_input
            if on_event:
                on_event(
                    {
                        "type": "phase_change",
                        "timestamp": 1.0,
                        "phase": "candidate_search",
                        "spinner_verb": "searching",
                    }
                )
                on_event(
                    {
                        "type": "artifact_patch",
                        "timestamp": 1.1,
                        "artifact": "resolved_signals",
                        "data": {"brand_name": "Humo Santo"},
                    }
                )
            return {"brand_name": "Humo Santo", "resolved_entities": {}}

        def fake_build(resolved, *, api_key, location_override=None, on_event=None):
            seen["location_override"] = location_override
            if on_event:
                on_event(
                    {
                        "type": "checkpoint",
                        "timestamp": 2.0,
                        "checkpoint_id": "strategy_selection",
                        "spinner_verb": "awaiting",
                        "data": self._result(),
                    }
                )
            return self._result()

        with (
            patch.object(sh, "extract_seed_signals", side_effect=fake_extract),
            patch.object(sh, "load_qloo_api_key", return_value="test-key"),
            patch.object(sh, "resolve_signals", side_effect=fake_resolve),
            patch.object(sh, "build_grounding", side_effect=fake_build),
        ):
            frames = list(
                sh.stream_campaign_grounding(
                    "  Build Austin for Humo Santo  ",
                    "Austin, TX",
                )
            )

        events = self._events(frames)
        types = [event["type"] for event in events]
        self.assertEqual(types[0], "phase_change")
        self.assertEqual(events[0]["phase"], "brief_extraction")
        self.assertEqual(types[1], "artifact_patch")
        self.assertEqual(events[1]["artifact"], "seed_signals")
        self.assertEqual(types[-1], "complete")
        self.assertEqual(events[-1]["data"]["brand_name"], "Humo Santo")
        self.assertIn("candidate_search", [e.get("phase") for e in events])
        self.assertIn("resolved_signals", [e.get("artifact") for e in events])
        self.assertEqual(seen["prompt"], "Build Austin for Humo Santo")
        self.assertEqual(
            seen["resolved_input"]["location_query"], "Austin, TX"
        )
        self.assertEqual(seen["location_override"], "Austin, TX")

    def test_stream_emits_error_event(self) -> None:
        with (
            patch.object(
                sh,
                "extract_seed_signals",
                side_effect=ValueError("bad brief"),
            ),
            patch.object(sh, "load_qloo_api_key", return_value="test-key"),
        ):
            frames = list(sh.stream_campaign_grounding("bad brief"))

        events = self._events(frames)
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(events[-1]["error_type"], "ValueError")
        self.assertIn("bad brief", events[-1]["message"])

    def test_empty_prompt_yields_error_without_worker(self) -> None:
        frames = list(sh.stream_campaign_grounding("   "))
        events = self._events(frames)
        self.assertEqual(events[0]["type"], "error")
        self.assertEqual(events[0]["error_type"], "ValueError")

    def test_locked_stream_skips_extraction_and_resolution(self) -> None:
        resolved = {
            "brand_name": "Chaen",
            "location_query": "New York, NY",
            "resolved_entities": {
                "seed": [
                    {
                        "name": "Erewhon",
                        "entity_id": "urn:entity:brand:erewhon",
                        "subtype": "urn:entity:brand",
                        "affinity_hint": None,
                    },
                    {
                        "name": "Clairo",
                        "entity_id": "urn:entity:artist:clairo",
                        "subtype": "urn:entity:artist",
                        "affinity_hint": None,
                    },
                ],
                "competitors": [
                    {
                        "name": "Red Bull",
                        "entity_id": "urn:entity:brand:red_bull",
                        "subtype": "urn:entity:brand",
                        "affinity_hint": None,
                    }
                ],
            },
            "resolved_tags": [],
            "insights_tags": [],
            "neighborhood_hints": [],
            "raw_signals": {},
        }
        seen: dict[str, object] = {}

        def fake_build(input_resolved, *, api_key, location_override=None, on_event=None):
            seen["resolved"] = input_resolved
            seen["location_override"] = location_override
            return self._result()

        with (
            patch.object(
                sh,
                "extract_seed_signals",
                side_effect=AssertionError("locked signals must not extract"),
            ),
            patch.object(
                sh,
                "resolve_signals",
                side_effect=AssertionError("locked signals must not resolve"),
            ),
            patch.object(sh, "load_qloo_api_key", return_value="test-key"),
            patch.object(sh, "build_grounding", side_effect=fake_build),
        ):
            frames = list(
                sh.stream_resolved_grounding(resolved, "New York, NY")
            )

        events = self._events(frames)
        self.assertEqual(events[0]["type"], "artifact_patch")
        self.assertEqual(events[0]["artifact"], "resolved_signals")
        self.assertEqual(events[-1]["type"], "complete")
        self.assertIs(seen["resolved"], resolved)
        self.assertEqual(seen["location_override"], "New York, NY")


@_REQUIRES_DEPS
class PresentationTests(unittest.TestCase):
    def test_artifact_summaries_handle_lists(self) -> None:
        self.assertIn(
            "packets=2",
            sh._artifact_summary("packets", [{"id": 1}, {"id": 2}]),
        )
        summary = sh._artifact_summary(
            "strategies",
            [{"tribe_name": "Eastside Crate"}],
        )
        self.assertIn("strategies=1", summary)
        self.assertIn("Eastside Crate", summary)

    def test_presets_include_five_launchpad_prompts(self) -> None:
        self.assertEqual([p["title"] for p in sh.PRESETS], ["Chaen Matcha Energy", "Humo Santo Mezcal", "Nocturne Botanica", "Vespera", "Salina Club"])
        for preset in sh.PRESETS:
            self.assertTrue(preset["prompt"])
            self.assertTrue(preset["location"])


@_REQUIRES_DEPS
class ApiRouteTests(unittest.TestCase):
    def test_ask_endpoint_forwards_stateful_request(self) -> None:
        expected = {"ready_for_session": False, "state": {}}
        with patch.object(sh, "ask_turn", return_value=expected) as ask_turn:
            response = sh.ask(
                sh.AskRequest(
                    prompt="Need a matcha campaign",
                    state={"brand_name": "Chaen"},
                    selected_seeds=["Erewhon"],
                    selected_competitors=["Red Bull"],
                    selected_location="New York, NY",
                )
            )

        self.assertEqual(response, expected)
        ask_turn.assert_called_once_with(
            "Need a matcha campaign",
            state={"brand_name": "Chaen"},
            selected_seeds=["Erewhon"],
            selected_competitors=["Red Bull"],
            selected_location="New York, NY",
        )

    def test_session_endpoint_prefers_locked_signals(self) -> None:
        resolved = {"brand_name": "Chaen", "resolved_entities": {}}
        frames = iter(["data: {\"type\": \"complete\"}\n\n"])
        with (
            patch.object(
                sh, "stream_resolved_grounding", return_value=frames
            ) as locked_stream,
            patch.object(sh, "stream_campaign_grounding") as prompt_stream,
        ):
            response = sh.session_stream(
                sh.SessionRequest(
                    resolved_signals=resolved,
                    prompt="This must be ignored",
                    location="New York, NY",
                )
            )

        self.assertEqual(response.media_type, "text/event-stream")
        locked_stream.assert_called_once_with(resolved, "New York, NY")
        prompt_stream.assert_not_called()


if __name__ == "__main__":
    unittest.main()
