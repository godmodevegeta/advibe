"""Local Meta request templates. This adapter never performs network requests."""

from __future__ import annotations

import json
import shlex
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from build_grounding import haversine_km
from generate_creatives import emit, fingerprint, normalize_selection


class CampaignSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective: Literal["OUTCOME_SALES", "OUTCOME_TRAFFIC"]
    daily_budget_cents_per_adset: int = Field(default=5000, gt=0, strict=True)
    currency: Literal["USD", "GBP", "EUR"] = "USD"


def stage_or_deploy_meta_campaign(
    grounding_result,
    creatives_result,
    *,
    daily_budget_cents_per_adset=5000,
    push_live=False,
    campaign_settings=None,
    on_event=None,
):
    if push_live:
        raise ValueError(
            "live_deployment_disabled: this version stages local drafts only"
        )
    if not campaign_settings:
        raise ValueError("Choose Sales or Traffic before staging")
    settings = CampaignSettings.model_validate(campaign_settings).model_dump()
    if "daily_budget_cents_per_adset" not in campaign_settings:
        settings["daily_budget_cents_per_adset"] = daily_budget_cents_per_adset
        settings = CampaignSettings.model_validate(settings).model_dump()
    if creatives_result.get("status") != "complete":
        raise ValueError(
            "All selected creative variants must pass validation before staging"
        )
    bundles = creatives_result["bundles"]
    selected = list(dict.fromkeys(b["strategy_id"] for b in bundles))
    variants = normalize_selection(grounding_result, selected)
    by_id = {v["variant_id"]: v for v in variants}
    if len(bundles) != len(variants) or {b["variant_id"] for b in bundles} != set(
        by_id
    ):
        raise ValueError("Creative coverage differs from the selected city variants")
    digest = fingerprint(
        {"grounding": variants, "creatives": creatives_result, "settings": settings}
    )[:16]
    campaign_id = f"camp_staged_{digest}"
    campaign = {
        "staged_id": campaign_id,
        "payload": {
            "name": f"{grounding_result['brand_name']} | {grounding_result['location_query']} | Advibe Qloo Cultural Campaign",
            "objective": settings["objective"],
            "status": "PAUSED",
            "special_ad_categories": [],
            "buying_type": "AUCTION",
            "is_adset_budget_sharing_enabled": False,
        },
    }
    adsets, creatives, ads = [], [], []
    warnings = []
    missing = [
        "META_API_VERSION",
        "META_AD_ACCOUNT_ID",
        "META_PAGE_ID",
        "approved image assets",
        "real destination URLs",
    ]
    if settings["objective"] == "OUTCOME_SALES":
        missing += ["META_PIXEL_ID", "purchase event configuration"]
    emit(
        on_event,
        "phase_change",
        phase="meta_assembly",
        spinner_verb=f"Assembling one staged campaign and {len(bundles)} localized ad sets...",
    )
    for index, bundle in enumerate(bundles, 1):
        variant = by_id[bundle["variant_id"]]
        spec = variant["strategy"]["meta_adset_spec"]
        age_min, age_max = spec.get("age_min"), spec.get("age_max")
        genders = spec.get("genders")
        pins = spec.get("geo_locations", {}).get("custom_locations", [])
        if (
            not isinstance(age_min, int)
            or not isinstance(age_max, int)
            or not 18 <= age_min <= age_max <= 65
            or not genders
            or any(g not in (1, 2) for g in genders)
        ):
            raise ValueError(
                f"Invalid age or gender targeting for {variant['variant_id']}"
            )
        if len(pins) != 1:
            raise ValueError("Each city variant requires exactly one geo pin")
        pin = pins[0]
        if (
            not -90 <= float(pin["latitude"]) <= 90
            or not -180 <= float(pin["longitude"]) <= 180
            or pin.get("radius") != 1.0
            or pin.get("distance_unit") != "mile"
        ):
            raise ValueError(
                "Each geo pin must retain valid coordinates and a 1.0-mile radius"
            )
        suffix = fingerprint({"snapshot": digest, "variant": bundle["variant_id"]})[:16]
        context = {
            "variant_id": bundle["variant_id"],
            "strategy_id": bundle["strategy_id"],
            "location_query": bundle["location_query"],
            "tribe_name": bundle["tribe_name"],
        }
        targeting = {
            "age_min": age_min,
            "age_max": age_max,
            "genders": genders,
            "geo_locations": {"custom_locations": pins},
            "targeting_automation": {"advantage_audience": 0},
        }
        adset_payload = {
            "name": spec.get("name") or bundle["local_tribe_name"],
            "campaign_id": "${META_CAMPAIGN_ID}",
            "status": "PAUSED",
            "daily_budget": settings["daily_budget_cents_per_adset"],
            "billing_event": "IMPRESSIONS",
            "optimization_goal": (
                "OFFSITE_CONVERSIONS"
                if settings["objective"] == "OUTCOME_SALES"
                else "LINK_CLICKS"
            ),
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "destination_type": "WEBSITE",
            "targeting": targeting,
        }
        if settings["objective"] == "OUTCOME_SALES":
            adset_payload["promoted_object"] = {
                "pixel_id": "${META_PIXEL_ID}",
                "custom_event_type": "PURCHASE",
            }
        adset_id, creative_id = f"adset_staged_{suffix}", f"cre_staged_{suffix}"
        adsets.append(
            {
                **context,
                "staged_id": adset_id,
                "campaign_staged_id": campaign_id,
                "payload": adset_payload,
            }
        )
        copy = bundle["meta_ad"]
        creatives.append(
            {
                **context,
                "staged_id": creative_id,
                "asset_status": "DRAFT",
                "preview_destination_url": copy["destination_url"],
                "payload": {
                    "name": f"{bundle['local_tribe_name']} | Editorial Feed",
                    "object_story_spec": {
                        "page_id": "${META_PAGE_ID}",
                        "link_data": {
                            "message": copy["primary_text"],
                            "name": copy["headline"],
                            "description": copy["description"],
                            "link": "${DESTINATION_URL_" + str(index) + "}",
                            "image_hash": "${IMAGE_HASH_" + str(index) + "}",
                            "call_to_action": {
                                "type": copy["call_to_action"],
                                "value": {
                                    "link": "${DESTINATION_URL_" + str(index) + "}"
                                },
                            },
                        },
                    },
                    "url_tags": copy["destination_url"].split("?", 1)[1],
                },
            }
        )
        ads.append(
            {
                **context,
                "staged_id": f"ad_staged_{suffix}",
                "adset_staged_id": adset_id,
                "creative_staged_id": creative_id,
                "payload": {
                    "name": f"{bundle['local_tribe_name']} | Ad v1",
                    "adset_id": "${META_ADSET_ID_" + str(index) + "}",
                    "creative": {
                        "creative_id": "${META_CREATIVE_ID_" + str(index) + "}"
                    },
                    "status": "PAUSED",
                },
            }
        )
    for i, a in enumerate(adsets):
        for b in adsets[i + 1 :]:
            if a["location_query"] != b["location_query"]:
                continue
            x = a["payload"]["targeting"]["geo_locations"]["custom_locations"][0]
            y = b["payload"]["targeting"]["geo_locations"]["custom_locations"][0]
            distance = haversine_km(x, y)
            if distance < 2 * 1.609344:
                warnings.append(
                    {
                        "kind": "geo_overlap",
                        "variants": [a["variant_id"], b["variant_id"]],
                        "distance_km": round(distance, 3),
                        "message": "Planned 1-mile circles overlap; auction separation is not guaranteed.",
                    }
                )
    operations = [
        {
            "method": "POST",
            "edge": "campaigns",
            "capture": "META_CAMPAIGN_ID",
            "payload": campaign["payload"],
        }
    ]
    for index, (adset, creative, ad) in enumerate(zip(adsets, creatives, ads), 1):
        operations += [
            {
                "method": "POST",
                "edge": edge,
                "capture": capture,
                "payload": obj["payload"],
            }
            for edge, capture, obj in (
                ("adsets", f"META_ADSET_ID_{index}", adset),
                ("adcreatives", f"META_CREATIVE_ID_{index}", creative),
                ("ads", f"META_AD_ID_{index}", ad),
            )
        ]
    # Deliberately non-executable: requires a separate future deployment implementation.
    lines = [
        "# REVIEW TEMPLATE ONLY - live deployment is not implemented.",
        "# Replace placeholders and validate against your account and supported API version.",
    ]
    for operation in operations:
        lines += [
            f"# Capture the returned id as {operation['capture']}",
            "# curl --request POST 'https://graph.facebook.com/${META_API_VERSION}/act_${META_AD_ACCOUNT_ID}/"
            + operation["edge"]
            + "' \\",
            "#   --header 'Authorization: Bearer ${META_ACCESS_TOKEN}' \\",
            "#   --header 'Content-Type: application/json' --data "
            + shlex.quote(json.dumps(operation["payload"], ensure_ascii=False)),
        ]
    result = {
        "mode": "staged_paused",
        "live_deployment_enabled": False,
        "api_validated": False,
        "snapshot_id": digest,
        "settings": settings,
        "campaign": campaign,
        "adsets": adsets,
        "adcreatives": creatives,
        "ads": ads,
        "operations": operations,
        "daily_budget_total_minor_units": settings["daily_budget_cents_per_adset"]
        * len(adsets),
        "missing_inputs": missing,
        "warnings": warnings,
        "curl_script": "\n".join(lines),
    }
    emit(on_event, "meta_staged", data=result)
    return result
