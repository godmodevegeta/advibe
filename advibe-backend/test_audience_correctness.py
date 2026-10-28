"""Regression tests for incomplete and mixed-domain Qloo audience evidence."""

import unittest
import build_grounding as bg


class AudienceCorrectnessTests(unittest.TestCase):
    def test_partial_coverage_and_missing_cohorts_are_not_zero(self):
        seeds = [
            {"entity_id": "venue", "name": "Coffee", "subtype": "urn:entity:place"},
            {"entity_id": "brand", "name": "Erewhon", "subtype": "urn:entity:brand"},
        ]
        result = bg.parse_demographics(
            {
                "results": {
                    "demographics": [
                        {
                            "entity_id": "brand",
                            "query": {
                                "age": {"25_to_29": 0.4},
                                "gender": {"female": 0.6},
                            },
                        },
                        {
                            "entity_id": "urn:tag:lifestyle:qloo:wellness",
                            "query": {"age": {"25_to_29": -0.8}},
                        },
                    ]
                }
            },
            seeds,
        )
        self.assertEqual(result["coverage"]["returned"], 1)
        self.assertEqual(result["coverage"]["missing_seeds"], [seeds[0]])
        self.assertEqual(result["aggregate_age"]["25_to_29"], 0.4)
        self.assertIsNone(result["aggregate_age"]["30_to_34"])
        self.assertEqual(len(result["tag_blocks"]), 1)
        self.assertEqual(result["scope"], "global")

    def test_mean_uses_only_observed_values(self):
        self.assertEqual(
            bg._mean_lifts([{"age": {"x": 0.6}}, {"age": {}}], "age", ["x"]), {"x": 0.6}
        )

    def test_zero_affinity_survives_and_compare_score_is_not_affinity(self):
        self.assertEqual(
            bg._normalize_tag(
                {"tag_id": "urn:tag:test:x", "name": "X", "query": {"affinity": 0}},
                "discovered",
            )["affinity"],
            0,
        )
        self.assertIsNone(
            bg._normalize_tag(
                {"tag_id": "urn:tag:test:x", "name": "X", "query": {"score": 0.9}},
                "compare",
            )["affinity"]
        )

    def test_compare_retains_category_evidence_with_mixed_domain_warning(self):
        campaign = {
            "seed_entities": [{"name": "Cafe", "subtype": "urn:entity:place"}],
            "competitor_entities": [{"name": "Energy", "subtype": "urn:entity:brand"}],
        }
        result = bg.parse_compare(
            {
                "results": {
                    "a": [],
                    "b": [
                        {
                            "tag_id": "urn:tag:genre:brand:energy_drink",
                            "name": "Energy Drink",
                        }
                    ],
                }
            },
            campaign,
        )
        self.assertTrue(result["mixed_entity_types"])
        self.assertEqual(result["all_b_only_tags"][0]["name"], "Energy Drink")
        self.assertEqual(result["method"], "descriptive_tag_overlap")
