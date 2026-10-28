// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  useCreativeExecution,
  type CreativeBundle,
  type ExecutionResult,
} from "./creativeExecution";
import { CreativeControls, CreativeArtifacts } from "./CreativeWorkspace";
import type { Output } from "./types";
import fixture from "./fixtures/grounding.json";

const grounding = {
  brand_name: "Chaen",
  location_query: "New York, NY",
  demographics: fixture.audience_insights.demographics,
  taste_vocabulary: fixture.audience_insights.taste_vocabulary,
  heatmap_pins: fixture.geo_pins.heatmap_pins,
  strategies: fixture.strategies,
  packets: fixture.packets,
} as Output;
const bundle: CreativeBundle = {
  strategy_id: "tribe_1",
  variant_id: "city_1:tribe_1",
  location_query: "New York, NY",
  tribe_name: "Creative tribe",
  local_tribe_name: "Local creative tribe",
  creative_id: "creative_1",
  meta_ad: {
    primary_text: "Proposed copy",
    headline: "A local cultural concept",
    description: "A planned test",
    call_to_action: "LEARN_MORE",
    destination_url: "https://chaen.example/nyc",
  },
  creative_hooks: [
    {
      angle: "Evening",
      hook_text: "Find a new rhythm",
      qloo_anchor: "Artist",
      qloo_id: "artist-id",
    },
  ],
  reel_script_15s: {
    sonic_direction: "Measured pacing",
    visual_direction: "Soft light",
    shots: [],
  },
  ooh_concept: {
    venue_anchors: ["Local venue"],
    placement_format: "Proposed poster",
    poster_headline: "Your evening",
    visual_brief: "Typographic concept",
  },
  editorial_palette: {
    background_hex: "#101010",
    text_hex: "#ffffff",
    accent_hex: "#3080ff",
    mood_label: "Evening",
  },
  creative_hypothesis: "A local reference may resonate",
  measurement_plan: {
    primary_metric: "outbound_ctr",
    diagnostic_metrics: [],
    targets: null,
    measured_results: null,
  },
};
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stream() {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  return {
    response: new Response(body),
    send: async (event: unknown) =>
      act(async () => {
        controller.enqueue(
          new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`),
        );
      }),
    close: async () => act(async () => controller.close()),
  };
}

it("requires the app user to choose an objective and counts grouped city variants", () => {
  function Controls() {
    const execution = useCreativeExecution(
      {
        ...grounding,
        strategies: [
          {
            ...grounding.strategies[0],
            location_variants: [
              grounding.strategies[0],
              { ...grounding.strategies[0], location_id: "city_2" },
              { ...grounding.strategies[0], location_id: "city_3" },
            ],
          },
        ],
      },
      ["tribe_1"],
    );
    return <CreativeControls execution={execution} />;
  }
  render(<Controls />);
  const button = screen.getByRole("button", {
    name: "Generate Ad Creatives & Stage Meta Campaign",
  }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  expect(screen.getByText(/3 localized creative bundles/)).toBeDefined();
  expect(screen.getByText(/150.00\/day/)).toBeDefined();
  fireEvent.change(screen.getByLabelText("Campaign objective"), {
    target: { value: "OUTCOME_SALES" },
  });
  expect(button.disabled).toBe(false);
  fireEvent.change(screen.getByLabelText("Daily budget per ad set"), {
    target: { value: "0" },
  });
  expect(button.disabled).toBe(true);
});

it("hydrates bundles before completion and retries only the unchanged failed snapshot", async () => {
  const first = stream(),
    second = stream();
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(first.response)
    .mockResolvedValueOnce(second.response);
  vi.stubGlobal("fetch", fetcher);
  const { result, rerender } = renderHook(
    ({ selection }) => useCreativeExecution(grounding, selection),
    { initialProps: { selection: ["tribe_1", "tribe_2"] } },
  );
  act(() =>
    result.current.setSettings((s) => ({ ...s, objective: "OUTCOME_TRAFFIC" })),
  );
  let pending!: Promise<void>;
  act(() => {
    pending = result.current.run();
  });
  await first.send({
    type: "execution_started",
    data: { snapshot_id: "snapshot" },
  });
  await first.send({
    type: "creative_snapshot",
    data: { input_fingerprint: "input", expected_count: 2, bundles: [] },
  });
  await first.send({ type: "creative_bundle", data: bundle });
  expect(result.current.state.status).toBe("running");
  expect(result.current.state.bundles).toHaveLength(1);
  const partial: ExecutionResult = {
    snapshot_id: "snapshot",
    status: "partial",
    settings: result.current.settings,
    selected_strategy_ids: ["tribe_1", "tribe_2"],
    creatives: {
      input_fingerprint: "input",
      expected_count: 2,
      status: "partial",
      bundles: [bundle],
      failures: [
        {
          variant_id: "city_1:tribe_2",
          strategy_id: "tribe_2",
          location_query: "New York, NY",
          message: "Invalid copy",
        },
      ],
    },
    meta: null,
    staging_error: null,
  };
  await first.send({ type: "execution_complete", data: partial });
  await first.close();
  await act(async () => pending);
  expect(result.current.state.status).toBe("partial");
  act(() => {
    pending = result.current.run(true);
  });
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  expect(JSON.parse(fetcher.mock.calls[1][1].body).previous_result).toEqual(
    partial,
  );
  expect(result.current.state.bundles).toHaveLength(1);
  await second.send({
    type: "execution_complete",
    data: {
      ...partial,
      status: "complete",
      creatives: { ...partial.creatives, failures: [], status: "complete" },
    },
  });
  await second.close();
  await act(async () => pending);
  rerender({ selection: ["tribe_1"] });
  expect(result.current.changed).toBe(true);
  expect(result.current.state.bundles[0]).toEqual(bundle);
  expect(grounding.strategies).toEqual(fixture.strategies);
});

it("retains incremental results when a stream disconnects and isolates a new session", async () => {
  const transport = stream();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(transport.response));
  const { result } = renderHook(() =>
    useCreativeExecution(grounding, ["tribe_1"]),
  );
  act(() =>
    result.current.setSettings((s) => ({ ...s, objective: "OUTCOME_TRAFFIC" })),
  );
  let pending!: Promise<void>;
  act(() => {
    pending = result.current.run();
  });
  await transport.send({
    type: "execution_started",
    data: { snapshot_id: "snapshot" },
  });
  await transport.send({
    type: "creative_snapshot",
    data: { input_fingerprint: "input" },
  });
  await transport.send({ type: "creative_bundle", data: bundle });
  await transport.close();
  await act(async () => pending);
  expect(result.current.state.status).toBe("partial");
  expect(result.current.state.message).toMatch(/ended early/);
  expect(result.current.state.result?.creatives.bundles).toEqual([bundle]);
  act(() => result.current.reset());
  expect(result.current.state.status).toBe("idle");
  expect(result.current.state.bundles).toEqual([]);
});

it("renders editorial previews and exact entity provenance without measured performance claims", () => {
  render(
    <CreativeArtifacts
      state={{ status: "running", bundles: [bundle], failures: [], events: [] }}
    />,
  );
  expect(screen.getByText("A local cultural concept")).toBeDefined();
  expect(screen.getByText("Artist").title).toBe("artist-id");
  expect(screen.getByText(/No measured results or targets/)).toBeDefined();
  expect(screen.getByText("New York, NY")).toBeDefined();
});
