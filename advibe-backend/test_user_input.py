import unittest
from unittest.mock import patch

import user_input as ui


class NormalizationTests(unittest.TestCase):
    def test_owned_brand_is_also_a_seed(self) -> None:
        result = ui._normalize_payload(
            {
                "brand_name": "Jungsik",
                "product_description": "new line of makgeolli",
                "seed_brands": ["Momofuku"],
                "competitor_brands": ["Chamisul"],
                "seed_tags": ["makgeolli", "luxury"],
            },
            "i own Jungsik in NYC, i want an ad for new line of makgeolli",
        )

        self.assertEqual(result["seed_brands"][0], "Jungsik")
        self.assertIn("Momofuku", result["seed_brands"])
        self.assertEqual(result["competitor_brands"], ["Chamisul"])

    def test_new_brand_is_not_forced_into_seeds(self) -> None:
        result = ui._normalize_payload(
            {
                "brand_name": "Chaen",
                "product_description": "canned matcha",
                "seed_brands": ["Erewhon", "Chaen"],
                "competitor_brands": [],
                "seed_tags": ["matcha"],
            },
            "my new matcha brand Chaen in New York",
        )

        self.assertNotIn("Chaen", result["seed_brands"])
        self.assertIn("Erewhon", result["seed_brands"])

    def test_competitor_wins_strict_no_overlap(self) -> None:
        result = ui._normalize_payload(
            {
                "brand_name": "Jungsik",
                "seed_brands": ["Dom Pérignon"],
                "competitor_brands": ["Dom Pérignon", "Chamisul"],
            },
            "i own Jungsik",
        )

        self.assertNotIn("Dom Pérignon", result["seed_brands"])
        self.assertEqual(
            result["competitor_brands"], ["Dom Pérignon", "Chamisul"]
        )
        self.assertIn("Jungsik", result["seed_brands"])

    def test_canonical_tags_are_added(self) -> None:
        result = ui._normalize_payload(
            {
                "brand_name": "Jungsik",
                "product_description": "new line of makgeolli",
                "seed_brands": ["Jungsik"],
                "competitor_brands": [],
                "seed_tags": ["makgeolli", "luxury", "agave spirits"],
            },
            "i own Jungsik, high luxury makgeolli",
        )

        self.assertIn("korean", result["seed_tags"])
        self.assertIn("rice wine", result["seed_tags"])
        self.assertIn("sake", result["seed_tags"])
        self.assertNotIn("agave spirits", result["seed_tags"])

    def test_owned_brand_detection(self) -> None:
        self.assertTrue(ui._is_owned_brand("i own Jungsik in NYC", "Jungsik"))
        self.assertTrue(
            ui._is_owned_brand("my restaurant Jungsik is in NYC", "Jungsik")
        )
        self.assertFalse(
            ui._is_owned_brand(
                "i own a new brand called Chaen", "Chaen"
            )
        )
        self.assertFalse(
            ui._is_owned_brand("my new matcha brand Chaen", "Chaen")
        )


class ExtractionTests(unittest.TestCase):
    def test_sparse_brief_enriches_seeds_and_competitors(self) -> None:
        initial = {
            "brand_name": "Jungsik",
            "product_description": "new line of makgeolli",
            "seed_brands": [],
            "competitor_brands": [],
            "seed_tags": ["makgeolli", "luxury"],
            "location": "NYC",
            "location_query": "New York, NY",
            "neighborhood_hints": [],
        }
        enrichment = {
            "seed_brands": [
                "Momofuku",
                "Dom Pérignon",
                "Aesop",
                "Ryuichi Sakamoto",
            ],
            "competitor_brands": ["Chamisul", "Veuve Clicquot"],
        }

        with patch(
            "user_input.complete_json", side_effect=[initial, enrichment]
        ):
            result = ui.extract_seed_signals(
                "i own Jungsik in NYC, i want an ad for new line of "
                "makgeolli we're launching, its in the high luxury"
            )

        self.assertIn("Jungsik", result["seed_brands"])
        self.assertIn("Momofuku", result["seed_brands"])
        self.assertEqual(len(result["seed_brands"]), 5)
        self.assertEqual(
            result["competitor_brands"],
            ["Chamisul", "Veuve Clicquot"],
        )
        self.assertFalse(
            set(result["seed_brands"]) & set(result["competitor_brands"])
        )

    def test_multiple_explicit_seeds_disable_inference(self) -> None:
        explicit = ["On Running", "Soho Beach House", "Rüfüs Du Sol"]
        initial = {
            "brand_name": "Salina Club",
            "product_description": "marine-mineral electrolyte aperitif",
            "explicit_seed_brands": explicit,
            "seed_brands": [*explicit, "Patagonia", "Aesop"],
            "competitor_brands": ["Gatorade", "Nuun"],
            "seed_tags": ["electrolyte", "aperitif", "running"],
            "location": "Miami, Florida",
            "location_query": "Miami, FL",
            "neighborhood_hints": [],
        }

        with patch(
            "user_input.complete_json", side_effect=[initial]
        ) as complete:
            result = ui.extract_seed_signals(
                "We are launching Salina Club in Miami, Florida. "
                "Inspired by On Running, Soho Beach House, and Rüfüs Du Sol."
            )

        self.assertEqual(result["explicit_seed_brands"], explicit)
        self.assertEqual(result["seed_brands"], explicit)
        self.assertEqual(complete.call_count, 1)

    def test_two_explicit_seeds_disable_inference(self) -> None:
        explicit = ["On Running", "Soho Beach House"]
        initial = {
            "brand_name": "Salina Club",
            "product_description": "marine-mineral electrolyte aperitif",
            "explicit_seed_brands": explicit,
            "seed_brands": [*explicit, "Patagonia", "Aesop"],
            "competitor_brands": ["Gatorade"],
            "seed_tags": ["electrolyte", "aperitif", "running"],
            "location": "Miami, Florida",
            "location_query": "Miami, FL",
            "neighborhood_hints": [],
        }

        with patch(
            "user_input.complete_json", side_effect=[initial]
        ) as complete:
            result = ui.extract_seed_signals(
                "A Miami electrolyte drink inspired by On Running and "
                "Soho Beach House."
            )

        self.assertEqual(result["seed_brands"], explicit)
        self.assertEqual(complete.call_count, 1)

    def test_one_explicit_seed_still_enriches(self) -> None:
        initial = {
            "brand_name": "Jungsik",
            "product_description": "new line of makgeolli",
            "explicit_seed_brands": ["Jungsik"],
            "seed_brands": ["Jungsik"],
            "competitor_brands": ["Chamisul"],
            "seed_tags": ["makgeolli", "luxury"],
            "location": "NYC",
            "location_query": "New York, NY",
            "neighborhood_hints": [],
        }
        enrichment = {
            "seed_brands": [
                "Jungsik",
                "Momofuku",
                "Aesop",
                "Ryuichi Sakamoto",
            ],
            "competitor_brands": ["Chamisul"],
        }

        with patch(
            "user_input.complete_json", side_effect=[initial, enrichment]
        ):
            result = ui.extract_seed_signals(
                "i own Jungsik in NYC, i want an ad for new line of "
                "makgeolli we're launching, its in the high luxury"
            )

        self.assertEqual(result["seed_brands"][0], "Jungsik")
        self.assertEqual(len(result["seed_brands"]), 4)
        self.assertIn("Momofuku", result["seed_brands"])

    def test_explicit_seed_order_is_preserved(self) -> None:
        explicit = ["Soho Beach House", "On Running", "Rüfüs Du Sol"]
        initial = {
            "brand_name": "Salina Club",
            "product_description": "marine-mineral electrolyte aperitif",
            "explicit_seed_brands": explicit,
            "seed_brands": ["On Running", "Patagonia", *explicit],
            "competitor_brands": ["Gatorade"],
            "seed_tags": ["electrolyte"],
            "location": "Miami, Florida",
            "location_query": "Miami, FL",
            "neighborhood_hints": [],
        }

        with patch(
            "user_input.complete_json", side_effect=[initial]
        ):
            result = ui.extract_seed_signals(
                "A Miami electrolyte drink inspired by Soho Beach House, "
                "On Running, and Rüfüs Du Sol."
            )

        self.assertEqual(result["seed_brands"], explicit)

    def test_specific_venue_name_is_preserved(self) -> None:
        result = ui._normalize_payload(
            {
                "brand_name": "Salina Club",
                "product_description": "electrolyte aperitif",
                "explicit_seed_brands": ["Soho Beach House"],
                "seed_brands": ["Soho Beach House"],
                "competitor_brands": [],
                "seed_tags": ["electrolyte"],
            },
            "Salina Club is inspired by Soho Beach House.",
        )

        self.assertEqual(result["seed_brands"], ["Soho Beach House"])

    def test_overlapping_competitors_trigger_seed_refill(self) -> None:
        initial = {
            "brand_name": "Jungsik",
            "product_description": "high luxury makgeolli",
            "seed_brands": [
                "Jungsik",
                "Chamisul",
                "Veuve Clicquot",
                "Blue Bottle Coffee",
                "A24",
            ],
            "competitor_brands": ["Chamisul", "Veuve Clicquot"],
            "seed_tags": [
                "makgeolli",
                "korean",
                "luxury",
                "fine dining",
                "rice wine",
            ],
            "location": "NYC",
            "location_query": "New York, NY",
        }
        enrichment = {
            "seed_brands": [
                "Jungsik",
                "Blue Bottle Coffee",
                "A24",
                "Momofuku",
                "Ryuichi Sakamoto",
            ],
            "competitor_brands": ["Chamisul", "Veuve Clicquot"],
        }

        with patch(
            "user_input.complete_json", side_effect=[initial, enrichment]
        ):
            result = ui.extract_seed_signals(
                "i own Jungsik in NYC, i want an ad for new line of "
                "makgeolli we're launching, its in the high luxury"
            )

        self.assertEqual(
            result["competitor_brands"], ["Chamisul", "Veuve Clicquot"]
        )
        self.assertEqual(len(result["seed_brands"]), 5)
        self.assertIn("Momofuku", result["seed_brands"])
        self.assertIn("Ryuichi Sakamoto", result["seed_brands"])
        self.assertFalse(
            set(result["seed_brands"]) & set(result["competitor_brands"])
        )

    def test_explicit_competitor_is_preserved(self) -> None:
        initial = {
            "brand_name": "Humo Santo",
            "product_description": "artisanal mezcal",
            "seed_brands": ["Casamigos", "Soho House", "Khruangbin"],
            "competitor_brands": ["Don Julio"],
            "seed_tags": ["mezcal", "tech culture", "poker nights"],
        }
        enrichment = {
            "seed_brands": [
                "Casamigos",
                "Soho House",
                "Khruangbin",
                "A24",
                "Ryuichi Sakamoto",
            ],
            "competitor_brands": ["Wrong Brand"],
        }

        with patch(
            "user_input.complete_json", side_effect=[initial, enrichment]
        ):
            result = ui.extract_seed_signals(
                "An Austin mezcal brand compared against Don Julio."
            )

        self.assertEqual(result["competitor_brands"], ["Don Julio"])
        self.assertIn("A24", result["seed_brands"])

    def test_empty_input_stays_empty_without_llm(self) -> None:
        with patch(
            "user_input.complete_json",
            side_effect=AssertionError("LLM should not be called"),
        ):
            result = ui.extract_seed_signals("")

        self.assertEqual(result["seed_brands"], [])
        self.assertEqual(result["competitor_brands"], [])
        self.assertEqual(result["seed_tags"], [])


if __name__ == "__main__":
    unittest.main()
