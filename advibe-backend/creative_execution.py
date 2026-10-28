"""Shared JSON/SSE coordinator for creative execution and local Meta staging."""

from generate_creatives import generate_campaign_creatives, fingerprint, emit
from meta_campaign import CampaignSettings, stage_or_deploy_meta_campaign


def execute_creatives(
    grounding,
    selected_strategy_ids,
    campaign_settings,
    *,
    previous_result=None,
    on_event=None
):
    settings = CampaignSettings.model_validate(campaign_settings).model_dump()
    snapshot = fingerprint(
        {
            "grounding": grounding,
            "selection": selected_strategy_ids,
            "settings": settings,
        }
    )
    if previous_result and previous_result.get("snapshot_id") != snapshot:
        raise ValueError(
            "Selection, grounding, or settings changed; start a new execution"
        )
    emit(
        on_event,
        "execution_started",
        data={
            "snapshot_id": snapshot,
            "settings": settings,
            "selected_strategy_ids": selected_strategy_ids,
        },
    )
    creatives = generate_campaign_creatives(
        grounding,
        selected_strategy_ids=selected_strategy_ids,
        on_event=on_event,
        previous_result=previous_result.get("creatives") if previous_result else None,
        primary_metric=(
            "purchases" if settings["objective"] == "OUTCOME_SALES" else "outbound_ctr"
        ),
    )
    meta = None
    staging_error = None
    if creatives["status"] == "complete":
        try:
            meta = stage_or_deploy_meta_campaign(
                grounding, creatives, campaign_settings=settings, on_event=on_event
            )
        except ValueError as exc:
            staging_error = str(exc)
    result = {
        "snapshot_id": snapshot,
        "status": (
            "complete" if meta else "partial" if creatives["bundles"] else "error"
        ),
        "settings": settings,
        "selected_strategy_ids": selected_strategy_ids,
        "creatives": creatives,
        "meta": meta,
        "staging_error": staging_error,
    }
    emit(on_event, "execution_complete", data=result)
    return result
