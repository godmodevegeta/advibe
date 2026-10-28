"""Stream the AdVibe grounding pipeline over Server-Sent Events.

The harness runs extract_seed_signals -> resolve_signals -> build_grounding in
a background thread and forwards pipeline events as SSE frames. It also exposes
a small FastAPI app for the React frontend.

Run the server:
    python3 stream_harness.py --serve

Run the terminal stream tester:
    python3 stream_harness.py -p "Build an Austin campaign for Humo Santo"

Event payloads all include ``type`` and ``timestamp``. The supported types are
``phase_change``, ``artifact_patch``, ``qloo_call``, ``checkpoint``,
``complete``, and ``error``. Every SSE frame is ``data: <json>\\n\\n``.

Dependencies are pinned in requirements.txt and installed in .venv.
"""

from __future__ import annotations

import argparse
import json
import queue
import threading
import time
from collections.abc import Iterator, Sequence
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ask_flow import ask_turn, _scope_message, _state_from
from campaign_locations import apply_location_turn, locations_from
from multi_grounding import build_multi_grounding
from build_grounding import _public_result, build_grounding
from resolve_signals import load_qloo_api_key, resolve_signals
from user_input import extract_seed_signals
from creative_execution import execute_creatives
from generate_creatives import normalize_selection
from meta_campaign import CampaignSettings

_STREAM_END = object()
_HEARTBEAT_SECONDS = 15.0


PRESETS: list[dict[str, str]] = [
    {
        "id": "chaen-matcha-nyc",
        "title": "Chaen Matcha Energy",
        "description": "Better-for-you energy for downtown creatives.",
        "prompt": (
            "Canned Ceremonial Matcha Energy drink brand called Chaen. "
            "Similar vibe to Chamberlain Coffee and Erewhon. Target city: "
            "New York, NY. Compare against Red Bull."
        ),
        "location": "New York, NY",
    },
    {
        "id": "humo-santo-austin",
        "title": "Humo Santo Mezcal",
        "description": "Artisanal mezcal for tech founders and vinyl lounges.",
        "prompt": (
            "Build an Austin, Texas campaign for 'Humo Santo', our new "
            "artisanal Espadín mezcal made for tech founders, poker nights, "
            "and vinyl lounges. Think the vibe of Casamigos meets Soho House "
            "and Khruangbin, going head-to-head against Don Julio."
        ),
        "location": "Austin, TX",
    },
    {
        "id": "nocturne-botanica-london",
        "title": "Nocturne Botanica",
        "description": "Smoky hinoki and fig skin-scent perfume oil.",
        "prompt": (
            "Launch a London, UK campaign for 'Nocturne Botanica', a smoky "
            "hinoki and fig skin-scent perfume oil for gallery directors, "
            "pilates regulars, and late-night wine bar readers. Channel the "
            "world of Aesop, Byredo, and FKA twigs, stealing buyers from Jo Malone."
        ),
        "location": "London, UK",
    },
    {
        "id": "vespera-chicago",
        "title": "Vespera",
        "description": "Zero-proof charred grapefruit and gentian bitter aperitif.",
        "prompt": (
            "Run a Chicago, Illinois campaign for 'Vespera', a zero-proof charred "
            "grapefruit and gentian bitter aperitif for chefs, architecture buffs, "
            "and jazz bar regulars. Channel the sensibility of Ghia, Fellow, and "
            "BadBadNotGood, positioning against Bitter Root Botanicals and Aperol."
        ),
        "location": "Chicago, IL",
    },
    {
        "id": "salina-club-miami",
        "title": "Salina Club",
        "description": "Marine-mineral electrolyte aperitif for active Miami mornings.",
        "prompt": (
            "We are launching 'Salina Club' in Miami, Florida - a marine-mineral "
            "electrolyte aperitif made for sunrise run clubs, padel players, and "
            "rooftop recovery sessions. Inspired by On Running, Soho Beach House, "
            "and Rüfüs Du Sol."
        ),
        "location": "Miami, FL",
    },
]


def _event(event_type: str, **payload: Any) -> dict[str, Any]:
    return {"type": event_type, "timestamp": time.time(), **payload}


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def stream_campaign_grounding(
    prompt: str,
    location_override: str | None = None,
    *,
    locations: list[dict[str, Any]] | None = None,
    tribe_scope: str | None = None,
) -> Iterator[str]:
    """Run the full pipeline in a worker thread and yield SSE frames live."""
    prompt = prompt.strip()
    location_override = (location_override or "").strip() or None
    if not prompt:
        yield _sse(
            _event(
                "error",
                message="prompt must be a non-empty string",
                error_type="ValueError",
            )
        )
        return

    events: queue.Queue[Any] = queue.Queue()
    stop_event = threading.Event()

    def emit(event: dict[str, Any]) -> None:
        if not stop_event.is_set():
            events.put(event)

    def worker() -> None:
        nonlocal location_override
        started = time.monotonic()
        try:
            emit(
                _event(
                    "phase_change",
                    phase="brief_extraction",
                    spinner_verb=(
                        "Parsing the brief into Qloo-ready cultural seeds..."
                    ),
                )
            )
            extracted = extract_seed_signals(prompt)
            if location_override:
                extracted["location"] = location_override
                extracted["location_query"] = location_override
            emit(
                _event(
                    "artifact_patch",
                    artifact="seed_signals",
                    data=extracted,
                )
            )

            api_key = load_qloo_api_key()
            resolved = resolve_signals(
                extracted,
                api_key,
                on_event=emit,
            )
            if locations is not None:
                current = _state_from(
                    {"locations": locations, "tribe_scope": tribe_scope}
                )
                edited_scope = _scope_message(prompt, _state_from(None))
                if edited_scope.get("locations") or edited_scope.get("location_query"):
                    current["locations"] = []
                apply_location_turn(current, edited_scope, None)
                resolved.update(
                    {
                        "locations": current["locations"],
                        "tribe_scope": current["tribe_scope"],
                    }
                )
                if not current["locations"]:
                    raise ValueError("provide at least one target location")
                location_override = current["locations"][0]["location_query"]
                resolved["location_query"] = current["location_query"]
                resolved["neighborhood_hints"] = current["neighborhood_hints"]
                resolved.setdefault("raw_signals", {}).update(
                    {
                        key: current[key]
                        for key in (
                            "locations",
                            "location_query",
                            "location",
                            "neighborhood_hints",
                            "tribe_scope",
                        )
                    }
                )
                emit(
                    _event("artifact_patch", artifact="resolved_signals", data=resolved)
                )
            if len(locations_from(resolved)) > 1:
                result = build_multi_grounding(resolved, api_key=api_key, on_event=emit)
            else:
                result = build_grounding(
                    resolved,
                    api_key=api_key,
                    location_override=location_override,
                    on_event=emit,
                )
            emit(
                _event(
                    "complete",
                    data=_public_result(result),
                    duration_seconds=round(time.monotonic() - started, 2),
                )
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as an SSE error event
            emit(
                _event(
                    "error",
                    message=str(exc),
                    location_query=getattr(exc, "location_query", None),
                    error_type=type(exc).__name__,
                )
            )
        finally:
            events.put(_STREAM_END)

    thread = threading.Thread(
        target=worker,
        name="grounding-stream",
        daemon=True,
    )
    thread.start()

    try:
        while True:
            try:
                item = events.get(timeout=_HEARTBEAT_SECONDS)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            if item is _STREAM_END:
                break
            yield _sse(item)
    finally:
        stop_event.set()


def stream_resolved_grounding(
    resolved_signals: dict[str, Any],
    location_override: str | None = None,
) -> Iterator[str]:
    """Stream grounding from Ask-verified signals without re-resolving them."""
    if not isinstance(resolved_signals, dict):
        yield _sse(
            _event(
                "error",
                message="resolved_signals must be an object",
                error_type="ValueError",
            )
        )
        return

    location_override = (location_override or "").strip() or None
    events: queue.Queue[Any] = queue.Queue()
    stop_event = threading.Event()

    def emit(event: dict[str, Any]) -> None:
        if not stop_event.is_set():
            events.put(event)

    def worker() -> None:
        started = time.monotonic()
        try:
            # This is intentionally first: the frontend can render its locked
            # Ask inputs before Qloo's six grounding calls begin.
            emit(
                _event(
                    "artifact_patch",
                    artifact="resolved_signals",
                    data=resolved_signals,
                )
            )
            api_key = load_qloo_api_key()
            if "locations" in resolved_signals and not locations_from(resolved_signals):
                raise ValueError("provide at least one target location")
            if len(locations_from(resolved_signals)) > 1:
                result = build_multi_grounding(
                    resolved_signals, api_key=api_key, on_event=emit
                )
            else:
                result = build_grounding(
                    resolved_signals,
                    api_key=api_key,
                    location_override=location_override,
                    on_event=emit,
                )
            emit(
                _event(
                    "complete",
                    data=_public_result(result),
                    duration_seconds=round(time.monotonic() - started, 2),
                )
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as an SSE error event
            emit(
                _event(
                    "error",
                    message=str(exc),
                    location_query=getattr(exc, "location_query", None),
                    error_type=type(exc).__name__,
                )
            )
        finally:
            events.put(_STREAM_END)

    thread = threading.Thread(
        target=worker,
        name="resolved-grounding-stream",
        daemon=True,
    )
    thread.start()

    try:
        while True:
            try:
                item = events.get(timeout=_HEARTBEAT_SECONDS)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            if item is _STREAM_END:
                break
            yield _sse(item)
    finally:
        stop_event.set()


app = FastAPI(
    title="AdVibe Grounding Stream",
    description=(
        "Live SSE harness for the Qloo signal resolution and grounding " "pipeline."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GroundingRequest(BaseModel):
    locations: list[dict[str, Any]] | None = None
    tribe_scope: Literal["overall", "per_location"] | None = None
    prompt: str = Field(..., min_length=1)
    location: str | None = None


class AskRequest(BaseModel):
    selected_tribe_scope: Literal["overall", "per_location"] | None = None
    prompt: str | None = None
    state: dict[str, Any] | None = None
    selected_seeds: list[str | dict[str, Any]] | None = None
    selected_competitors: list[str | dict[str, Any]] | None = None
    selected_location: str | None = None


class SessionRequest(BaseModel):
    locations: list[dict[str, Any]] | None = None
    tribe_scope: Literal["overall", "per_location"] | None = None
    resolved_signals: dict[str, Any] | None = None
    prompt: str | None = None
    location: str | None = None


class CreativeRequest(BaseModel):
    model_config = {"extra": "forbid"}
    grounding: dict[str, Any]
    selected_strategy_ids: list[str] | None = None
    campaign_settings: CampaignSettings
    previous_result: dict[str, Any] | None = None


def _creative_args(request: CreativeRequest):
    try:
        normalize_selection(request.grounding, request.selected_strategy_ids)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "grounding": request.grounding,
        "selected_strategy_ids": request.selected_strategy_ids,
        "campaign_settings": request.campaign_settings.model_dump(),
        "previous_result": request.previous_result,
    }


@app.post("/api/session/creatives")
def session_creatives(request: CreativeRequest):
    try:
        return execute_creatives(**_creative_args(request))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def stream_creative_execution(args):
    events = queue.Queue()
    stop = threading.Event()

    def emit(event):
        if not stop.is_set():
            events.put(event)

    def worker():
        try:
            execute_creatives(**args, on_event=emit)
        except Exception as exc:
            emit(
                _event(
                    "execution_error",
                    workflow="creative_execution",
                    message=str(exc)[:1800],
                )
            )
        finally:
            events.put(_STREAM_END)

    threading.Thread(target=worker, name="creative-execution", daemon=True).start()
    try:
        while True:
            try:
                event = events.get(timeout=_HEARTBEAT_SECONDS)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            if event is _STREAM_END:
                break
            yield _sse(event)
    finally:
        stop.set()


@app.post("/api/session/creatives/stream")
def session_creatives_stream(request: CreativeRequest):
    return StreamingResponse(
        stream_creative_execution(_creative_args(request)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/presets")
def presets() -> dict[str, Any]:
    return {"presets": PRESETS}


@app.post("/api/grounding/stream")
def grounding_stream(request: GroundingRequest) -> StreamingResponse:
    prompt = request.prompt.strip()
    if not prompt:
        raise HTTPException(
            status_code=422,
            detail="prompt must not be empty",
        )
    location = (request.location or "").strip() or None
    return StreamingResponse(
        (
            stream_campaign_grounding(
                prompt,
                location,
                locations=request.locations,
                tribe_scope=request.tribe_scope,
            )
            if request.locations is not None
            else stream_campaign_grounding(prompt, location)
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/ask")
def ask(request: AskRequest) -> dict[str, Any]:
    """Run one Ask workflow turn and return serializable next-turn state."""
    scope_args = (
        {"selected_tribe_scope": request.selected_tribe_scope}
        if request.selected_tribe_scope
        else {}
    )
    return ask_turn(
        request.prompt,
        state=request.state,
        selected_seeds=request.selected_seeds,
        selected_competitors=request.selected_competitors,
        selected_location=request.selected_location,
        **scope_args,
    )


@app.post("/api/session/stream")
def session_stream(request: SessionRequest) -> StreamingResponse:
    """Start a Session from locked Ask signals or the legacy prompt flow."""
    location = (request.location or "").strip() or None
    if request.resolved_signals is not None:
        signals = (
            dict(request.resolved_signals)
            if request.locations is not None or request.tribe_scope is not None
            else request.resolved_signals
        )
        if request.locations is not None:
            signals["locations"] = request.locations
        if request.tribe_scope is not None:
            signals["tribe_scope"] = request.tribe_scope
        stream = stream_resolved_grounding(signals, location)
    else:
        prompt = (request.prompt or "").strip()
        if not prompt:
            raise HTTPException(
                status_code=422,
                detail="provide resolved_signals or a non-empty prompt",
            )
        stream = (
            stream_campaign_grounding(
                prompt,
                location,
                locations=request.locations,
                tribe_scope=request.tribe_scope,
            )
            if request.locations is not None
            else stream_campaign_grounding(prompt, location)
        )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _artifact_summary(
    artifact: str,
    data: Any,
) -> str:
    if artifact == "packets":
        packets = data.get("packets") if isinstance(data, dict) else data
        return f" - packets={len(packets or [])}"
    if artifact == "strategies":
        strategies = data.get("strategies") if isinstance(data, dict) else data
        strategies = strategies or []
        names = [
            strategy.get("tribe_name")
            for strategy in strategies
            if isinstance(strategy, dict) and strategy.get("tribe_name")
        ]
        suffix = f": {', '.join(names)}" if names else ""
        return f" - strategies={len(strategies)}{suffix}"
    if not isinstance(data, dict):
        return ""
    if artifact == "seed_signals":
        brand = data.get("brand_name") or "unknown brand"
        seeds = len(data.get("seed_brands") or [])
        return f" - brand={brand}, seeds={seeds}"
    if artifact == "resolved_signals":
        entities = data.get("resolved_entities") or {}
        seed_count = len(entities.get("seed") or [])
        competitor_count = len(entities.get("competitors") or [])
        tags = len(data.get("resolved_tags") or [])
        return f" - seeds={seed_count}, competitors={competitor_count}, " f"tags={tags}"
    if artifact == "campaign_brief":
        return (
            f" - brand={data.get('brand_name')}, "
            f"location={data.get('location_query')}"
        )
    if artifact == "geo_pins":
        pins = data.get("heatmap_pins") or []
        places = data.get("places") or []
        return f" - pins={len(pins)}, places={len(places)}"
    if artifact == "audience_insights":
        return " - demographics, taste vocabulary, compare & trending ready"
    return ""


def _format_event(
    event: dict[str, Any],
    elapsed: float,
) -> str:
    prefix = f"[+{elapsed:.1f}s]"
    event_type = event.get("type", "unknown")
    if event_type == "phase_change":
        phase = event.get("phase", "unknown")
        return (
            f"{prefix} 🔄 phase_change: {phase} - " f"{event.get('spinner_verb', '')}"
        )
    if event_type == "artifact_patch":
        artifact = event.get("artifact", "unknown")
        summary = _artifact_summary(artifact, event.get("data"))
        return f"{prefix} 📦 artifact_patch: {artifact}{summary}"
    if event_type == "qloo_call":
        status = event.get("status", "unknown")
        if status == "running":
            emoji = "🔌"
        elif status == "ok":
            emoji = "✅"
        elif status == "empty":
            emoji = "⚠️"
        else:
            emoji = "❌"
        duration = event.get("duration_ms")
        suffix = f" {duration}ms" if duration is not None else ""
        name = event.get("name", "unknown")
        return f"{prefix} {emoji} qloo_call: {name} [{status}]{suffix}"
    if event_type == "checkpoint":
        return (
            f"{prefix} 🚦 checkpoint: "
            f"{event.get('checkpoint_id', 'unknown')} - "
            f"{event.get('spinner_verb', '')}"
        )
    if event_type == "complete":
        data = event.get("data") or {}
        strategies = data.get("strategies") or []
        return (
            f"{prefix} 🎉 complete: {data.get('brand_name', 'unknown')} in "
            f"{data.get('location_query', 'unknown')}, "
            f"strategies={len(strategies)}, "
            f"duration={event.get('duration_seconds', '?')}s"
        )
    if event_type == "error":
        return (
            f"{prefix} ❌ error: {event.get('error_type', 'Error')}: "
            f"{event.get('message', '')}"
        )
    return f"{prefix} • {event_type}: {json.dumps(event, ensure_ascii=False)}"


def _run_cli(prompt: str, location: str | None) -> int:
    started = time.monotonic()
    had_error = False
    for frame in stream_campaign_grounding(prompt, location):
        if not frame.startswith("data: "):
            continue
        try:
            event = json.loads(frame[len("data: ") :].strip())
        except json.JSONDecodeError:
            print(frame, end="", flush=True)
            continue
        print(
            _format_event(event, time.monotonic() - started),
            flush=True,
        )
        if event.get("type") == "error":
            had_error = True
    return 1 if had_error else 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stream_harness.py",
        description=(
            "Stream the AdVibe grounding pipeline over SSE, or run the "
            "FastAPI harness server."
        ),
    )
    parser.add_argument(
        "-p",
        "--prompt",
        help="Free-text brand brief. Runs the terminal stream tester.",
    )
    parser.add_argument(
        "-l",
        "--location",
        help='Override the target location, for example "Austin, TX".',
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start the FastAPI server. This is the default without -p.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Server host. Defaults to 127.0.0.1.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port. Defaults to 8000.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.prompt and args.serve:
        parser.error("pass either -p or --serve, not both")
    if args.prompt:
        return _run_cli(args.prompt, args.location)

    import uvicorn

    print(
        f"Serving AdVibe stream harness on http://{args.host}:{args.port}",
        flush=True,
    )
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
