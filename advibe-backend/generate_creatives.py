"""Execute selected cultural briefs into validated, platform-neutral creative bundles."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Literal
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field
from build_grounding import BANNED_PHRASES, scrub_banned_phrases
from user_input import complete_json


def emit(callback, event_type, **payload):
    if callback:
        try:
            callback(
                {
                    "type": event_type,
                    "workflow": "creative_execution",
                    "timestamp": time.time(),
                    **payload,
                }
            )
        except Exception:
            # Progress observers must not turn a valid bundle into a failed one.
            pass


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def slug(value):
    return (
        re.sub(
            r"[^a-z0-9]+",
            "-",
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode()
            .lower(),
        ).strip("-")
        or "campaign"
    )


def normalize_selection(grounding, selected_strategy_ids=None):
    strategies = grounding.get("strategies")
    if not isinstance(strategies, list) or not strategies:
        raise ValueError("Grounding must contain completed strategies")
    by_id = {s["id"]: s for s in strategies}
    selected = (
        list(by_id)
        if selected_strategy_ids is None
        else list(dict.fromkeys(selected_strategy_ids))
    )
    if not selected or any(s not in by_id for s in selected):
        raise ValueError("Select at least one known tribe")
    packets = grounding.get("packets", grounding.get("_packets", []))
    variants = []
    for sid in selected:
        parent = by_id[sid]
        for strategy in parent.get("location_variants") or [parent]:
            packet = strategy.get("packet") or next(
                (p for p in packets if p["strategy_id"] == strategy["id"]), None
            )
            if (
                not packet
                or not strategy.get("cultural_system_prompt")
                or not strategy.get("meta_adset_spec")
            ):
                raise ValueError(
                    f"Missing packet, cultural brief, or Meta specification for {sid}; restart grounding"
                )
            city = (
                strategy.get("location_query")
                or packet.get("product_context", {}).get("location_query")
                or grounding.get("location_query")
            )
            city_id = strategy.get("location_id") or (
                sid.split(":")[0] if ":" in sid else "city_1"
            )
            variant_id = f"{city_id}:{strategy['id'].split(':')[-1]}"
            variants.append(
                {
                    "strategy_id": sid,
                    "variant_id": variant_id,
                    "location_id": city_id,
                    "location_query": city,
                    "tribe_name": parent["tribe_name"],
                    "local_tribe_name": strategy["tribe_name"],
                    "strategy": strategy,
                    "packet": packet,
                }
            )
    if len({v["variant_id"] for v in variants}) != len(variants):
        raise ValueError("Duplicate city variant identifiers")
    return variants


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MetaAd(StrictModel):
    primary_text: str = Field(min_length=1)
    headline: str = Field(min_length=1)
    description: str = Field(min_length=1)
    call_to_action: Literal["SHOP_NOW", "LEARN_MORE", "SIGN_UP"]


class Hook(StrictModel):
    angle: str = Field(min_length=1)
    hook_text: str = Field(min_length=1)
    qloo_anchor: str = Field(min_length=1)
    qloo_id: str = Field(min_length=1)


class Shot(StrictModel):
    window: Literal["0-3s Hook", "3-10s Hold", "10-15s CTA"]
    visual: str = Field(min_length=1)
    audio_or_vo: str = Field(min_length=1)
    on_screen_text: str = Field(min_length=1)


class Reel(StrictModel):
    sonic_direction: str = Field(min_length=1)
    visual_direction: str = Field(min_length=1)
    shots: list[Shot] = Field(min_length=3, max_length=3)


class OOH(StrictModel):
    venue_anchors: list[str]
    placement_format: str = Field(min_length=1)
    poster_headline: str = Field(min_length=1)
    visual_brief: str = Field(min_length=1)


class Palette(StrictModel):
    background_hex: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    accent_hex: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    text_hex: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    mood_label: str = Field(min_length=1)


class Creative(StrictModel):
    meta_ad: MetaAd
    creative_hooks: list[Hook] = Field(min_length=3, max_length=3)
    reel_script_15s: Reel
    ooh_concept: OOH
    editorial_palette: Palette
    creative_hypothesis: str = Field(min_length=1)


def anchors(packet):
    return {
        e.get("entity_id", e.get("tag_id")): e["name"]
        for key in ("artists", "movies", "podcasts", "brands", "venues", "taste_tags")
        for e in packet.get(key, [])
        if e.get("entity_id", e.get("tag_id")) and e.get("name")
    }


def contrast(a, b):
    def luminance(color):
        channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        channels = [
            c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
            for c in channels
        ]
        return sum(c * w for c, w in zip(channels, (0.2126, 0.7152, 0.0722)))

    x, y = sorted((luminance(a), luminance(b)))
    return (y + 0.05) / (x + 0.05)


def validate_creative(raw, variant):
    packet = variant["packet"]
    allowed = anchors(packet)
    errors = []
    protected = [
        *allowed.values(),
        packet.get("product_context", {}).get("brand_name", ""),
    ]

    def scrub(value, key=""):
        if isinstance(value, dict):
            return {k: scrub(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [scrub(v, key) for v in value]
        if (
            isinstance(value, str)
            and key
            not in (
                "qloo_id",
                "qloo_anchor",
                "venue_anchors",
                "window",
                "call_to_action",
            )
            and not key.endswith("_hex")
        ):
            if re.search(
                r"\b(?:(?:endorsed|sponsored|supported|approved|backed)\s+by|official partner|in partnership with|collaboration with|(?:available|stocked|sold|served) at)\b",
                value,
                re.I,
            ):
                errors.append(
                    "Creative copy must not claim endorsements, commercial relationships, or product availability from Qloo cultural references"
                )
            brand = packet.get("product_context", {}).get("brand_name", "")
            if (
                brand
                and key
                in (
                    "primary_text",
                    "hook_text",
                    "headline",
                    "description",
                    "on_screen_text",
                    "audio_or_vo",
                    "poster_headline",
                )
                and re.search(
                    r"\b(?:find|enjoy|buy|get|order|try|discover|experience)\s+"
                    + re.escape(brand)
                    + r"\b[^.!?\n]{0,35}\bat\b",
                    value,
                    re.I,
                )
            ):
                errors.append(
                    "Do not tell viewers to find, buy, or enjoy the product at Qloo venues; distribution is unverified. Refer to neighborhood culture instead."
                )
            value = scrub_banned_phrases(value, protected)
            checked = value
            for name in sorted(filter(None, protected), key=len, reverse=True):
                checked = re.sub(re.escape(name), "", checked, flags=re.I)
            if any(
                re.search(r"\b" + re.escape(p) + r"\b", checked, re.I)
                for p in BANNED_PHRASES
            ):
                errors.append("Banned phrase remains in creative copy")
        return value

    data = Creative.model_validate(scrub(raw)).model_dump()
    if not re.search(r"[.!?][\"'\u2019\u201d]?$", data["meta_ad"]["primary_text"]):
        errors.append(
            "primary_text must end with a complete sentence after banned-phrase scrubbing, not a dangling fragment"
        )
    for field, low, high in (
        ("primary_text", 60, 110),
        ("headline", 5, 9),
        ("description", 6, 12),
    ):
        count = len(data["meta_ad"][field].split())
        if not low <= count <= high:
            errors.append(
                f"{field} must contain {low}-{high} words after banned-phrase scrubbing, got {count}"
            )
    hooks = data["creative_hooks"]
    if (
        len({h["hook_text"].casefold() for h in hooks}) != 3
        or len({h["angle"].casefold() for h in hooks}) != 3
    ):
        errors.append("Hooks and angles must be distinct")
    invalid = [
        {"qloo_id": h["qloo_id"], "qloo_anchor": h["qloo_anchor"]}
        for h in hooks
        if allowed.get(h["qloo_id"]) != h["qloo_anchor"]
    ]
    if invalid:
        errors.append(
            f"Hook anchor must match an exact packet entity or tag. Invalid pairs: {json.dumps(invalid)}. Copy pairs from allowed_hook_anchors."
        )
    venues = [e["name"] for e in packet.get("venues", [])]
    if set(data["ooh_concept"]["venue_anchors"]) != set(venues):
        errors.append("OOH venue anchors must match the assigned packet venues")
    for field, key in (("sonic_direction", "artists"), ("visual_direction", "movies")):
        if any(
            e["name"].casefold() not in data["reel_script_15s"][field].casefold()
            for e in packet.get(key, [])
        ):
            errors.append(f"{field} must cite the packet's {key}")
    if [s["window"] for s in data["reel_script_15s"]["shots"]] != [
        "0-3s Hook",
        "3-10s Hold",
        "10-15s CTA",
    ]:
        errors.append("Reel beats must follow the exact 15-second sequence")
    palette = data["editorial_palette"]
    if contrast(palette["background_hex"], palette["text_hex"]) < 16:
        errors.append("Editorial background and text must have at least 16:1 contrast")
    if errors:
        raise ValueError("; ".join(errors))
    return data


def _generate_one(variant, on_event):
    payload = {
        "packet": variant["packet"],
        "allowed_hook_anchors": [
            {"qloo_id": key, "qloo_anchor": name}
            for key, name in anchors(variant["packet"]).items()
        ],
        "schema": Creative.model_json_schema(),
        "forbidden_phrases": list(BANNED_PHRASES),
    }
    instruction = """Execute the cultural brief as structured creative development. Return ONLY JSON matching the supplied schema. Primary text: 60-110 words; headline: 5-9 words; description: 6-12 words. Three distinct hooks must cite exact packet qloo_anchor names and qloo_id UUIDs/tag URNs. OOH venue_anchors must contain all and only packet venue names. Cite every packet artist in sonic_direction and every packet movie in visual_direction. Use exact windows 0-3s Hook, 3-10s Hold, 10-15s CTA. The palette is interpretive art direction; background/text contrast must be >=16:1 (near-black and near-white work). Accent may carry film-inspired color. Keep the proposition coherent across formats. Placements are proposals, not permission. Do not invent entities, prices, discounts, product benefits, endorsements, licensing, performance statistics, or trend momentum. Missing evidence stays missing. No Never use clause in deliverable copy. No URLs or IDs outside the anchor fields."""
    messages = [
        {
            "role": "system",
            "content": variant["strategy"]["cultural_system_prompt"]
            + "\n\n"
            + instruction,
        },
        {
            "role": "user",
            "content": "Aim for 85 words of primary text, a 7-word headline, and a 9-word description. Count whitespace-separated words before returning JSON. Avoid forbidden phrases because removing them can make copy too short. Product facts come ONLY from packet.product_context.product_description. Cultural tags and reference brands are audience tastes, never evidence that the product has those benefits, ingredients, certifications, ethical production, or distribution. Say inspired by when referring to cultural references. Never claim supported by, endorsements, partnerships, or that the product is sold at an assigned venue. Do not imply permission to use an artist's recording; propose sonic characteristics as references subject to rights clearance. Use allowed_hook_anchors as the exclusive source for the three hooks. Copy each chosen qloo_id and qloo_anchor pair verbatim, including UUID case. Do not cite the selected campaign seeds unless they occur in this list. The same valid reference may support distinct hooks. The structured output instructions override any conflicting formatting instructions in the cultural brief.\n"
            + json.dumps(payload, ensure_ascii=False),
        },
    ]
    for attempt in range(2):
        raw = complete_json(
            messages, max_tokens=3000, temperature=0.3 if not attempt else 0.1
        )
        try:
            return validate_creative(raw, variant)
        except (ValueError, TypeError) as exc:
            if attempt:
                raise
            emit(
                on_event,
                "phase_change",
                phase="creative_repair",
                spinner_verb=f"Repairing creative constraints for {variant['local_tribe_name']}...",
                variant_id=variant["variant_id"],
                location_query=variant["location_query"],
            )
            messages += [
                {"role": "assistant", "content": json.dumps(raw, ensure_ascii=False)},
                {
                    "role": "user",
                    "content": f"Repair the JSON. Validation error: {str(exc)[:1500]}. Return the complete corrected object.",
                },
            ]


def generate_campaign_creatives(
    grounding_result: dict[str, Any],
    *,
    selected_strategy_ids=None,
    on_event=None,
    previous_result=None,
    primary_metric="purchases",
):
    variants = normalize_selection(grounding_result, selected_strategy_ids)
    input_hash = fingerprint({"variants": variants, "primary_metric": primary_metric})
    bundles = {}
    if previous_result:
        if previous_result.get("input_fingerprint") != input_hash:
            raise ValueError("Retry input differs from the original creative snapshot")
        by_id = {v["variant_id"]: v for v in variants}
        for bundle in previous_result.get("bundles", []):
            vid = bundle.get("variant_id")
            if vid not in by_id:
                raise ValueError("Retry contains an unknown creative variant")
            variant = by_id[vid]
            if (
                any(
                    bundle.get(key) != variant[key]
                    for key in (
                        "strategy_id",
                        "location_id",
                        "location_query",
                        "tribe_name",
                        "local_tribe_name",
                    )
                )
                or bundle.get("packet_id") != variant["packet"]["packet_id"]
            ):
                raise ValueError(
                    "Retry creative lineage differs from its frozen city packet"
                )
            raw = {k: bundle[k] for k in Creative.model_fields}
            raw = copy.deepcopy(raw)
            raw["meta_ad"].pop("destination_url", None)
            if validate_creative(raw, variant) != raw:
                raise ValueError(
                    "Retry contains copy that has not passed the final scrub"
                )
            bundles[vid] = copy.deepcopy(bundle)
    pending = [v for v in variants if v["variant_id"] not in bundles]
    failures = []
    emit(
        on_event,
        "creative_snapshot",
        data={
            "input_fingerprint": input_hash,
            "expected_count": len(variants),
            "bundles": list(bundles.values()),
        },
    )
    emit(
        on_event,
        "phase_change",
        phase="creative_generation",
        spinner_verb=f"Executing {len(pending)} cultural briefs with up to 3 creative workers...",
    )
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_generate_one, v, on_event): v for v in pending}
        for future in as_completed(futures):
            variant = futures[future]
            try:
                data = future.result()
                brand = (
                    variant["packet"].get("product_context", {}).get("brand_name")
                    or grounding_result["brand_name"]
                )
                campaign_slug = f"{slug(brand)}_{slug(variant['location_query'])}"
                query = urlencode(
                    {
                        "utm_source": "meta",
                        "utm_medium": "paid_social",
                        "utm_campaign": campaign_slug,
                        "utm_content": variant["variant_id"],
                    }
                )
                data["meta_ad"][
                    "destination_url"
                ] = f"https://{slug(brand)}.example/{slug(variant['location_query'])}?{query}"
                bundle = {
                    **data,
                    **{
                        k: variant[k]
                        for k in (
                            "strategy_id",
                            "variant_id",
                            "location_id",
                            "location_query",
                            "tribe_name",
                            "local_tribe_name",
                        )
                    },
                    "creative_id": "creative_"
                    + fingerprint(
                        {
                            "input": input_hash,
                            "variant": variant["variant_id"],
                            "copy": data,
                        }
                    )[:16],
                    "packet_id": variant["packet"]["packet_id"],
                    "source_anchors": anchors(variant["packet"]),
                    "measurement_plan": {
                        "primary_metric": primary_metric,
                        "diagnostic_metrics": [
                            "thumbstop_rate",
                            "hold_rate",
                            "outbound_ctr",
                            "purchase_cvr",
                            "cpa",
                            "roas",
                        ],
                        "targets": None,
                        "measured_results": None,
                    },
                }
                bundles[variant["variant_id"]] = bundle
                emit(on_event, "creative_bundle", data=bundle)
            except Exception as exc:
                failure = {
                    "variant_id": variant["variant_id"],
                    "strategy_id": variant["strategy_id"],
                    "location_query": variant["location_query"],
                    "message": str(exc)[:1800],
                }
                failures.append(failure)
                emit(on_event, "variant_error", data=failure)
    ordered = [bundles[v["variant_id"]] for v in variants if v["variant_id"] in bundles]
    return {
        "input_fingerprint": input_hash,
        "status": "complete" if not failures else "partial" if ordered else "error",
        "expected_count": len(variants),
        "bundles": ordered,
        "failures": failures,
    }
