"""Creative validation, variant identity, retry, and network-free Meta staging."""

import copy
import json
import unittest
import threading
from unittest.mock import patch
import generate_creatives as gc
import meta_campaign as mc
import creative_execution as ce
import stream_harness as sh


def grounding(cities=1, independent=False):
    local = []
    for city in range(1, cities + 1):
        strategies, packets = [], []
        for tribe in range(1, 4):
            sid = f"tribe_{tribe}"
            pin = {
                "latitude": 51.5 + tribe * 0.01,
                "longitude": -0.1,
                "radius": 1.0,
                "distance_unit": "mile",
            }
            packet = {
                "packet_id": f"packet_{tribe}",
                "strategy_id": sid,
                "product_context": {
                    "brand_name": "Nocturne",
                    "product_description": "Hinoki perfume oil",
                    "location_query": f"City {city}",
                },
                "artists": [{"entity_id": "artist", "name": "Kelela"}],
                "movies": [{"entity_id": "movie", "name": "Moonlight"}],
                "venues": [{"entity_id": "venue", "name": "Engawa"}],
                "brands": [],
                "taste_tags": [],
            }
            packets.append(packet)
            strategies.append(
                {
                    "id": sid,
                    "tribe_name": f"Tribe {tribe}",
                    "cultural_system_prompt": "Execute this culturally grounded brief.",
                    "location_id": f"city_{city}",
                    "location_query": f"City {city}",
                    "packet": packet,
                    "meta_adset_spec": {
                        "name": sid,
                        "status": "PAUSED",
                        "age_min": 25,
                        "age_max": 44,
                        "genders": [1, 2],
                        "geo_locations": {"custom_locations": [pin]},
                    },
                }
            )
        local.append(strategies)
    if cities == 1:
        strategies = local[0]
    elif independent:
        strategies = [
            {**s, "id": f"{s['location_id']}:{s['id']}"}
            for group in local
            for s in group
        ]
    else:
        strategies = [
            {
                "id": f"tribe_{i+1}",
                "tribe_name": f"Parent {i+1}",
                "location_variants": [group[i] for group in local],
            }
            for i in range(3)
        ]
    return {
        "brand_name": "Nocturne",
        "location_query": "; ".join(f"City {i+1}" for i in range(cities)),
        "strategies": strategies,
        "packets": packets,
    }


def valid_copy():
    return {
        "meta_ad": {
            "primary_text": " ".join(
                [
                    "Find your evening rhythm near Engawa with a scent worn close to the skin."
                ]
                * 5
            ),
            "headline": "A quieter rhythm for your evening",
            "description": "An intimate perfume oil for the hours ahead",
            "call_to_action": "SHOP_NOW",
        },
        "creative_hooks": [
            {
                "angle": f"Angle {i}",
                "hook_text": f"Opening line {i}",
                "qloo_anchor": "Kelela",
                "qloo_id": "artist",
            }
            for i in range(3)
        ],
        "reel_script_15s": {
            "sonic_direction": "Use Kelela as a pacing reference, subject to licensing.",
            "visual_direction": "Use Moonlight as a lighting reference.",
            "shots": [
                {
                    "window": w,
                    "visual": "Close detail of the bottle.",
                    "audio_or_vo": "A restrained pulse.",
                    "on_screen_text": "Nocturne",
                }
                for w in ("0-3s Hook", "3-10s Hold", "10-15s CTA")
            ],
        },
        "ooh_concept": {
            "venue_anchors": ["Engawa"],
            "placement_format": "Proposed venue table card",
            "poster_headline": "Your evening, closer",
            "visual_brief": "Typographic contrast; placement subject to permission.",
        },
        "editorial_palette": {
            "background_hex": "#101010",
            "text_hex": "#ffffff",
            "accent_hex": "#3080ff",
            "mood_label": "Moonlit contrast",
        },
        "creative_hypothesis": "A quiet neighborhood cue may resonate with this cultural cohort.",
    }


SETTINGS = {
    "objective": "OUTCOME_TRAFFIC",
    "currency": "USD",
    "daily_budget_cents_per_adset": 5000,
}


class CreativeTests(unittest.TestCase):
    def test_selection_and_city_variant_counts(self):
        self.assertEqual(len(gc.normalize_selection(grounding(3), ["tribe_1"])), 3)
        self.assertEqual(len(gc.normalize_selection(grounding(3))), 9)
        self.assertEqual(len(gc.normalize_selection(grounding(3, True))), 9)
        for ids in ([], ["bad"]):
            with self.assertRaises(ValueError):
                gc.normalize_selection(grounding(), ids)
        old = grounding()
        old["_packets"] = old.pop("packets")
        for s in old["strategies"]:
            s.pop("packet")
        self.assertEqual(len(gc.normalize_selection(old)), 3)

    def test_validation_rejects_wrong_anchors_word_limits_palette_and_beats(self):
        variant = gc.normalize_selection(grounding())[0]
        for mutate in (
            lambda d: d["creative_hooks"][0].update(qloo_id="invented"),
            lambda d: d["meta_ad"].update(headline="Two words"),
            lambda d: d["meta_ad"].update(
                primary_text=valid_copy()["meta_ad"]["primary_text"].rstrip(".")
            ),
            lambda d: d["creative_hooks"][0].update(
                hook_text="Enjoy Nocturne at Engawa"
            ),
            lambda d: d["meta_ad"].update(
                description="Supported by Kelela and available at Engawa"
            ),
            lambda d: d["editorial_palette"].update(text_hex="#121212"),
            lambda d: d["editorial_palette"].update(accent_hex="url(evil)"),
            lambda d: d["ooh_concept"].update(venue_anchors=["Imaginary place"]),
            lambda d: d["reel_script_15s"]["shots"][0].update(window="3-10s Hold"),
        ):
            data = valid_copy()
            mutate(data)
            with self.assertRaises(ValueError):
                gc.validate_creative(data, variant)
        self.assertEqual(
            gc.validate_creative(valid_copy(), variant)["creative_hooks"][0][
                "qloo_anchor"
            ],
            "Kelela",
        )

    def test_semantic_repair_and_exhaustion(self):
        bad = valid_copy()
        bad["meta_ad"]["headline"] = "Too short"
        variant = gc.normalize_selection(grounding())[0]
        with patch.object(gc, "complete_json", side_effect=[bad, valid_copy()]) as llm:
            self.assertEqual(
                gc._generate_one(variant, None)["creative_hypothesis"],
                valid_copy()["creative_hypothesis"],
            )
            self.assertEqual(llm.call_count, 2)
        with patch.object(gc, "complete_json", return_value=bad):
            with self.assertRaises(ValueError):
                gc._generate_one(variant, None)

    def test_partial_retry_preserves_success_and_does_not_stage_partial_coverage(self):
        def generate(v, callback):
            if v["variant_id"].endswith("tribe_2"):
                raise ValueError("Invalid creative")
            return valid_copy()

        with patch.object(gc, "_generate_one", side_effect=generate):
            first = ce.execute_creatives(grounding(), ["tribe_1", "tribe_2"], SETTINGS)
        self.assertEqual(first["status"], "partial")
        self.assertIsNone(first["meta"])
        self.assertEqual(len(first["creatives"]["bundles"]), 1)
        creative_id = first["creatives"]["bundles"][0]["creative_id"]
        with patch.object(gc, "_generate_one", return_value=valid_copy()) as llm:
            retry = ce.execute_creatives(
                grounding(), ["tribe_1", "tribe_2"], SETTINGS, previous_result=first
            )
        self.assertEqual(llm.call_count, 1)
        self.assertEqual(retry["status"], "complete")
        self.assertEqual(retry["creatives"]["bundles"][0]["creative_id"], creative_id)
        with self.assertRaises(ValueError):
            ce.execute_creatives(
                grounding(), ["tribe_1"], SETTINGS, previous_result=first
            )

    def test_multi_city_identity_and_deterministic_staging(self):
        with patch.object(gc, "_generate_one", return_value=valid_copy()):
            result = ce.execute_creatives(grounding(3), ["tribe_1"], SETTINGS)
        meta = result["meta"]
        self.assertEqual(len(meta["adsets"]), 3)
        self.assertEqual(
            len({b["variant_id"] for b in result["creatives"]["bundles"]}), 3
        )
        self.assertEqual(meta["daily_budget_total_minor_units"], 15000)
        self.assertEqual(
            meta,
            mc.stage_or_deploy_meta_campaign(
                grounding(3), result["creatives"], campaign_settings=SETTINGS
            ),
        )
        for adset in meta["adsets"]:
            self.assertEqual(adset["payload"]["status"], "PAUSED")
            self.assertIn("targeting_automation", adset["payload"]["targeting"])
            self.assertNotIn("age_min", adset["payload"])
        self.assertNotIn("status", meta["adcreatives"][0]["payload"])
        self.assertTrue(
            all(
                line.startswith("#") or not line
                for line in meta["curl_script"].splitlines()
            )
        )

    def test_sales_overlap_and_no_network_even_with_credentials(self):
        with patch.object(gc, "_generate_one", return_value=valid_copy()), patch(
            "urllib.request.urlopen", side_effect=AssertionError("Network forbidden")
        ), patch.dict(
            "os.environ", {"META_ACCESS_TOKEN": "secret", "META_AD_ACCOUNT_ID": "123"}
        ):
            result = ce.execute_creatives(
                grounding(), None, {**SETTINGS, "objective": "OUTCOME_SALES"}
            )
            self.assertEqual(result["status"], "complete")
            self.assertTrue(result["meta"]["warnings"])
            self.assertEqual(
                result["meta"]["adsets"][0]["payload"]["optimization_goal"],
                "OFFSITE_CONVERSIONS",
            )
            self.assertNotIn("secret", json.dumps(result))
            with self.assertRaisesRegex(ValueError, "live_deployment_disabled"):
                mc.stage_or_deploy_meta_campaign(
                    grounding(),
                    result["creatives"],
                    push_live=True,
                    campaign_settings=SETTINGS,
                )

    def test_json_sse_parity_and_grounding_public_packets(self):
        args = {
            "grounding": grounding(),
            "selected_strategy_ids": ["tribe_1"],
            "campaign_settings": SETTINGS,
        }
        with patch.object(gc, "_generate_one", return_value=valid_copy()):
            direct = sh.session_creatives(sh.CreativeRequest(**args))
            frames = list(sh.stream_creative_execution(args))
        events = [json.loads(f[6:]) for f in frames if f.startswith("data: ")]
        self.assertEqual(events[-1]["type"], "execution_complete")
        self.assertEqual(events[-1]["data"], direct)
        self.assertTrue(any(e["type"] == "creative_bundle" for e in events))
        self.assertTrue(any(e["type"] == "meta_staged" for e in events))
        source = {
            **grounding(),
            "demographics": {},
            "taste_vocabulary": [],
            "heatmap_pins": [],
        }
        source["_packets"] = source.pop("packets")
        public = sh._public_result(source)
        self.assertEqual(public["packets"], source["_packets"])
        self.assertNotIn("_packets", public)

    def test_nine_city_variants_use_at_most_three_workers(self):
        barrier = threading.Barrier(3, timeout=3)
        lock = threading.Lock()
        active, peak = 0, 0

        def generate(variant, callback):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            barrier.wait()
            with lock:
                active -= 1
            return valid_copy()

        with patch.object(gc, "_generate_one", side_effect=generate):
            result = ce.execute_creatives(grounding(3), None, SETTINGS)
        self.assertEqual(peak, 3)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(result["meta"]["ads"]), 9)

    def test_observer_failure_and_retry_city_lineage(self):
        def broken_observer(event):
            raise RuntimeError("Progress observer disconnected")

        with patch.object(gc, "_generate_one", return_value=valid_copy()):
            result = ce.execute_creatives(
                grounding(), ["tribe_1"], SETTINGS, on_event=broken_observer
            )
        self.assertEqual(result["status"], "complete")
        result["creatives"]["bundles"][0]["location_query"] = "Wrong city"
        with self.assertRaisesRegex(ValueError, "lineage"):
            ce.execute_creatives(
                grounding(), ["tribe_1"], SETTINGS, previous_result=result
            )

    def test_banned_copy_scrub_keeps_qloo_proper_names(self):
        variant = gc.normalize_selection(grounding())[0]
        variant["packet"]["artists"][0]["name"] = "Journey"
        data = valid_copy()
        for hook in data["creative_hooks"]:
            hook["qloo_anchor"] = "Journey"
        data["reel_script_15s"][
            "sonic_direction"
        ] = "Use Journey as a pacing reference."
        data["creative_hypothesis"] = "Elevate the evening near Engawa."
        checked = gc.validate_creative(data, variant)
        self.assertNotIn("elevate", checked["creative_hypothesis"].lower())
        self.assertIn("Journey", checked["reel_script_15s"]["sonic_direction"])
