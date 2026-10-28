import { describe, it, expect } from "vitest";
import {
  consumeSSE,
  initialSession,
  sessionReducer,
  sessionRequest,
} from "./stream";
import type { Output, StreamEvent, Signals } from "./types";
describe("stream transport", () => {
  it("retains every trending attempt across windows and cities", () => {
    let state = initialSession();
    for (const city of ["city_1", "city_2"])
      for (const id of ["recent", "history"]) {
        state = sessionReducer(state, {
          type: "qloo_call",
          timestamp: 1,
          location_id: city,
          name: "trending",
          call_id: `${city}:${id}`,
          status: "running",
        });
        state = sessionReducer(state, {
          type: "qloo_call",
          timestamp: 2,
          location_id: city,
          name: "trending",
          call_id: `${city}:${id}`,
          status: id === "recent" ? "empty" : "ok",
        });
      }
    expect(Object.keys(state.calls)).toHaveLength(4);
    expect(
      Object.values(state.calls).filter((c) => c.status === "empty"),
    ).toHaveLength(2);
  });
  it("decodes fragmented UTF-8, CRLF, comments and final unterminated frames", async () => {
    const events: StreamEvent[] = [];
    const bytes = new TextEncoder().encode(
      ': heartbeat\r\n\r\ndata: {"type":"phase_change","timestamp":1,"phase":"qloo_fanout","spinner_verb":"Café"}\r\n\r\ndata: {"type":"error","timestamp":2,"message":"test","error_type":"Test"}',
    );
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        for (const byte of bytes) c.enqueue(new Uint8Array([byte]));
        c.close();
      },
    });
    await consumeSSE(body, (e) => events.push(e));
    expect(events).toHaveLength(2);
    expect(events[0]).toMatchObject({ spinner_verb: "Café" });
  });
  it("retains partial artifacts through checkpoint and completion", () => {
    let state = initialSession();
    state = sessionReducer(state, {
      type: "artifact_patch",
      timestamp: 1,
      artifact: "packets",
      data: [],
    });
    state = sessionReducer(state, {
      type: "phase_change",
      timestamp: 2,
      phase: "qloo_fanout",
      spinner_verb: "Working",
    });
    state = sessionReducer(state, {
      type: "phase_change",
      timestamp: 6.2,
      phase: "strategy_generation",
      spinner_verb: "Generating",
    });
    expect(state.steps[0].end! - state.steps[0].start).toBeCloseTo(4.2);
    const output = { strategies: [] } as unknown as Output;
    state = sessionReducer(state, {
      type: "checkpoint",
      timestamp: 7,
      checkpoint_id: "strategy_selection",
      spinner_verb: "Select tribes",
      data: output,
    });
    state = sessionReducer(state, {
      type: "complete",
      timestamp: 8,
      data: output,
      duration_seconds: 7,
    });
    expect(state.artifacts.packets).toEqual([]);
    expect(state.status).toBe("complete");
    expect(state.message).toBe("Select tribes");
    state = sessionReducer(state, { type: "reset" });
    expect(state.events).toEqual([]);
  });
  it("preserves artifacts when interrupted", () => {
    let state = initialSession();
    state = sessionReducer(state, {
      type: "artifact_patch",
      timestamp: 1,
      artifact: "geo_pins",
      data: { heatmap_pins: [], places: [] },
    });
    state = sessionReducer(state, {
      type: "error",
      timestamp: 2,
      error_type: "StreamError",
      message: "Stream ended early",
    });
    expect(state.status).toBe("error");
    expect(state.artifacts.geo_pins).toBeDefined();
  });
  it("re-resolves only directly edited briefs", () => {
    const signals = { location_query: "Austin, TX" } as Signals;
    expect(sessionRequest("Campaign", "Campaign", signals).url).toBe(
      "/api/session/stream",
    );
    expect(sessionRequest("Edited", "Campaign", signals)).toEqual({
      url: "/api/grounding/stream",
      body: { prompt: "Edited", location: "Austin, TX" },
    });
  });
});

it("retains city-specific artifacts and identically named Qloo calls", () => {
  let state = initialSession();
  for (const [id, city] of [
    ["city_1", "New York, NY"],
    ["city_2", "London, UK"],
  ]) {
    state = sessionReducer(state, {
      type: "phase_change",
      timestamp: 1,
      phase: "qloo_fanout",
      spinner_verb: "Grounding",
      location_id: id,
      location_query: city,
    });
    state = sessionReducer(state, {
      type: "artifact_patch",
      timestamp: 2,
      artifact: "geo_pins",
      data: { heatmap_pins: [], places: [] },
      location_id: id,
      location_query: city,
    });
    state = sessionReducer(state, {
      type: "qloo_call",
      timestamp: 3,
      name: "places",
      status: "ok",
      duration_ms: 200,
      location_id: id,
      location_query: city,
    });
  }
  expect(Object.keys(state.cityArtifacts)).toEqual(["city_1", "city_2"]);
  expect(Object.keys(state.calls)).toHaveLength(2);
  expect(state.steps.map((step) => step.location_id)).toEqual([
    "city_1",
    "city_2",
  ]);
  state = sessionReducer(state, {
    type: "error",
    timestamp: 4,
    error_type: "CityGroundingError",
    message: "London, UK: Failed",
    location_query: "London, UK",
  });
  expect(state.cityArtifacts.city_1.geo_pins).toBeDefined();
  expect(state.status).toBe("error");
});
