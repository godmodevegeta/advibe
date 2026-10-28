"""Offline tests for the deterministic parts of build_grounding.py."""

from __future__ import annotations

import threading
import unittest
from unittest.mock import patch

import build_grounding as bg


def _entity(
    entity_id: str,
    name: str,
    *,
    domain: str = "artist",
    affinity: float = 0.8,
    popularity: float = 0.9,
) -> dict:
    return {
        "entity_id": entity_id,
        "name": name,
        "domain": domain,
        "subtype": f"urn:entity:{domain}",
        "affinity": affinity,
        "popularity": popularity,
        "popularity_known": popularity > 0,
        "arbitrage_score": bg.arbitrage_score(affinity, popularity),
        "high_arbitrage": affinity > 0.8 and 0 < popularity < 0.78,
        "signal_contribution": None,
        "descriptors": [],
    }


class ArbitrageTests(unittest.TestCase):
    def test_standard_score(self) -> None:
        self.assertEqual(bg.arbitrage_score(0.84, 0.71), 1.18)

    def test_popularity_floor(self) -> None:
        self.assertEqual(bg.arbitrage_score(0.84, 0.0), 2.4)

    def test_zero_affinity(self) -> None:
        self.assertEqual(bg.arbitrage_score(0.0, 0.9), 0.0)


class DistanceTests(unittest.TestCase):
    def test_haversine_known_distance(self) -> None:
        first = {"latitude": 30.26802, "longitude": -97.74742}
        second = {"latitude": 30.250168, "longitude": -97.75017}
        distance = bg.haversine_km(first, second)
        self.assertGreater(distance, 1.9)
        self.assertLess(distance, 2.1)


class GeoLabelTests(unittest.TestCase):
    def test_nominatim_label_prefers_neighbourhood(self) -> None:
        payload = {
            "address": {
                "neighbourhood": "Lower East Side",
                "suburb": "Manhattan",
                "city_district": "Manhattan Community Board 3",
            }
        }
        self.assertEqual(bg._nominatim_label(payload), "Lower East Side")

    def test_broad_geocode_labels(self) -> None:
        self.assertTrue(bg._is_broad_geocode_label("Brooklyn"))
        self.assertTrue(
            bg._is_broad_geocode_label("Manhattan Community Board 3")
        )
        self.assertTrue(bg._is_broad_geocode_label("New York County"))
        self.assertFalse(bg._is_broad_geocode_label("Lower East Side"))
        self.assertFalse(bg._is_broad_geocode_label("Theater District"))

    def test_heatmap_label_retries_broad_label(self) -> None:
        pin = {"latitude": 40.715332, "longitude": -73.98193}
        responses = {
            17: {"label": "Manhattan Community Board 3"},
            18: {"label": "Lower East Side"},
        }

        def fake_reverse(
            latitude: float, longitude: float, *, zoom: int = 17
        ) -> dict:
            return responses[zoom]

        with patch.object(bg, "_reverse_geocode", side_effect=fake_reverse):
            bg._build_heatmap_label(pin, enable_nominatim=True)

        self.assertEqual(pin["neighborhood_label"], "Lower East Side")
        self.assertEqual(pin["label_source"], "nominatim")

    def test_heatmap_label_keeps_good_label(self) -> None:
        pin = {"latitude": 40.759277, "longitude": -73.98193}
        responses = {
            17: {"label": "Theater District"},
            18: {"label": "Manhattan Community Board 5"},
        }

        def fake_reverse(
            latitude: float, longitude: float, *, zoom: int = 17
        ) -> dict:
            return responses[zoom]

        with patch.object(bg, "_reverse_geocode", side_effect=fake_reverse):
            bg._build_heatmap_label(pin, enable_nominatim=True)

        self.assertEqual(pin["neighborhood_label"], "Theater District")
        self.assertEqual(pin["label_source"], "nominatim")

    def test_target_city_is_treated_as_broad(self) -> None:
        self.assertTrue(
            bg._is_broad_geocode_label("Miami", "Miami, FL")
        )
        self.assertFalse(bg._is_broad_geocode_label("Miami"))

    def test_heatmap_label_retries_target_city_label(self) -> None:
        pin = {"latitude": 25.743713, "longitude": -80.216675}
        responses = {
            17: {"label": "Miami"},
            18: {"label": "Shore Drive East"},
        }

        def fake_reverse(
            latitude: float, longitude: float, *, zoom: int = 17
        ) -> dict:
            return responses[zoom]

        with patch.object(bg, "_reverse_geocode", side_effect=fake_reverse):
            bg._build_heatmap_label(
                pin,
                enable_nominatim=True,
                location_query="Miami, FL",
            )

        self.assertEqual(pin["neighborhood_label"], "Shore Drive East")
        self.assertEqual(pin["label_source"], "nominatim")

    def test_nominatim_label_accepts_hamlet(self) -> None:
        payload = {
            "address": {
                "hamlet": "Bay Heights",
                "city": "Miami",
            }
        }
        self.assertEqual(bg._nominatim_label(payload), "Bay Heights")

    def test_area_label_matches_base_city(self) -> None:
        self.assertIn("Miami", bg._name_variants("Miami Area"))
        self.assertTrue(bg._mentions_name("Miami creatives", "Miami Area"))

    def test_venue_fallback_accepts_near_venue(self) -> None:
        pin = {
            "label_source": "pending",
            "nearest_venue": "Panther Coffee",
            "nearest_venue_distance_km": 1.2,
        }

        bg._apply_heatmap_label_fallback(
            pin, location_query="Miami, FL"
        )

        self.assertEqual(pin["neighborhood_label"], "Panther Coffee")
        self.assertEqual(pin["label_source"], "venue_fallback")

    def test_venue_fallback_rejects_far_venue(self) -> None:
        pin = {
            "label_source": "pending",
            "nearest_venue": "Hotel Breakwater South Beach",
            "nearest_venue_distance_km": 9.47,
        }

        bg._apply_heatmap_label_fallback(
            pin, location_query="Miami, FL"
        )

        self.assertEqual(pin["neighborhood_label"], "Miami Area")
        self.assertEqual(pin["label_source"], "location_fallback")

    def test_venue_fallback_without_distance_uses_city(self) -> None:
        pin = {
            "label_source": "pending",
            "nearest_venue": "Panther Coffee",
            "nearest_venue_distance_km": None,
        }

        bg._apply_heatmap_label_fallback(
            pin, location_query="Miami, FL"
        )

        self.assertEqual(pin["neighborhood_label"], "Miami Area")
        self.assertEqual(pin["label_source"], "location_fallback")

    def test_venue_fallback_keeps_nominatim_label(self) -> None:
        pin = {
            "label_source": "nominatim",
            "neighborhood_label": "Shore Drive East",
            "nearest_venue": "Panther Coffee",
            "nearest_venue_distance_km": 1.2,
        }

        bg._apply_heatmap_label_fallback(
            pin, location_query="Miami, FL"
        )

        self.assertEqual(pin["neighborhood_label"], "Shore Drive East")
        self.assertEqual(pin["label_source"], "nominatim")


class PinSelectionTests(unittest.TestCase):
    def test_select_pins_prefers_high_affinity_and_separation(self) -> None:
        pins = [
            {"latitude": 30.0, "longitude": -97.0, "affinity": 1.0},
            {"latitude": 30.0001, "longitude": -97.0, "affinity": 0.99},
            {"latitude": 30.02, "longitude": -97.0, "affinity": 0.98},
            {"latitude": 30.0, "longitude": -97.03, "affinity": 0.97},
        ]
        selected = bg.select_pins(pins, min_separation_km=2.0)
        self.assertEqual(len(selected), 3)
        self.assertEqual(
            [pin["affinity"] for pin in selected], [1.0, 0.98, 0.97]
        )


class WalkablePinTests(unittest.TestCase):
    def _place(
        self,
        entity_id: str,
        name: str,
        latitude: float,
        longitude: float,
        affinity: float = 0.8,
    ) -> dict:
        return {
            "entity_id": entity_id,
            "name": name,
            "latitude": latitude,
            "longitude": longitude,
            "has_coordinates": True,
            "affinity": affinity,
            "popularity": 0.5,
        }

    def _heat_pin(
        self,
        geohash: str,
        latitude: float,
        longitude: float,
        affinity: float,
    ) -> dict:
        return {
            "geohash": geohash,
            "latitude": latitude,
            "longitude": longitude,
            "affinity": affinity,
            "affinity_rank": None,
            "popularity": 0.5,
        }

    def test_far_venue_cell_is_rejected_and_places_backfill(self) -> None:
        heatmap_pins = [
            self._heat_pin("civic", 37.78, -122.41, 1.0),
            self._heat_pin("alcatraz", 37.8266, -122.4213, 0.99),
            self._heat_pin("chinatown", 37.795, -122.4062, 0.98),
        ]
        places = [
            self._place("p1", "Civic Venue", 37.7801, -122.4101),
            self._place("p2", "Chinatown Venue", 37.7951, -122.4063),
            self._place("p3", "Hayes Venue", 37.77, -122.43),
            self._place("p4", "Mission Venue", 37.76, -122.45),
        ]
        selected, _, degrees, warnings = bg._finalize_walkable_pins(
            heatmap_pins,
            places,
            enable_nominatim=False,
            location_query="San Francisco, CA",
        )
        self.assertEqual(len(selected), 3)
        self.assertEqual(degrees, bg.PIN_DEGREE_SEPARATION)
        self.assertEqual(warnings, [])
        self.assertTrue(
            all(
                pin["nearest_venue_distance_km"]
                <= bg.WALKABLE_VENUE_MAX_DISTANCE_KM
                for pin in selected
            )
        )
        self.assertFalse(
            any(abs(pin["latitude"] - 37.8266) < 0.001 for pin in selected)
        )
        for index, pin in enumerate(selected):
            for other in selected[index + 1 :]:
                self.assertGreaterEqual(
                    bg._degree_separation(pin, other),
                    bg.PIN_DEGREE_SEPARATION,
                )

    def test_banned_heatmap_label_is_replaced(self) -> None:
        heatmap_pins = [
            self._heat_pin("bad", 37.8266, -122.4213, 1.0),
            self._heat_pin("good1", 37.78, -122.41, 0.9),
            self._heat_pin("good2", 37.795, -122.4062, 0.8),
        ]
        places = [
            self._place("bad", "Wharf Kiosk", 37.8267, -122.4214),
            self._place("p1", "Civic Venue", 37.7801, -122.4101),
            self._place("p2", "Chinatown Venue", 37.7951, -122.4063),
            self._place("p3", "Hayes Venue", 37.77, -122.43),
            self._place("p4", "Mission Venue", 37.76, -122.45),
        ]

        def fake_label(
            pin: dict,
            *,
            enable_nominatim: bool,
            location_query: str | None = None,
        ) -> None:
            if abs(pin["latitude"] - 37.8266) < 0.001:
                label = "Alcatraz Wharf"
            else:
                label = "Civic Center"
            pin["neighborhood_label"] = label
            pin["label_source"] = "nominatim"

        with patch.object(bg, "_build_heatmap_label", side_effect=fake_label):
            selected, _, _, warnings = bg._finalize_walkable_pins(
                heatmap_pins,
                places,
                enable_nominatim=True,
                location_query="San Francisco, CA",
            )
        self.assertEqual(len(selected), 3)
        self.assertEqual(warnings, [])
        self.assertFalse(
            any(
                bg._is_banned_geo_label(pin.get("neighborhood_label"))
                for pin in selected
            )
        )
        self.assertTrue(
            any(
                pin.get("label_source") == "location_fallback"
                for pin in selected
            )
        )
        self.assertTrue(
            all(
                pin["nearest_venue_distance_km"]
                <= bg.WALKABLE_VENUE_MAX_DISTANCE_KM
                for pin in selected
            )
        )

    def test_banned_label_terms_use_word_boundaries(self) -> None:
        for label in (
            "Alcatraz Wharf",
            "Treasure Island",
            "Bay Bridge",
            "SFO Airport",
        ):
            with self.subTest(label=label):
                self.assertTrue(bg._is_banned_geo_label(label))
        for label in ("Bayview", "Civic Center", "Chinatown"):
            with self.subTest(label=label):
                self.assertFalse(bg._is_banned_geo_label(label))


class DemographicsTests(unittest.TestCase):
    def _payload(self) -> dict:
        return {
            "results": {
                "demographics": [
                    {
                        "entity_id": "brand-1",
                        "query": {
                            "age": {
                                "30_to_34": 0.6,
                                "35_to_44": -0.79,
                            },
                            "gender": {
                                "male": -0.26,
                                "female": 0.26,
                            },
                        },
                    },
                    {
                        "entity_id": "artist-1",
                        "query": {
                            "age": {
                                "30_to_34": -0.78,
                                "35_to_44": 0.29,
                            },
                            "gender": {
                                "male": 0.16,
                                "female": -0.16,
                            },
                        },
                    },
                ]
            }
        }

    def test_aggregate_mean_is_primary(self) -> None:
        seeds = [
            {
                "entity_id": "brand-1",
                "name": "Casamigos",
                "subtype": "urn:entity:brand",
            },
            {
                "entity_id": "artist-1",
                "name": "Khruangbin",
                "subtype": "urn:entity:artist",
            },
        ]
        demo = bg.parse_demographics(self._payload(), seeds)
        self.assertEqual(demo["primary"], "aggregate")
        self.assertAlmostEqual(
            demo["aggregate_age"]["30_to_34"], -0.09, places=4
        )
        self.assertAlmostEqual(
            demo["aggregate_gender"]["female"], 0.05, places=4
        )

    def test_non_seed_signal_blocks_are_ignored(self) -> None:
        payload = self._payload()
        payload["results"]["demographics"].append(
            {
                "entity_id": "urn:tag:lifestyle:qloo:fitness",
                "query": {
                    "age": {"25_to_29": 0.8},
                    "gender": {"female": 0.4},
                },
            }
        )
        seeds = [
            {
                "entity_id": "brand-1",
                "name": "Casamigos",
                "subtype": "urn:entity:brand",
            },
            {
                "entity_id": "artist-1",
                "name": "Khruangbin",
                "subtype": "urn:entity:artist",
            },
        ]

        demo = bg.parse_demographics(payload, seeds)

        self.assertEqual(
            [block["name"] for block in demo["all_seed_blocks"]],
            ["Casamigos", "Khruangbin"],
        )
        self.assertIsNone(demo["aggregate_age"]["25_to_29"])

    def test_artist_seed_skew(self) -> None:
        seeds = [
            {
                "entity_id": "brand-1",
                "name": "Casamigos",
                "subtype": "urn:entity:brand",
            },
            {
                "entity_id": "artist-1",
                "name": "Khruangbin",
                "subtype": "urn:entity:artist",
            },
        ]
        demo = bg.parse_demographics(self._payload(), seeds)
        self.assertEqual(len(demo["artist_seed_blocks"]), 1)
        self.assertAlmostEqual(
            demo["artist_seed_age"]["35_to_44"], 0.29, places=4
        )
        self.assertEqual(
            demo["recommended_genders"]["underground_arbitrage"], [1, 2]
        )
        self.assertEqual(
            demo["recommended_age_ranges"]["underground_arbitrage"],
            [22, 34],
        )
        self.assertEqual(
            demo["recommended_age_ranges"]["competitor_conquest"],
            [28, 44],
        )

    def test_age_ranges_are_always_distinct(self) -> None:
        seeds = [
            {
                "entity_id": "brand-1",
                "name": "Casamigos",
                "subtype": "urn:entity:brand",
            },
        ]
        for peak in bg.AGE_COHORTS:
            with self.subTest(peak=peak):
                payload = self._payload()
                payload["results"]["demographics"] = [
                    {
                        "entity_id": "brand-1",
                        "query": {
                            "age": {
                                key: (0.8 if key == peak else -0.1)
                                for key in bg.AGE_COHORTS
                            },
                            "gender": {
                                "male": 0.5,
                                "female": -0.5,
                            },
                        },
                    }
                ]
                demo = bg.parse_demographics(payload, seeds)
                ranges = demo["recommended_age_ranges"]
                pairs = [
                    tuple(ranges[key])
                    for key in (
                        "core_high_affinity",
                        "underground_arbitrage",
                        "competitor_conquest",
                    )
                ]
                self.assertEqual(len(set(pairs)), 3)
                self.assertEqual(
                    ranges["core_high_affinity"],
                    list(bg._CORE_AGE_RANGES[peak]),
                )
                self.assertEqual(
                    demo["recommended_genders"]["core_high_affinity"],
                    [1],
                )
                self.assertEqual(
                    demo["recommended_genders"]["competitor_conquest"],
                    [1, 2],
                )


class AllocationTests(unittest.TestCase):
    def test_no_duplicates_and_theme_fit(self) -> None:
        brands = [
            _entity(
                f"b{index}",
                f"Brand {index}",
                domain="brand",
                affinity=0.9 - index * 0.01,
                popularity=0.95 if index < 3 else 0.7 - index * 0.05,
            )
            for index in range(9)
        ]
        brands[3]["popularity"] = 0.0
        groups = bg.allocate_entities(
            brands,
            packet1_count=3,
            packet2_count=3,
            packet3_count=3,
            packet1_predicate=lambda item: item["popularity"] >= 0.85,
            packet2_predicate=lambda item: item["popularity"] > 0.0,
        )
        flattened = [item["entity_id"] for group in groups for item in group]
        self.assertEqual(len(flattened), 9)
        self.assertEqual(len(set(flattened)), 9)
        self.assertTrue(
            all(item["popularity"] >= 0.85 for item in groups[0])
        )


class VenueAssignmentTests(unittest.TestCase):
    def test_venues_are_unique(self) -> None:
        pins = [
            {"latitude": 30.0, "longitude": -97.0},
            {"latitude": 30.02, "longitude": -97.0},
            {"latitude": 30.04, "longitude": -97.0},
        ]
        places = []
        for pin_index, pin in enumerate(pins):
            for place_index in range(3):
                places.append(
                    {
                        "entity_id": f"p{pin_index}-{place_index}",
                        "name": f"Place {pin_index}-{place_index}",
                        "latitude": pin["latitude"] + 0.001 * place_index,
                        "longitude": pin["longitude"],
                        "affinity": 0.9,
                        "has_coordinates": True,
                    }
                )
        groups = bg._assign_venues(pins, places)
        flattened = [
            place["entity_id"] for group in groups for place in group
        ]
        self.assertEqual(len(flattened), 9)
        self.assertEqual(len(set(flattened)), 9)
        self.assertTrue(all(len(group) == 3 for group in groups))


class PromptValidationTests(unittest.TestCase):
    def test_unicode_name_matching(self) -> None:
        self.assertTrue(
            bg._mentions_name("Meet us at Hotel San Jose.", "Hotel San Jose\u0301")
        )
        self.assertTrue(
            bg._mentions_name("Meet us at Perla\u2019s.", "Perla's")
        )

    def test_name_suffix_variants(self) -> None:
        self.assertTrue(
            bg._mentions_name(
                "We shot at Clark's Oyster Bar last night.",
                "Clark's Oyster Bar - Austin",
            )
        )
        self.assertTrue(
            bg._mentions_name(
                "Dinner at JW Marriott.", "JW Marriott Austin"
            )
        )
        self.assertTrue(
            bg._mentions_name(
                "Tim Ferriss Show is the reference.",
                "The Tim Ferriss Show",
            )
        )
        self.assertFalse(
            bg._mentions_name(
                "We follow standard practice.", "The Standard"
            )
        )

    def test_name_variants_handle_with_and_venue_suffixes(self) -> None:
        self.assertIn(
            "El Che", bg._name_variants("El Che Steakhouse & Bar")
        )
        self.assertIn(
            "Beverly Hills Hotel",
            bg._name_variants("The Beverly Hills Hotel"),
        )
        self.assertIn(
            "Beverly Hills",
            bg._name_variants("The Beverly Hills Hotel"),
        )
        self.assertIn(
            "Las Culturistas",
            bg._name_variants(
                "Las Culturistas with Matt Rogers and Bowen Yang"
            ),
        )

    def _packet(self) -> dict:
        return {
            "packet_id": "core_high_affinity",
            "strategy_id": "tribe_1",
            "required_mentions": {
                "artists": ["Jungle", "SAULT"],
                "movies": ["Roma"],
                "podcasts": ["Song Exploder"],
                "brands": ["The Standard"],
                "venues": ["La Casa"],
                "tags": ["Sultry", "Chill", "Art House"],
                "geo_label": "Warehouse District",
                "competitor": None,
            },
        }

    def _prompt(self, filler_repeats: int = 14) -> str:
        filler = (
            "Make the work specific to this packet and avoid generic "
            "choices."
        )
        base = (
            "Use Jungle and SAULT for the sonic palette. Use Roma for color "
            "grading. Shoot at La Casa in Warehouse District. The Standard "
            "is the brand reference. Cultural codes are Sultry, Chill, Art "
            "House. Never use: unlock, elevate, journey, curated, authentic, "
            "crafted, indulge, savor. "
        )
        return base + " ".join([filler] * filler_repeats)

    def test_valid_prompt(self) -> None:
        strategy = {
            "id": "tribe_1",
            "tribe_name": "The Warehouse District Crate",
            "strategic_angle": (
                "This tribe converts on cultural recognition. "
                "It avoids auction overlap through a single geo pin."
            ),
            "cultural_system_prompt": self._prompt(),
        }
        errors = bg._validate_one_strategy(strategy, self._packet())
        self.assertEqual(errors, [])

    def test_word_count_outside_validator_range(self) -> None:
        strategy = {
            "id": "tribe_1",
            "tribe_name": "The Warehouse District Crate",
            "strategic_angle": "One. Two.",
            "qloo_grounding_summary": "Grounding.",
            "cultural_system_prompt": self._prompt(60),
            "meta_adset_spec": {},
        }
        errors = bg._validate_one_strategy(strategy, self._packet())
        self.assertTrue(
            any("validator accepts" in error for error in errors)
        )

    def test_missing_artist(self) -> None:
        strategy = {
            "id": "tribe_1",
            "tribe_name": "The Warehouse District Crate",
            "strategic_angle": "One. Two.",
            "qloo_grounding_summary": "Grounding.",
            "cultural_system_prompt": self._prompt().replace(
                "Jungle", "Someone"
            ),
            "meta_adset_spec": {},
        }
        errors = bg._validate_one_strategy(strategy, self._packet())
        self.assertTrue(
            any("missing artists" in error for error in errors)
        )

    def test_banned_phrases_outside_clause(self) -> None:
        prompt = self._prompt().replace(
            "Cultural codes are",
            "The result feels authentic and seamless. Cultural codes are",
        )
        strategy = {
            "id": "tribe_1",
            "tribe_name": "The Warehouse District Crate",
            "strategic_angle": "One. Two.",
            "qloo_grounding_summary": "Grounding.",
            "cultural_system_prompt": prompt,
            "meta_adset_spec": {},
        }
        errors = bg._validate_one_strategy(strategy, self._packet())
        self.assertTrue(
            any(
                "outside the Never use clause" in error
                for error in errors
            )
        )
        self.assertIn("authentic", bg._banned_phrases_outside_clause(prompt))
        self.assertIn("seamless", bg._banned_phrases_outside_clause(prompt))

    def test_tribe_name_rejects_aesthetic(self) -> None:
        strategy = {
            "id": "tribe_1",
            "tribe_name": "South River City Lo-Fi Aesthetic",
            "strategic_angle": "One. Two.",
            "qloo_grounding_summary": "Grounding.",
            "cultural_system_prompt": self._prompt(),
            "meta_adset_spec": {},
        }
        errors = bg._validate_one_strategy(strategy, self._packet())
        self.assertTrue(
            any("audience or collective" in error for error in errors)
        )

    def test_tribe_name_word_count(self) -> None:
        strategy = {
            "id": "tribe_1",
            "tribe_name": "Tastemakers",
            "strategic_angle": "One. Two.",
            "qloo_grounding_summary": "Grounding.",
            "cultural_system_prompt": self._prompt(),
            "meta_adset_spec": {},
        }
        errors = bg._validate_one_strategy(strategy, self._packet())
        self.assertTrue(
            any("3-7 words" in error for error in errors)
        )

    def test_forbidden_phrases_uses_clause(self) -> None:
        prompt = (
            "Avoid forbidden phrases in copy. Use authentic details. "
            "Strictly avoid forbidden phrases: authentic, lifestyle."
        )
        scrubbed = bg.scrub_banned_phrases(prompt)
        before, clause, after = bg._split_banned_clause(scrubbed)
        self.assertIn("grounded details", scrubbed)
        self.assertNotIn("authentic", before.casefold())
        self.assertIn("authentic", clause.casefold())
        self.assertIn("lifestyle", clause.casefold())
        self.assertEqual(after, "")

    def test_scrub_preserves_clause(self) -> None:
        prompt = (
            "The result feels authentic, seamless, and lifestyle-driven. "
            "Never use: authentic, seamless, lifestyle."
        )
        scrubbed = bg.scrub_banned_phrases(prompt)
        before, clause, after = bg._split_banned_clause(scrubbed)
        self.assertNotIn("authentic", before.casefold())
        self.assertNotIn("seamless", before.casefold())
        self.assertNotIn("lifestyle", before.casefold())
        self.assertIn("authentic", clause.casefold())
        self.assertIn("seamless", clause.casefold())
        self.assertIn("lifestyle", clause.casefold())
        self.assertEqual(after, "")
        self.assertEqual(bg._banned_phrases_outside_clause(scrubbed), [])

    def test_scrub_text_after_clause(self) -> None:
        prompt = (
            "Use premium details. Never use: premium, iconic. "
            "Ensure premium production values."
        )
        scrubbed = bg.scrub_banned_phrases(prompt)
        before, clause, after = bg._split_banned_clause(scrubbed)
        self.assertNotIn("premium", before.casefold())
        self.assertIn("premium", clause.casefold())
        self.assertNotIn("premium", after.casefold())
        self.assertIn("high-craft", after.casefold())
        self.assertEqual(bg._banned_phrases_outside_clause(scrubbed), [])

    def test_avoid_in_sentence_does_not_split_clause(self) -> None:
        scrubbed = bg.scrub_banned_phrases(
            "The strategy avoids auction overlap and matches the vibe."
        )
        self.assertNotIn("vibe", scrubbed.casefold())
        self.assertIn("mood", scrubbed.casefold())

    def test_authentically_is_scrubbed(self) -> None:
        scrubbed = bg.scrub_banned_phrases(
            "Use the taste tags authentically."
        )
        self.assertIn("genuinely", scrubbed.casefold())
        self.assertNotIn("authentically", scrubbed.casefold())

    def test_lifestyle_replacement_is_grammatical(self) -> None:
        cases = {
            "outdoor lifestyle": "outdoor culture",
            "a lifestyle of quality": "a culture of quality",
            "lifestyle brand": "culture brand",
            "the Miami lifestyle": "the Miami culture",
            "lifestyle cues": "culture cues",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(
                    bg.scrub_banned_phrases(source), expected
                )

    def test_protected_mentions_survive_scrubbing(self) -> None:
        prompt = (
            "Use Active Lifestyle as a taste tag. "
            "Avoid an outdoor lifestyle."
        )
        scrubbed = bg.scrub_banned_phrases(
            prompt, protected=["Active Lifestyle"]
        )
        self.assertIn("Active Lifestyle", scrubbed)
        self.assertIn("outdoor culture", scrubbed)
        self.assertNotIn("Active Culture", scrubbed)

    def test_banned_phrase_detection_ignores_protected_mentions(self) -> None:
        prompt = (
            "Use Active Lifestyle as a taste tag. "
            "Never use unlock, journey, curated, iconic, or lifestyle."
        )
        self.assertEqual(
            bg._banned_phrases_outside_clause(
                prompt, ["Active Lifestyle"]
            ),
            [],
        )

    def test_bare_avoid_is_not_a_banned_clause(self) -> None:
        prompt = (
            "Avoid lifestyle clutter. Use authentic, crafted, and "
            "indulgent details."
        )
        self.assertFalse(bg._has_banned_clause(prompt))

    def test_validate_strategies_scrubs_before_validation(self) -> None:
        prompt = self._prompt().replace(
            "Cultural codes are",
            "The result feels authentic and seamless. Cultural codes are",
        )
        names = [
            "The Warehouse District Crate",
            "The Warehouse District Archive",
            "The Warehouse District Workshop",
        ]
        strategies = [
            {
                "id": "tribe_1",
                "tribe_name": name,
                "strategic_angle": "One. Two.",
                "qloo_grounding_summary": "Grounding.",
                "cultural_system_prompt": prompt,
                "meta_adset_spec": {},
            }
            for name in names
        ]
        raw, errors, warnings = bg._validate_strategies(
            {"strategies": strategies},
            [self._packet(), self._packet(), self._packet()],
        )
        self.assertEqual(errors, {})
        self.assertEqual(warnings, [])
        self.assertEqual(
            bg._banned_phrases_outside_clause(
                raw[0]["cultural_system_prompt"]
            ),
            [],
        )


class TribeNamingTests(unittest.TestCase):
    def _packet(self, packet_id: str, label: str) -> dict:
        return {
            "packet_id": packet_id,
            "strategy_id": f"tribe_{packet_id}",
            "geo_pin": {"neighborhood_label": label},
        }

    def test_conflict_phrase_detects_shared_persona_nouns(self) -> None:
        self.assertEqual(
            bg._tribe_name_conflict_phrase(
                "San Francisco Synth Pioneers",
                "San Francisco Analog Synth Pioneers",
            ),
            "synth pioneers",
        )
        self.assertIsNone(
            bg._tribe_name_conflict_phrase(
                "Civic Center Synth Patrons",
                "Chinatown Underground AI Creators",
            )
        )

    def test_duplicate_names_are_rewritten_to_distinct_archetypes(self) -> None:
        packets = [
            self._packet("core_high_affinity", "Civic Center"),
            self._packet("underground_arbitrage", "Chinatown"),
            self._packet("competitor_conquest", "Hayes Valley"),
        ]
        strategies = [
            {"tribe_name": "Civic Center Synth Pioneers"}
            for _ in packets
        ]
        bg._ensure_distinct_tribe_names(strategies, packets)
        names = [strategy["tribe_name"] for strategy in strategies]
        self.assertEqual(len(set(names)), 3)
        self.assertEqual(names[1], "Chinatown Underground Creators")
        self.assertEqual(names[2], "Hayes Valley Workday Switchers")

    def test_payload_includes_assigned_name_guidance(self) -> None:
        payload = bg._build_llm_payload(
            campaign={"brand_name": "Monolith One"},
            demographics={},
            packet=self._packet(
                "underground_arbitrage", "Chinatown"
            ),
            trending={},
        )
        guidance = payload["output_requirements"]["tribe_name_guidance"]
        self.assertEqual(
            guidance["assigned_archetype"],
            "Underground Subculture / Indie Creator",
        )
        self.assertEqual(guidance["neighborhood"], "Chinatown")
        self.assertIn(
            "Collector/Patron", guidance["other_tribe_archetypes"]
        )
        self.assertIn(
            "Workday Operator/Switcher",
            guidance["other_tribe_archetypes"],
        )

    def test_validation_flags_duplicate_names_across_packets(self) -> None:
        packet = {
            "packet_id": "core_high_affinity",
            "strategy_id": "tribe_1",
            "required_mentions": {
                "artists": [],
                "movies": [],
                "podcasts": [],
                "brands": [],
                "venues": [],
                "tags": [],
                "geo_label": None,
                "competitor": None,
            },
        }
        prompt = " ".join(["Specific creative direction."] * 30)
        prompt += (
            " Never use: unlock, elevate, journey, curated, authentic, "
            "crafted, indulge, savor."
        )
        strategy = {
            "id": "tribe_1",
            "tribe_name": "San Francisco Synth Pioneers",
            "strategic_angle": "One. Two.",
            "cultural_system_prompt": prompt,
        }
        _, errors, _ = bg._validate_strategies(
            {"strategies": [strategy, dict(strategy), dict(strategy)]},
            [packet, packet, packet],
        )
        self.assertEqual(set(errors), {0, 1, 2})
        self.assertTrue(
            all(
                any(
                    "reuses the noun phrase" in message
                    for message in messages
                )
                for messages in errors.values()
            )
        )


class MetaSpecTests(unittest.TestCase):
    def _packet(self) -> dict:
        return {
            "packet_id": "core_high_affinity",
            "strategy_id": "tribe_1",
            "product_context": {
                "brand_name": "Humo Santo",
                "product_description": "mezcal",
                "location_query": "Austin, TX",
            },
            "geo_pin": {
                "latitude": 30.26802,
                "longitude": -97.74742,
                "neighborhood_label": "Warehouse District",
            },
            "demographic_focus": {
                "age_min": 30,
                "age_max": 34,
                "genders": [2],
            },
        }

    def test_finalize_forces_paused_and_geo(self) -> None:
        strategy = {
            "meta_adset_spec": {
                "name": "Test",
                "status": "ACTIVE",
                "age_min": 10,
                "age_max": 80,
                "genders": ["all"],
                "geo_locations": {
                    "custom_locations": [
                        {"latitude": 1, "longitude": 2},
                        {"latitude": 3, "longitude": 4},
                    ]
                },
            }
        }
        spec = bg.finalize_meta_spec(strategy, self._packet(), 0)
        self.assertEqual(spec["status"], "PAUSED")
        self.assertEqual(spec["age_min"], 18)
        self.assertEqual(spec["age_max"], 65)
        self.assertEqual(spec["genders"], [1, 2])
        locations = spec["geo_locations"]["custom_locations"]
        self.assertEqual(len(locations), 1)
        self.assertEqual(locations[0]["radius"], 1.0)
        self.assertEqual(locations[0]["distance_unit"], "mile")

    def test_invalid_age_order_uses_recommendation(self) -> None:
        strategy = {
            "meta_adset_spec": {
                "age_min": 50,
                "age_max": 40,
                "genders": ["female"],
            }
        }
        spec = bg.finalize_meta_spec(strategy, self._packet(), 0)
        self.assertEqual(spec["age_min"], 30)
        self.assertEqual(spec["age_max"], 34)
        self.assertEqual(spec["genders"], [2])

    def test_meta_name_gets_brand_prefix(self) -> None:
        strategy = {
            "meta_adset_spec": {
                "name": "Warehouse District Soul Set",
            }
        }
        spec = bg.finalize_meta_spec(strategy, self._packet(), 0)
        self.assertEqual(
            spec["name"], "Humo Santo - Warehouse District Soul Set"
        )

    def test_meta_name_keeps_existing_brand_prefix(self) -> None:
        strategy = {
            "meta_adset_spec": {
                "name": "Humo Santo - Warehouse District Soul Set",
            }
        }
        spec = bg.finalize_meta_spec(strategy, self._packet(), 0)
        self.assertEqual(
            spec["name"], "Humo Santo - Warehouse District Soul Set"
        )

    def test_meta_name_is_deterministic_from_packet_and_tribe(self) -> None:
        spec = bg.finalize_meta_spec(
            {"meta_adset_spec": {}},
            self._packet(),
            0,
            tribe_name="Warehouse District Crate",
        )
        self.assertEqual(
            spec["name"],
            "Humo Santo | Warehouse District Crate | Austin, TX",
        )

    def test_finalize_strategy_adds_derived_fields(self) -> None:
        strategy = {
            "id": "tribe_1",
            "tribe_name": "Warehouse District Crate",
            "strategic_angle": "One. Two.",
            "cultural_system_prompt": (
                "Use Jungle and SAULT. Shoot at La Casa. The Standard. "
                "Sultry, Chill, Art House. Never use: unlock, elevate."
            ),
        }
        final = bg.finalize_strategy(strategy, self._packet(), 0)
        self.assertEqual(
            set(final),
            {
                "id",
                "tribe_name",
                "strategic_angle",
                "qloo_grounding_summary",
                "cultural_system_prompt",
                "meta_adset_spec",
            },
        )
        self.assertEqual(
            final["meta_adset_spec"]["name"],
            "Humo Santo | Warehouse District Crate | Austin, TX",
        )

    def test_finalize_strategy_scrubs_text(self) -> None:
        strategy = {
            "tribe_name": "Iconic Tribe",
            "strategic_angle": (
                "This is iconic. It has authentic vibes."
            ),
            "cultural_system_prompt": (
                "Use authentic details. Never use: authentic."
            ),
            "meta_adset_spec": {},
        }
        final = bg.finalize_strategy(strategy, self._packet(), 0)
        self.assertNotIn("iconic", final["tribe_name"].casefold())
        self.assertNotIn("iconic", final["strategic_angle"].casefold())
        self.assertNotIn(
            "authentic", final["strategic_angle"].casefold()
        )
        self.assertNotIn("vibes", final["strategic_angle"].casefold())
        self.assertIn(
            "Never use: authentic", final["cultural_system_prompt"]
        )
        self.assertNotIn(
            "authentic",
            final["cultural_system_prompt"].split("Never use")[0].casefold(),
        )


class StrategyGenerationTests(unittest.TestCase):
    def _packet(self, index: int) -> dict:
        return {
            "packet_id": "core_high_affinity",
            "strategy_id": f"tribe_{index + 1}",
            "required_mentions": {
                "artists": ["Jungle", "SAULT"],
                "movies": ["Roma"],
                "podcasts": ["Song Exploder"],
                "brands": ["The Standard"],
                "venues": ["La Casa"],
                "tags": ["Sultry", "Chill", "Art House"],
                "geo_label": "Warehouse District",
                "competitor": None,
            },
            "product_context": {
                "brand_name": "Humo Santo",
                "product_description": "mezcal",
                "location_query": "Austin, TX",
            },
            "geo_pin": {
                "latitude": 30.26802,
                "longitude": -97.74742,
                "neighborhood_label": "Warehouse District",
            },
            "demographic_focus": {
                "age_min": 30,
                "age_max": 34,
                "genders": [2],
            },
        }

    def _prompt(self) -> str:
        filler = (
            "Make the work specific to this packet and avoid generic "
            "choices."
        )
        base = (
            "Use Jungle and SAULT for the sonic palette. Use Roma for color "
            "grading. Shoot at La Casa in Warehouse District. The Standard "
            "is the brand reference. Cultural codes are Sultry, Chill, Art "
            "House. Never use: unlock, elevate, journey, curated, authentic, "
            "crafted, indulge, savor. "
        )
        return base + " ".join([filler] * 14)

    def _strategy(self, index: int, prompt: str | None = None) -> dict:
        names = [
            "Warehouse District Crate",
            "Warehouse District Archive",
            "Warehouse District Workshop",
        ]
        return {
            "id": f"tribe_{index + 1}",
            "tribe_name": names[index],
            "strategic_angle": "One. Two.",
            "cultural_system_prompt": prompt or self._prompt(),
        }

    def test_parallel_repair_is_isolated_to_failed_index(self) -> None:
        packets = [self._packet(index) for index in range(3)]
        barrier = threading.Barrier(3)
        repaired_ids: list[str] = []

        def fake_generate(index: int, messages: list[dict]) -> dict:
            barrier.wait(timeout=2)
            prompt = self._prompt()
            if index == 1:
                prompt = prompt.replace("Jungle", "Someone")
            return self._strategy(index, prompt)

        def fake_repair(
            messages: list[dict],
            first_response: dict,
            errors: list[str],
        ) -> dict:
            repaired_ids.append(first_response["id"])
            return self._strategy(1)

        with (
            patch.object(
                bg,
                "_staggered_complete_strategy",
                side_effect=fake_generate,
            ),
            patch.object(
                bg, "_repair_llm_strategy", side_effect=fake_repair
            ),
        ):
            events: list[dict] = []
            strategies, metadata = bg.generate_strategies(
                campaign={"brand_name": "Humo Santo"},
                demographics={},
                packets=packets,
                trending={},
                on_event=events.append,
            )

        self.assertEqual(repaired_ids, ["tribe_2"])
        self.assertEqual(
            [strategy["id"] for strategy in strategies],
            ["tribe_1", "tribe_2", "tribe_3"],
        )
        phases = [
            event.get("phase")
            for event in events
            if event["type"] == "phase_change"
        ]
        self.assertIn("strategy_generation", phases)
        self.assertIn("strategy_repair", phases)
        self.assertEqual(events[-1]["artifact"], "strategies")
        self.assertEqual(metadata["mode"], "llm")
        self.assertEqual(metadata["attempts"], 2)
        self.assertEqual(metadata["fallback_indices"], [])
        self.assertEqual(
            set(metadata["attempt_errors"][0]["errors"]), {1}
        )

    def test_strategy_calls_start_without_stagger(self) -> None:
        with (
            patch.object(bg.time, "sleep") as sleep,
            patch.object(bg, "_complete_strategy", return_value={}),
        ):
            bg._staggered_complete_strategy(2, [])
        sleep.assert_called_once_with(0.0)


class InputTests(unittest.TestCase):
    def test_json_and_pprint(self) -> None:
        self.assertEqual(
            bg._load_structured_input('{"a": 1}')["a"], 1
        )
        self.assertEqual(
            bg._load_structured_input("{'a': 1}")["a"], 1
        )
        self.assertIsNone(bg._load_structured_input("free text"))

    def test_location_only_brief_raises_clear_error(self) -> None:
        extracted = {
            "brand_name": None,
            "product_description": None,
            "seed_brands": [],
            "competitor_brands": [],
            "seed_tags": [],
            "location": "New York, NY",
            "location_query": "New York, NY",
            "neighborhood_hints": [],
            "raw_input": "New York, NY",
        }
        for brief in ("New York, NY", ""):
            with (
                self.subTest(brief=brief),
                patch.object(
                    bg, "extract_seed_signals", return_value=extracted
                ),
                self.assertRaisesRegex(
                    bg.GroundingInputError, "brand or product category"
                ),
            ):
                bg._resolve_input(
                    brief,
                    api_key="test",
                    location_override=None,
                )

    def test_build_campaign(self) -> None:
        resolved = {
            "brand_name": "Humo Santo",
            "resolved_entities": {
                "seed": [
                    {
                        "name": "Casamigos",
                        "entity_id": "seed-1",
                        "subtype": "urn:entity:brand",
                    }
                ],
                "competitors": [
                    {
                        "name": "Don Julio",
                        "entity_id": "comp-1",
                        "subtype": "urn:entity:brand",
                    }
                ],
            },
            "resolved_tags": [
                {
                    "query": "mezcal",
                    "tag_id": "urn:tag:cuisine:qloo:mezcal",
                    "name": "Mezcal",
                }
            ],
            "insights_tags": [
                "urn:tag:cuisine:qloo:mezcal",
                "urn:tag:interests:qloo:vinyl_records",
            ],
            "location_query": "Austin, TX",
            "raw_signals": {
                "brand_name": "Humo Santo",
                "product_description": "mezcal",
                "raw_input": "Brief",
            },
        }
        campaign = bg.build_campaign(resolved)
        self.assertEqual(campaign["location_query"], "Austin, TX")
        self.assertEqual(len(campaign["seed_entities"]), 1)
        self.assertEqual(campaign["seed_tags"][0]["name"], "Mezcal")
        self.assertTrue(
            any(
                tag["tag_id"] == "urn:tag:interests:qloo:vinyl_records"
                for tag in campaign["seed_tags"]
            )
        )

    def test_missing_location_raises(self) -> None:
        resolved = {
            "brand_name": "X",
            "resolved_entities": {
                "seed": [
                    {
                        "name": "Seed",
                        "entity_id": "s1",
                        "subtype": "urn:entity:brand",
                    }
                ],
                "competitors": [],
            },
            "raw_signals": {},
        }
        with self.assertRaises(bg.GroundingInputError):
            bg.build_campaign(resolved)

    def test_typographic_dashes_normalized(self) -> None:
        self.assertEqual(bg._clean_string("one—two"), "one - two")
        self.assertEqual(bg._clean_multiline("one—two"), "one - two")
        self.assertEqual(bg._clean_string("15–30"), "15-30")


class TagAssignmentTests(unittest.TestCase):
    def test_disjoint_tag_groups(self) -> None:
        discovered = [
            {
                "tag_id": f"urn:tag:style:qloo:t{index}",
                "name": f"Tag {index}",
                "subtype": "urn:tag:style:qloo",
                "source": "discovered",
            }
            for index in range(15)
        ]
        seeds = [
            {
                "tag_id": "urn:tag:cuisine:qloo:mezcal",
                "name": "Mezcal",
                "source": "seed",
            },
            {
                "tag_id": "urn:tag:interests:qloo:vinyl_records",
                "name": "Vinyl Records",
                "source": "seed",
            },
            {
                "tag_id": "urn:tag:good_for:qloo:poker_nights",
                "name": "Poker Nights",
                "source": "seed",
            },
        ]
        compare = {
            "a_only_tags": [
                {
                    "tag_id": "urn:tag:style:qloo:psychedelic",
                    "name": "Psychedelic",
                    "subtype": "urn:tag:style:qloo",
                }
            ]
        }
        groups = bg._assign_tags(discovered, seeds, compare)
        ids = [
            tag["tag_id"] for group in groups for tag in group
        ]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(
            any(tag["name"] == "Mezcal" for tag in groups[0])
        )
        self.assertTrue(
            any(tag["name"] == "Vinyl Records" for tag in groups[1])
        )
        self.assertTrue(
            any(tag["name"] == "Poker Nights" for tag in groups[2])
        )
        self.assertTrue(
            any(tag["name"] == "Psychedelic" for tag in groups[2])
        )

    def test_generic_meal_tags_filtered(self) -> None:
        raw = [
            {
                "tag_id": "urn:tag:good_for:qloo:dinner",
                "name": "Dinner",
                "subtype": "urn:tag:good_for:qloo",
                "query": {"affinity": 0.9},
            },
            {
                "tag_id": "urn:tag:interests:qloo:food_and_drink",
                "name": "Food & Drink",
                "subtype": "urn:tag:interests:qloo",
                "query": {"affinity": 0.85},
            },
            {
                "tag_id": "urn:tag:good_for:qloo:late_night_drinks",
                "name": "Late Night Drinks",
                "subtype": "urn:tag:good_for:qloo",
                "query": {"affinity": 0.8},
            },
        ]
        names = [tag["name"] for tag in bg.select_taste_tags(raw)]
        self.assertNotIn("Dinner", names)
        self.assertNotIn("Food & Drink", names)
        self.assertIn("Late Night Drinks", names)

    def test_movie_tone_and_audience_tags_filtered(self) -> None:
        raw = [
            {
                "tag_id": "urn:tag:style:qloo:campy",
                "name": "Campy",
                "subtype": "urn:tag:style:qloo",
                "query": {"affinity": 0.99},
            },
            {
                "tag_id": "urn:tag:audience:qloo:family",
                "name": "Family",
                "subtype": "urn:tag:audience:qloo",
                "query": {"affinity": 0.98},
            },
            {
                "tag_id": "urn:tag:audience:qloo:science_oriented",
                "name": "Science-Oriented",
                "subtype": "urn:tag:audience:qloo",
                "query": {"affinity": 0.97},
            },
            {
                "tag_id": "urn:tag:lifestyle:qloo:fitness",
                "name": "Fitness",
                "subtype": "urn:tag:lifestyle:qloo",
                "query": {"affinity": 0.96},
            },
            {
                "tag_id": "urn:tag:personal_style:qloo:athletic",
                "name": "Athletic",
                "subtype": "urn:tag:personal_style:qloo",
                "query": {"affinity": 0.95},
            },
        ]
        names = [tag["name"] for tag in bg.select_taste_tags(raw)]
        self.assertNotIn("Campy", names)
        self.assertNotIn("Family", names)
        self.assertNotIn("Science-Oriented", names)
        self.assertIn("Fitness", names)
        self.assertIn("Athletic", names)

    def test_cultural_tag_types_keep_interests_and_drop_style(self) -> None:
        self.assertNotIn("urn:tag:style:qloo", bg.CULTURAL_TAG_TYPES)
        self.assertIn("urn:tag:interests:qloo", bg.CULTURAL_TAG_TYPES)
        self.assertIn("urn:tag:hobby:qloo", bg.CULTURAL_TAG_TYPES)
        self.assertIn(
            "urn:tag:personal_style:qloo", bg.CULTURAL_TAG_TYPES
        )
        self.assertIn("urn:tag:audience:qloo", bg.CULTURAL_TAG_TYPES)


class CompetitorTests(unittest.TestCase):
    def test_named_competitor_falls_back_to_brief(self) -> None:
        campaign = {
            "competitor_entities": [],
            "raw_signals": {"competitor_brands": ["Ippodo Tea"]},
        }
        self.assertEqual(
            bg._named_competitor(campaign, None), "Ippodo Tea"
        )

    def test_named_competitor_prefers_compare(self) -> None:
        campaign = {
            "competitor_entities": [{"name": "Don Julio"}],
            "raw_signals": {"competitor_brands": ["Other"]},
        }
        compare = {"competitor_name": "Don Julio"}
        self.assertEqual(
            bg._named_competitor(campaign, compare), "Don Julio"
        )

    def test_grounding_summary_names_unresolved_competitor(self) -> None:
        packet = {
            "packet_id": "competitor_conquest",
            "geo_pin": {
                "neighborhood_label": "Theater District",
                "latitude": 40.759277,
                "longitude": -73.98193,
                "affinity": 0.998,
            },
            "venues": [],
            "artists": [],
            "movies": [],
            "podcasts": [],
            "brands": [],
            "taste_tags": [],
            "demographic_focus": {},
            "competitor": "Ippodo Tea",
            "compare": None,
        }
        summary = bg.grounding_summary(packet)
        self.assertIn("Ippodo Tea", summary)
        self.assertIn("no compare deltas", summary)

    def test_build_packets_carries_named_competitor(self) -> None:
        campaign = {
            "brand_name": "Chaen",
            "product_description": "matcha",
            "location_query": "New York, NY",
            "seed_entities": [],
            "competitor_entities": [],
            "raw_signals": {"competitor_brands": ["Ippodo Tea"]},
        }
        demographics = {
            "recommended_age_ranges": {},
            "recommended_genders": {},
            "aggregate_age_lifts": {},
            "aggregate_gender_lifts": {},
            "artist_seed_blocks": [],
            "excluded_cohorts": [],
        }
        packets = bg.build_packets(
            campaign=campaign,
            demographics=demographics,
            artists=[],
            movies=[],
            podcasts=[],
            brands=[],
            taste_tags=[],
            seed_tags=[],
            pins=[],
            venues_by_pin=[],
            compare=None,
        )
        self.assertIsNone(packets[0]["competitor"])
        self.assertEqual(packets[2]["competitor"], "Ippodo Tea")
        self.assertEqual(
            packets[2]["required_mentions"]["competitor"], "Ippodo Tea"
        )
        self.assertIn("Ippodo Tea", bg.grounding_summary(packets[2]))


class FetchFallbackTests(unittest.TestCase):
    def _note(
        self, name: str, params: dict, status: str = "empty"
    ) -> dict:
        return {"name": name, "path": "/v2/insights", "params": params, "status": status}

    def test_entities_retry_without_tags_then_city(self) -> None:
        calls: list[tuple[str, dict]] = []
        entity = {"entity_id": "urn:entity:artist:1", "name": "Artist"}

        def fake_call(client, path, params, *, name):
            calls.append((name, dict(params)))
            if name == "artists":
                return None, self._note(name, params)
            if name == "artists_without_tags":
                return None, self._note(name, params)
            if name == "artists_city_only":
                return (
                    {"results": {"entities": [entity]}},
                    self._note(name, params, "ok"),
                )
            raise AssertionError(f"unexpected call: {name}")

        params = {
            "filter.type": "urn:entity:artist",
            "signal.location.query": "London, UK",
            "signal.interests.tags": "urn:tag:music:qloo:ambient",
        }
        with patch.object(bg, "_call_qloo", side_effect=fake_call):
            entities, notes = bg._fetch_entities_with_fallback(
                None, name="artists", params=params
            )

        self.assertEqual(entities, [entity])
        self.assertTrue(notes[-1]["fallback_used"])
        self.assertEqual(
            [name for name, _ in calls],
            ["artists", "artists_without_tags", "artists_city_only"],
        )
        self.assertNotIn("signal.interests.tags", calls[1][1])
        self.assertEqual(calls[1][1]["signal.location.query"], "London, UK")
        self.assertEqual(calls[2][1]["signal.location.query"], "London")
        self.assertNotIn("signal.interests.tags", calls[2][1])

    def test_place_query_falls_back_to_city_only(self) -> None:
        calls: list[tuple[str, dict]] = []
        place = {"entity_id": "urn:entity:place:1", "name": "Gallery"}

        def fake_call(client, path, params, *, name):
            calls.append((name, dict(params)))
            if name == "places":
                return None, self._note(name, params)
            if name == "places_without_tags":
                return None, self._note(name, params)
            if name == "places_city_only":
                return (
                    {"results": {"entities": [place]}},
                    self._note(name, params, "ok"),
                )
            raise AssertionError(f"unexpected call: {name}")

        params = {
            "filter.type": "urn:entity:place",
            "filter.location.query": "London, UK",
            "signal.interests.tags": "urn:tag:interests:qloo:art",
        }
        with patch.object(bg, "_call_qloo", side_effect=fake_call):
            entities, notes = bg._fetch_entities_with_fallback(
                None, name="places", params=params
            )

        self.assertEqual(entities, [place])
        self.assertTrue(notes[-1]["fallback_used"])
        self.assertEqual(calls[2][1]["filter.location.query"], "London")
        self.assertNotIn("signal.interests.tags", calls[2][1])

    def test_entities_without_tags_skip_tag_retry(self) -> None:
        calls: list[tuple[str, dict]] = []

        def fake_call(client, path, params, *, name):
            calls.append((name, dict(params)))
            if name == "brands":
                return None, self._note(name, params)
            if name == "brands_city_only":
                return (
                    {"results": {"entities": [{"entity_id": "urn:entity:brand:1", "name": "Brand"}]}},
                    self._note(name, params, "ok"),
                )
            raise AssertionError(f"unexpected call: {name}")

        params = {
            "filter.type": "urn:entity:brand",
            "filter.location.query": "London, UK",
        }
        with patch.object(bg, "_call_qloo", side_effect=fake_call):
            entities, _ = bg._fetch_entities_with_fallback(
                None, name="brands", params=params
            )

        self.assertEqual(len(entities), 1)
        self.assertEqual(
            [name for name, _ in calls], ["brands", "brands_city_only"]
        )

    def test_heatmap_query_falls_back_to_city_only(self) -> None:
        calls: list[tuple[str, dict]] = []

        def fake_call(client, path, params, *, name):
            calls.append((name, dict(params)))
            if name == "heatmap":
                return None, self._note(name, params)
            if name == "heatmap_city_only":
                return (
                    {
                        "results": {
                            "heatmap": [
                                {
                                    "location": {
                                        "latitude": 51.5,
                                        "longitude": -0.1,
                                    },
                                    "query": {"affinity": 0.9},
                                }
                            ]
                        }
                    },
                    self._note(name, params, "ok"),
                )
            raise AssertionError(f"unexpected call: {name}")

        params = {
            "filter.type": "urn:heatmap",
            "filter.location.query": "London, UK",
            "signal.interests.entities": "urn:entity:brand:1",
        }
        with patch.object(bg, "_call_qloo", side_effect=fake_call):
            payload, notes = bg._fetch_heatmap_with_fallback(None, params)

        self.assertTrue(bg._heatmap_from(payload))
        self.assertTrue(notes[-1]["fallback_used"])
        self.assertEqual(
            [name for name, _ in calls],
            ["heatmap", "heatmap_city_only"],
        )
        self.assertEqual(calls[1][1]["filter.location.query"], "London")
        self.assertEqual(
            calls[1][1]["signal.interests.entities"],
            "urn:entity:brand:1",
        )

    def test_city_only_location_requires_a_qualifier(self) -> None:
        self.assertEqual(
            bg._city_only_location_query("London, UK"), "London"
        )
        self.assertEqual(
            bg._city_only_location_query("New York, NY"), "New York"
        )
        self.assertIsNone(bg._city_only_location_query("London"))
        self.assertIsNone(bg._city_only_location_query(None))


class FallbackTests(unittest.TestCase):
    def test_fallback_prompt_is_in_range(self) -> None:
        packet = {
            "packet_id": "core_high_affinity",
            "label": "The Core Insider Lock",
            "strategy_id": "tribe_1",
            "product_context": {
                "brand_name": "Humo Santo",
                "product_description": "mezcal",
                "location_query": "Austin, TX",
            },
            "geo_pin": {
                "latitude": 30.26802,
                "longitude": -97.74742,
                "neighborhood_label": "Warehouse District",
            },
            "venues": [{"name": "La Casa", "affinity": 0.8}],
            "artists": [
                {"name": "Jungle", "affinity": 0.8},
                {"name": "SAULT", "affinity": 0.8},
            ],
            "movies": [{"name": "Roma", "affinity": 0.8}],
            "podcasts": [{"name": "Song Exploder", "affinity": 0.8}],
            "brands": [{"name": "The Standard", "affinity": 0.8}],
            "taste_tags": [
                {"name": "Sultry"},
                {"name": "Chill"},
                {"name": "Art House"},
            ],
            "demographic_focus": {
                "age_min": 30,
                "age_max": 34,
                "genders": [2],
            },
            "compare": None,
        }
        prompt = bg._fallback_prompt(packet)
        words = bg._word_count(prompt)
        self.assertGreaterEqual(words, bg.PROMPT_VALID_MIN_WORDS)
        self.assertLessEqual(words, bg.PROMPT_VALID_MAX_WORDS)
        scrubbed = bg.scrub_banned_phrases(prompt)
        self.assertEqual(
            bg._banned_phrases_outside_clause(scrubbed), []
        )
        for name in (
            "Jungle",
            "SAULT",
            "Roma",
            "La Casa",
            "The Standard",
            "Sultry",
        ):
            self.assertIn(name, prompt)
        self.assertEqual(
            bg._banned_phrases_outside_clause(prompt), []
        )


class EventHookTests(unittest.TestCase):
    def test_emit_swallows_callback_errors(self) -> None:
        def broken_callback(event: dict) -> None:
            raise RuntimeError("callback boom")

        bg._emit(broken_callback, "phase_change", phase="candidate_search")

    def test_call_qloo_emits_running_and_ok(self) -> None:
        class FakeClient:
            def get(self, path: str, params: dict) -> dict:
                return {"results": {"entities": []}}

        events: list[dict] = []
        payload, note = bg._call_qloo(
            FakeClient(),
            bg.QLOO_INSIGHTS_PATH,
            {"filter.type": "urn:entity:artist"},
            name="artists",
            on_event=events.append,
        )

        self.assertIsNotNone(payload)
        self.assertEqual(note["status"], "ok")
        self.assertEqual(
            [event["status"] for event in events],
            ["running", "ok"],
        )
        self.assertEqual(events[0]["name"], "artists")
        self.assertIn("duration_ms", events[1])
        self.assertIsInstance(events[0]["timestamp"], float)

    def test_call_qloo_emits_error(self) -> None:
        class FailingClient:
            def get(self, path: str, params: dict) -> dict:
                raise bg.QlooResolutionError("upstream failed")

        events: list[dict] = []
        payload, note = bg._call_qloo(
            FailingClient(),
            bg.QLOO_INSIGHTS_PATH,
            {},
            name="heatmap",
            on_event=events.append,
        )

        self.assertIsNone(payload)
        self.assertEqual(note["status"], "error")
        self.assertEqual(
            [event["status"] for event in events],
            ["running", "error"],
        )

    def test_generic_tag_names_include_new_quality_filters(self) -> None:
        self.assertIn("horse riding", bg._GENERIC_TAG_NAMES)
        self.assertIn("analysis", bg._GENERIC_TAG_NAMES)


if __name__ == "__main__":
    unittest.main()
