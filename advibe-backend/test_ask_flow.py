"""Offline tests for the stateful Ask workflow."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import ask_flow as af


class _FakeQlooClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def __enter__(self) -> "_FakeQlooClient":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def discover_entity_tags(self, entity_ids: list[str], take: int = 8) -> list[dict]:
        return [
            {
                "tag_id": f"urn:tag:interests:qloo:{name}",
                "name": name,
            }
            for name in ("tea", "wellness", "music")
        ]

    def search_entities(
        self,
        name: str,
        *,
        types: str | None = None,
        take: int = 5,
    ) -> list[dict]:
        entities = {
            "Chamberlain Coffee": ("brand", "urn:entity:brand"),
            "Erewhon": ("brand", "urn:entity:brand"),
            "Ippodo Tea": ("brand", "urn:entity:brand"),
            "Ryuichi Sakamoto": ("artist", "urn:entity:artist"),
            "Lost in Translation": ("movie", "urn:entity:movie"),
            "Red Bull": ("brand", "urn:entity:brand"),
            "Starbucks": ("brand", "urn:entity:brand"),
            "Casamigos": ("brand", "urn:entity:brand"),
            "Soho House": ("place", "urn:entity:place"),
            "Khruangbin": ("artist", "urn:entity:artist"),
            "Don Julio": ("brand", "urn:entity:brand"),
        }
        item = entities.get(name)
        if not item:
            return []
        _, subtype = item
        if types and subtype != types:
            return []
        return [
            {
                "name": name,
                "entity_id": f"urn:entity:{item[0]}:{name.casefold().replace(' ', '_')}",
                "types": [subtype],
                "subtype": subtype,
                "popularity": 0.9,
            }
        ]

    def search_tags(
        self,
        query: str,
        *,
        semantic: bool,
        take: int = 5,
    ) -> list[dict]:
        return [
            {
                "tag_id": f"urn:tag:interests:qloo:{query.replace(' ', '_')}",
                "name": query,
                "type": "urn:tag:interests:qloo",
                "popularity": 0.8,
            }
        ]


class _NoSearchQlooClient(_FakeQlooClient):
    def search_entities(self, *args: object, **kwargs: object) -> list[dict]:
        raise AssertionError("pre-verified entity pills must not be searched")

    def search_tags(self, *args: object, **kwargs: object) -> list[dict]:
        raise AssertionError("this scenario has no tags to resolve")


def _scoped_chaen() -> dict:
    return {
        "brand_name": "Chaen",
        "product_description": "canned ceremonial matcha drink",
        "explicit_seed_brands": [],
        "explicit_competitor_brands": [],
        "seed_tags": ["matcha", "japanese tea", "wellness"],
        "location": None,
        "location_query": None,
        "neighborhood_hints": [],
        "suggested_seed_queries": [
            "Chamberlain Coffee",
            "Erewhon",
            "Ippodo Tea",
            "Ryuichi Sakamoto",
            "Lost in Translation",
        ],
        "suggested_competitor_queries": ["Red Bull", "Starbucks"],
    }


def _scoped_humo() -> dict:
    return {
        "brand_name": "Humo Santo",
        "product_description": "artisanal Espadín mezcal",
        "explicit_seed_brands": ["Casamigos", "Soho House", "Khruangbin"],
        "explicit_competitor_brands": ["Don Julio"],
        "seed_tags": ["mezcal", "mexican", "vinyl records"],
        "location": "Austin, Texas",
        "location_query": "Austin, TX",
        "neighborhood_hints": [],
        "suggested_seed_queries": [],
        "suggested_competitor_queries": [],
    }


class AskFlowTests(unittest.TestCase):
    def test_seed_replacement_removes_old_signal_and_stale_tags(self) -> None:
        with (
            patch.object(af, "QlooClient", _FakeQlooClient),
            patch.object(af, "_scope_message", return_value=_scoped_chaen()),
        ):
            initial = af.ask_turn(
                "Chaen",
                api_key="test",
                selected_seeds=["Chamberlain Coffee", "Erewhon"],
                selected_competitors=["Red Bull"],
                selected_location="New York, NY",
            )
        change = {
            "removed_seed_names": ["Erewhon"],
            "explicit_seed_brands": ["Ippodo Tea"],
            "location_query": "Austin, TX",
        }
        with (
            patch.object(af, "QlooClient", _FakeQlooClient),
            patch.object(af, "_scope_message", return_value=change),
        ):
            result = af.ask_turn(
                "Replace Erewhon with Ippodo Tea in Austin",
                state=initial["state"],
                api_key="test",
            )
        names = [
            e["name"] for e in result["resolved_signals"]["resolved_entities"]["seed"]
        ]
        self.assertEqual(names, ["Chamberlain Coffee", "Ippodo Tea"])
        self.assertNotIn("Erewhon", result["state"]["explicit_seed_brands"])
        self.assertEqual(result["state"]["location_query"], "Austin, TX")
        self.assertTrue(result["ready_for_session"])
        change["explicit_seed_brands"] = ["Unknown brand"]
        with (
            patch.object(af, "QlooClient", _FakeQlooClient),
            patch.object(af, "_scope_message", return_value=change),
        ):
            unresolved = af.ask_turn(
                "Replace Erewhon with Unknown brand",
                state=initial["state"],
                api_key="test",
            )
        self.assertFalse(unresolved["ready_for_session"])
        self.assertIn("seeds", unresolved["missing_pillars"])

    def test_follow_up_scope_includes_prior_campaign_context(self) -> None:
        current = af._state_from(
            {
                "brand_name": "Chaen",
                "product_description": "ceremonial matcha",
                "messages": ["Launch Chaen"],
            }
        )
        with patch.object(af, "complete_json", return_value={}) as complete:
            af._scope_message("Red Bull", current)
        messages = complete.call_args.args[0]
        payload = json.loads(messages[1]["content"])
        self.assertEqual(payload["prompt"], "Red Bull")
        self.assertEqual(
            payload["context"],
            {
                "existing_brand_name": "Chaen",
                "existing_product_description": "ceremonial matcha",
                "existing_seed_names": [],
                "existing_locations": [],
                "existing_tribe_scope": "overall",
                "currently_missing_pillars": ["location", "seeds", "competitor"],
            },
        )
        self.assertIn("short brand name", messages[0]["content"])

    def test_sparse_tags_discover_and_filter_entity_interests(self) -> None:
        scoped = _scoped_humo()
        scoped["seed_tags"] = []
        discovered = [
            {"name": "Vinyl", "tag_id": "urn:tag:interests:qloo:vinyl"},
            {"name": "Vinyl", "tag_id": "urn:tag:interests:qloo:vinyl"},
            {"name": "Mezcal", "tag_id": "urn:tag:cuisine:qloo:mezcal"},
            {"name": "Tech", "tag_id": "urn:tag:cultural_relevance:qloo:tech"},
            {"name": "Sword", "tag_id": "urn:tag:keyword:qloo:sword"},
            {"name": "Pop up", "tag_id": "urn:tag:setting:qloo:pop_up"},
            {"name": "Affluent", "tag_id": "urn:tag:customer_segment:qloo:affluent"},
        ]
        with (
            patch.object(af, "complete_json", return_value=scoped),
            patch.object(af, "QlooClient", _FakeQlooClient),
            patch.object(
                _FakeQlooClient, "discover_entity_tags", return_value=discovered
            ) as discover,
        ):
            result = af.ask_turn("Launch Humo Santo", api_key="test-key")
        self.assertEqual(discover.call_args.kwargs, {"take": 8})
        self.assertEqual(len(discover.call_args.args[0]), 3)
        resolved = result["resolved_signals"]
        self.assertEqual(len(resolved["resolved_tags"]), 3)
        self.assertEqual(
            resolved["insights_tags"],
            [
                "urn:tag:cuisine:qloo:mezcal",
                "urn:tag:cultural_relevance:qloo:tech",
                "urn:tag:interests:qloo:vinyl",
            ],
        )

    def test_sufficient_tags_skip_discovery(self) -> None:
        with (
            patch.object(af, "complete_json", return_value=_scoped_humo()),
            patch.object(af, "QlooClient", _FakeQlooClient),
            patch.object(_FakeQlooClient, "discover_entity_tags") as discover,
        ):
            af.ask_turn("Launch Humo Santo", api_key="test-key")
        discover.assert_not_called()

    def test_prefix_fallback_checks_subtype_and_exclusions(self) -> None:
        candidates = [
            {
                "name": "Khruangbin Radio",
                "entity_id": "bad",
                "subtype": "urn:entity:podcast",
            },
            {
                "name": "Khruangbin Live",
                "entity_id": "excluded",
                "subtype": "urn:entity:artist",
            },
            {
                "name": "Unrelated Artist",
                "entity_id": "wrong",
                "subtype": "urn:entity:artist",
            },
            {
                "name": "Khruangbin Band",
                "entity_id": "artist",
                "subtype": "urn:entity:artist",
            },
        ]
        with patch.object(
            af, "_fetch_entity_candidates", return_value=(candidates, "untyped")
        ):
            result = af._resolve_entity_query(
                _FakeQlooClient("key"),
                "Khruangbin",
                competitor=False,
                excluded_ids={"excluded"},
            )
            competitor = af._resolve_entity_query(
                _FakeQlooClient("key"),
                "Khruangbin",
                competitor=True,
                excluded_ids=set(),
            )
        self.assertEqual(result["entity_id"], "artist")
        self.assertIsNone(competitor)

    def test_incomplete_brief_returns_verified_suggestions(self) -> None:
        with (
            patch.object(af, "complete_json", return_value=_scoped_chaen()),
            patch.object(af, "QlooClient", _FakeQlooClient),
        ):
            result = af.ask_turn(
                "I want to launch ads for my new matcha drink Chaen",
                api_key="test-key",
            )

        self.assertFalse(result["ready_for_session"])
        self.assertEqual(result["missing_pillars"], ["location", "seeds", "competitor"])
        self.assertTrue(result["assistant_message"])
        self.assertGreaterEqual(len(result["suggestions"]["seeds"]), 4)
        self.assertGreaterEqual(len(result["suggestions"]["competitors"]), 2)
        for entity in [
            *result["suggestions"]["seeds"],
            *result["suggestions"]["competitors"],
        ]:
            self.assertTrue(entity["entity_id"].startswith("urn:entity:"))
            self.assertTrue(entity["subtype"].startswith("urn:entity:"))

    def test_selected_follow_up_locks_grounding_signals(self) -> None:
        with (
            patch.object(af, "complete_json", return_value=_scoped_chaen()),
            patch.object(af, "QlooClient", _FakeQlooClient),
        ):
            first = af.ask_turn(
                "I want to launch ads for my new matcha drink Chaen",
                api_key="test-key",
            )
            result = af.ask_turn(
                state=first["state"],
                selected_seeds=["Chamberlain Coffee", "Erewhon"],
                selected_competitors=["Red Bull"],
                selected_location="New York, NY",
                api_key="test-key",
            )

        self.assertTrue(result["ready_for_session"])
        self.assertEqual(result["missing_pillars"], [])
        resolved = result["resolved_signals"]
        self.assertEqual(resolved["brand_name"], "Chaen")
        self.assertEqual(resolved["location_query"], "New York, NY")
        self.assertGreaterEqual(len(resolved["resolved_entities"]["seed"]), 2)
        self.assertEqual(
            resolved["resolved_entities"]["competitors"][0]["subtype"],
            "urn:entity:brand",
        )
        self.assertIn("raw_signals", resolved)

    def test_complete_brief_is_ready_in_one_turn(self) -> None:
        with (
            patch.object(af, "complete_json", return_value=_scoped_humo()),
            patch.object(af, "QlooClient", _FakeQlooClient),
        ):
            result = af.ask_turn(
                "Build an Austin, Texas campaign for Humo Santo.",
                api_key="test-key",
            )

        self.assertTrue(result["ready_for_session"])
        self.assertEqual(result["missing_pillars"], [])
        self.assertEqual(result["resolved_signals"]["location_query"], "Austin, TX")

    def test_preverified_pills_bypass_entity_lookup(self) -> None:
        state = {
            "brand_name": "Chaen",
            "product_description": "canned matcha",
            "location": "New York, NY",
            "location_query": "New York, NY",
        }
        seeds = [
            {
                "name": "Erewhon",
                "entity_id": "urn:entity:brand:erewhon",
                "subtype": "urn:entity:brand",
            },
            {
                "name": "Clairo",
                "entity_id": "urn:entity:artist:clairo",
                "subtype": "urn:entity:artist",
            },
        ]
        competitor = [
            {
                "name": "Red Bull",
                "entity_id": "urn:entity:brand:red_bull",
                "subtype": "urn:entity:brand",
            }
        ]
        with patch.object(af, "QlooClient", _NoSearchQlooClient):
            result = af.ask_turn(
                state=state,
                selected_seeds=seeds,
                selected_competitors=competitor,
                api_key="test-key",
            )

        self.assertTrue(result["ready_for_session"])
        self.assertEqual(
            result["resolved_signals"]["raw_signals"]["seed_brands"],
            ["Erewhon", "Clairo"],
        )


if __name__ == "__main__":
    unittest.main()
