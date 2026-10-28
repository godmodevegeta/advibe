"""Offline coverage for multi-city Ask transitions and scoped generation."""

import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import ask_flow as af
from campaign_locations import apply_location_turn, locations_from, normalize_locations
import multi_grounding as mg
import stream_harness as sh
from test_ask_flow import _FakeQlooClient, _scoped_chaen


class LocationTests(unittest.TestCase):
    def test_add_remove_replace_aliases_and_legacy(self):
        state = af._state_from({"location_query": "New York, NY"})
        apply_location_turn(
            state,
            {"location_operation": "add", "locations": ["SF", "London", "sf"]},
            None,
        )
        self.assertEqual(
            [v["location_query"] for v in state["locations"]],
            ["New York, NY", "San Francisco, CA", "London, UK"],
        )
        apply_location_turn(
            state, {"location_operation": "remove", "locations": ["NYC"]}, None
        )
        self.assertEqual(state["location_query"], "San Francisco, CA")
        apply_location_turn(
            state, {"location_operation": "replace", "locations": ["London"]}, None
        )
        self.assertEqual(state["location_query"], "London, UK")
        apply_location_turn(
            state, {"location_operation": "remove", "locations": ["London"]}, None
        )
        self.assertEqual(state["locations"], [])
        self.assertIn("location", af._missing_pillars(state))
        self.assertEqual(
            locations_from({**state, "location_query": "New York, NY"}), []
        )
        self.assertEqual(
            normalize_locations(
                [{"location_query": "London", "neighborhood_hints": ["Soho"]}]
            )[0]["neighborhood_hints"],
            ["Soho"],
        )

    def test_ask_conversation_preserves_signals_and_explains_scope(self):
        with patch.object(af, "QlooClient", _FakeQlooClient), patch.object(
            af, "_scope_message", return_value=_scoped_chaen()
        ):
            initial = af.ask_turn(
                "Chaen",
                api_key="test",
                selected_seeds=["Chamberlain Coffee", "Erewhon"],
                selected_competitors=["Red Bull"],
                selected_location="NYC",
            )
        with patch.object(af, "QlooClient", _FakeQlooClient), patch.object(
            af, "_scope_message", return_value={}
        ):
            question = af.ask_turn(
                "can we add more target locations?",
                state=initial["state"],
                api_key="test",
            )
        self.assertIn("Which cities", question["assistant_message"])
        self.assertEqual(question["state"]["locations"], initial["state"]["locations"])
        change = {"location_operation": "add", "locations": ["SF", "London"]}
        with patch.object(af, "QlooClient", _FakeQlooClient), patch.object(
            af, "_scope_message", return_value=change
        ):
            added = af.ask_turn(
                "add SF and london", state=question["state"], api_key="test"
            )
        self.assertTrue(added["ready_for_session"])
        self.assertEqual(len(added["resolved_signals"]["locations"]), 3)
        self.assertEqual(added["resolved_signals"]["tribe_scope"], "overall")
        self.assertIn("3 tribes total", added["assistant_message"])
        self.assertIn("San Francisco, CA", added["crafted_prompt"])
        self.assertEqual(
            added["resolved_signals"]["resolved_entities"],
            initial["resolved_signals"]["resolved_entities"],
        )
        with patch.object(af, "QlooClient", _FakeQlooClient), patch.object(
            af, "_scope_message", return_value={}
        ):
            chosen = af.ask_turn(
                state=added["state"],
                selected_tribe_scope="per_location",
                api_key="test",
            )
        self.assertIn("9 total", chosen["assistant_message"])
        self.assertEqual(chosen["resolved_signals"]["tribe_scope"], "per_location")


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(
            (
                Path(__file__).parent.parent
                / "advibe-frontend/src/fixtures/grounding.json"
            ).read_text()
        )
        self.signals = {
            "brand_name": "Chaen",
            "locations": normalize_locations(["NYC", "SF", "London"]),
            "tribe_scope": "overall",
            "raw_signals": {},
        }

    def city(
        self,
        resolved,
        *,
        api_key,
        location_override,
        on_event,
        generate,
        trending_cache=None
    ):
        self.assertFalse(generate)
        self.assertEqual(
            resolved["neighborhood_hints"],
            resolved["locations"][0]["neighborhood_hints"],
        )
        self.assertEqual(resolved["raw_signals"]["location_query"], location_override)
        for artifact in ("geo_pins", "audience_insights", "packets"):
            on_event(
                {
                    "type": "artifact_patch",
                    "timestamp": 1,
                    "artifact": artifact,
                    "data": copy.deepcopy(self.fixture[artifact]),
                }
            )
        return {
            "brand_name": "Chaen",
            "location_query": location_override,
            "demographics": self.fixture["audience_insights"]["demographics"],
            "taste_vocabulary": [],
            "heatmap_pins": self.fixture["geo_pins"]["heatmap_pins"],
            "strategies": [],
            "_campaign": {},
            "_packets": self.fixture["packets"],
            "_meta": {"trending": {}},
        }

    def test_three_total_and_nine_per_city(self):
        for scope, count in (("overall", 3), ("per_location", 9)):
            events = []
            with patch.object(
                mg, "build_grounding", side_effect=self.city
            ), patch.object(
                mg, "generate_strategies", return_value=(self.fixture["strategies"], {})
            ):
                result = mg.build_multi_grounding(
                    {**self.signals, "tribe_scope": scope},
                    api_key="test",
                    on_event=events.append,
                )
            self.assertEqual(len(result["strategies"]), count)
            self.assertEqual(len({s["id"] for s in result["strategies"]}), count)
            if scope == "overall":
                self.assertTrue(
                    all(len(s["location_variants"]) == 3 for s in result["strategies"])
                )
            self.assertEqual(len(result["city_outputs"]), 3)
            self.assertEqual(len([e for e in events if e["type"] == "checkpoint"]), 1)
            self.assertEqual(events[-1]["type"], "checkpoint")
            self.assertEqual(
                {e["location_id"] for e in events if e.get("artifact") == "geo_pins"},
                {"city_1", "city_2", "city_3"},
            )

    def test_city_failure_retains_partial_artifacts_and_never_completes(self):
        events = []
        count = 0

        def fail_second(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError("Qloo unavailable")
            return self.city(*args, **kwargs)

        with patch.object(mg, "build_grounding", side_effect=fail_second):
            with self.assertRaises(mg.CityGroundingError) as error:
                mg.build_multi_grounding(
                    self.signals, api_key="test", on_event=events.append
                )
        self.assertIn("San Francisco, CA", str(error.exception))
        self.assertTrue(any(e.get("artifact") == "geo_pins" for e in events))
        self.assertFalse(any(e["type"] in ("checkpoint", "complete") for e in events))

    def test_stream_routes_multi_city_and_reports_failed_city(self):
        events = []
        with patch.object(sh, "load_qloo_api_key", return_value="test"), patch.object(
            sh,
            "build_multi_grounding",
            side_effect=mg.CityGroundingError("London, UK", RuntimeError("Offline")),
        ):
            events = [
                json.loads(f.removeprefix("data: "))
                for f in sh.stream_resolved_grounding(self.signals)
            ]
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(events[-1]["location_query"], "London, UK")

    def test_edited_brief_updates_cities_and_scope(self):
        observed = {}

        def build(resolved, **kwargs):
            observed.update(resolved)
            return {
                "brand_name": "Chaen",
                "location_query": "NYC; London",
                "demographics": {},
                "taste_vocabulary": [],
                "heatmap_pins": [],
                "strategies": [],
            }

        with patch.object(sh, "extract_seed_signals", return_value={}), patch.object(
            sh, "resolve_signals", return_value={}
        ), patch.object(sh, "load_qloo_api_key", return_value="test"), patch.object(
            sh,
            "_scope_message",
            return_value={
                "locations": ["NYC", "London"],
                "location_operation": "add",
                "tribe_scope": "per_location",
            },
        ), patch.object(
            sh, "build_multi_grounding", side_effect=build
        ):
            list(
                sh.stream_campaign_grounding(
                    "Edited full brief",
                    locations=self.signals["locations"],
                    tribe_scope="overall",
                )
            )
        # Full edited briefs are authoritative rather than appended to the previous list.
        self.assertEqual(len(observed["locations"]), 2)
        self.assertEqual(observed["tribe_scope"], "per_location")
