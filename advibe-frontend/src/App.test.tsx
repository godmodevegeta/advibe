// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import App from "./App";
import type { AskResponse, Entity } from "./types";
const entity = (name: string): Entity => ({
  name,
  entity_id: name,
  subtype: "urn:entity:brand",
});
const seeds = [entity("Erewhon"), entity("Chamberlain Coffee")],
  competitor = entity("Red Bull");
const base = {
  brand_name: "Chaen",
  product_description: "matcha energy drink",
  location: null,
  location_query: null,
  resolved_entities: { seed: [], competitors: [] },
  resolved_tags: [],
  insights_tags: [],
  explicit_seed_brands: [],
  explicit_competitor_brands: [],
  seed_tags: [],
  neighborhood_hints: [],
  suggested_seed_queries: [],
  suggested_competitor_queries: [],
  messages: [],
} as AskResponse["state"];
const initial: AskResponse = {
  ready_for_session: false,
  missing_pillars: ["location", "seeds", "competitor"],
  assistant_message: "Choose two inspirations, a city, and a competitor.",
  crafted_prompt: "Campaign for Chaen",
  suggestions: {
    seeds,
    competitors: [competitor],
    locations: ["New York, NY"],
  },
  state: base,
  resolved_signals: { ...base, raw_signals: {} },
};
const ready: AskResponse = {
  ...initial,
  ready_for_session: true,
  missing_pillars: [],
  assistant_message: "All four signals are verified.",
  state: {
    ...base,
    location_query: "New York, NY",
    resolved_entities: { seed: seeds, competitors: [competitor] },
  },
  resolved_signals: {
    ...initial.resolved_signals,
    location_query: "New York, NY",
    resolved_entities: { seed: seeds, competitors: [competitor] },
  },
};
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
function setup() {
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
    configurable: true,
    value: vi.fn(),
  });
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ presets: [] })))
    .mockResolvedValueOnce(new Response(JSON.stringify(initial)))
    .mockResolvedValueOnce(new Response(JSON.stringify(ready)));
  vi.stubGlobal("fetch", fetcher);
  render(<App />);
  return fetcher;
}
describe("Ask journey", () => {
  it("submits Enter, batches verified selections, gates sessions, and re-resolves edited text", async () => {
    const fetcher = setup();
    const composer = screen.getByLabelText("Campaign prompt");
    fireEvent.change(composer, {
      target: { value: "I have a brand called Chaen" },
    });
    fireEvent.keyDown(composer, { key: "Enter" });
    await screen.findByText(initial.assistant_message);
    expect(fetcher.mock.calls[1][0]).toBe("/api/ask");
    expect(screen.queryByText("Start Session")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Erewhon/ }));
    fireEvent.click(screen.getByRole("button", { name: /Chamberlain Coffee/ }));
    fireEvent.click(screen.getByRole("button", { name: /Red Bull/ }));
    fireEvent.click(screen.getByRole("button", { name: "New York, NY" }));
    fireEvent.click(
      screen.getByRole("button", { name: /Continue with signals/ }),
    );
    await screen.findByText("Start Session");
    const sent = JSON.parse(fetcher.mock.calls[2][1].body);
    expect(sent.selected_seeds).toEqual(seeds);
    expect(sent.state).toEqual(base);
    expect(sent.selected_location).toBe("New York, NY");
    fireEvent.change(screen.getByLabelText("Curated campaign prompt"), {
      target: { value: "Edited campaign" },
    });
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(
          new TextEncoder().encode(
            'data: {"type":"error","timestamp":1,"message":"Test interruption","error_type":"Test"}\n\n',
          ),
        );
        c.close();
      },
    });
    fetcher.mockResolvedValueOnce(new Response(body));
    fireEvent.click(screen.getByRole("button", { name: /Start Session/ }));
    await screen.findByText("Test interruption");
    expect(fetcher.mock.calls[3][0]).toBe("/api/grounding/stream");
    expect(JSON.parse(fetcher.mock.calls[3][1].body).prompt).toBe(
      "Edited campaign",
    );
  });
  it("retains input after failure and retries without duplicating the user message", async () => {
    const fetcher = setup();
    fetcher
      .mockReset()
      .mockRejectedValueOnce(new Error("Network unavailable"))
      .mockResolvedValueOnce(new Response(JSON.stringify(ready)));
    fireEvent.change(screen.getByLabelText("Campaign prompt"), {
      target: { value: "Retry my campaign" },
    });
    fireEvent.keyDown(screen.getByLabelText("Campaign prompt"), {
      key: "Enter",
    });
    await screen.findByText("Network unavailable");
    expect(
      (screen.getByLabelText("Campaign prompt") as HTMLTextAreaElement).value,
    ).toBe("Retry my campaign");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByText("Start Session");
    expect(screen.getAllByText("Retry my campaign")).toHaveLength(1);
  });
});

import { act } from "@testing-library/react";
import artifacts from "./fixtures/grounding.json";
it("hydrates audience mid-stream and renders three selectable live-contract campaigns", async () => {
  const fetcher = setup();
  fetcher
    .mockReset()
    .mockResolvedValueOnce(new Response(JSON.stringify(ready)));
  fireEvent.change(screen.getByLabelText("Campaign prompt"), {
    target: {
      value: "I have a brand called Chaen - it's a matcha energy drink",
    },
  });
  fireEvent.keyDown(screen.getByLabelText("Campaign prompt"), { key: "Enter" });
  await screen.findByText("Start Session");
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  fetcher.mockResolvedValueOnce(new Response(body));
  fireEvent.click(screen.getByRole("button", { name: /Start Session/ }));
  const send = async (event: unknown) => {
    await act(async () => {
      controller.enqueue(
        new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`),
      );
    });
  };
  await send({
    type: "artifact_patch",
    timestamp: 1,
    artifact: "audience_insights",
    data: artifacts.audience_insights,
  });
  fireEvent.click(
    screen.getByRole("button", { name: /Audience & Taste Graph/ }),
  );
  await screen.findByText("Demographic cohort lift · Global seed profile");
  expect(screen.queryByText("Your cultural tribes are ready.")).toBeNull();
  await send({
    type: "artifact_patch",
    timestamp: 2,
    artifact: "packets",
    data: artifacts.packets,
  });
  await send({
    type: "artifact_patch",
    timestamp: 3,
    artifact: "strategies",
    data: artifacts.strategies,
  });
  fireEvent.click(screen.getByRole("button", { name: /Tribe Campaigns/ }));
  expect(screen.getAllByRole("checkbox")).toHaveLength(3);
  fireEvent.click(screen.getAllByRole("checkbox")[0]);
  expect(screen.getByText("1 of 3 selected")).toBeDefined();
  expect(screen.getAllByText("PAUSED")).toHaveLength(3);
  fireEvent.click(screen.getByRole("button", { name: "Collapse artifacts" }));
  expect(screen.queryByRole("checkbox")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Expand artifacts" }));
  expect((screen.getAllByRole("checkbox")[0] as HTMLInputElement).checked).toBe(
    true,
  );
  await send({
    type: "complete",
    timestamp: 4,
    duration_seconds: 3,
    data: {
      brand_name: "Chaen",
      location_query: "New York, NY",
      demographics: artifacts.audience_insights.demographics,
      taste_vocabulary: artifacts.audience_insights.taste_vocabulary,
      heatmap_pins: artifacts.geo_pins.heatmap_pins,
      strategies: artifacts.strategies,
    },
  });
  await act(async () => controller.close());
  await screen.findByText("Your cultural tribes are ready.");
  fireEvent.click(
    screen.getByRole("button", { name: /Audience & Taste Graph/ }),
  );
  expect(
    screen.getByText("Demographic cohort lift · Global seed profile"),
  ).toBeDefined();
});

it("defaults to three shared tribes, offers scope selection, and switches city artifacts", async () => {
  const fetcher = setup();
  const locations = ["New York, NY", "San Francisco, CA", "London, UK"].map(
    (location_query) => ({ location_query, neighborhood_hints: [] }),
  );
  const multi = {
    ...ready,
    state: { ...ready.state, locations, tribe_scope: "overall" },
    resolved_signals: {
      ...ready.resolved_signals,
      locations,
      tribe_scope: "overall",
    },
  };
  fetcher
    .mockReset()
    .mockResolvedValueOnce(new Response(JSON.stringify(multi)));
  fireEvent.change(screen.getByLabelText("Campaign prompt"), {
    target: {
      value: "I have a brand called Chaen - it's a matcha energy drink",
    },
  });
  fireEvent.keyDown(screen.getByLabelText("Campaign prompt"), { key: "Enter" });
  await screen.findByRole("button", { name: "3 per city" });
  expect(screen.getByText(/3 tribes across 3 cities/)).toBeDefined();
  fetcher.mockResolvedValueOnce(
    new Response(
      JSON.stringify({
        ...multi,
        state: { ...multi.state, tribe_scope: "per_location" },
        resolved_signals: {
          ...multi.resolved_signals,
          tribe_scope: "per_location",
        },
      }),
    ),
  );
  fireEvent.click(screen.getByRole("button", { name: "3 per city" }));
  await screen.findByText(/9 tribes across 3 cities/);
  expect(JSON.parse(fetcher.mock.calls[1][1].body).selected_tribe_scope).toBe(
    "per_location",
  );
  fetcher.mockResolvedValueOnce(new Response(JSON.stringify(multi)));
  fireEvent.click(screen.getByRole("button", { name: "3 total" }));
  await screen.findByText(/3 tribes across 3 cities/);
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  fetcher.mockResolvedValueOnce(
    new Response(
      new ReadableStream<Uint8Array>({
        start(c) {
          controller = c;
        },
      }),
    ),
  );
  fireEvent.click(screen.getByRole("button", { name: /Start Session/ }));
  const send = async (event: unknown) =>
    act(async () => {
      controller.enqueue(
        new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`),
      );
    });
  for (const [index, location] of locations.entries()) {
    await send({
      type: "artifact_patch",
      timestamp: index + 1,
      artifact: "audience_insights",
      location_id: `city_${index + 1}`,
      location_query: location.location_query,
      data: {
        ...artifacts.audience_insights,
        taste_vocabulary: [
          {
            name: `Signal from ${location.location_query}`,
            tag_id: `tag-${index}`,
          },
        ],
      },
    });
  }
  fireEvent.click(
    screen.getByRole("button", { name: /Audience & Taste Graph/ }),
  );
  expect(screen.getByText("Signal from New York, NY")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "London, UK" }));
  expect(screen.getByText("Signal from London, UK")).toBeDefined();
  expect(screen.queryByText("Signal from New York, NY")).toBeNull();
  const parents = artifacts.strategies.map((s, index) => ({
    id: s.id,
    tribe_name: `Shared tribe ${index + 1}`,
    strategic_angle: s.strategic_angle,
    qloo_grounding_summary: "Grounded in three cities",
    location_variants: locations.map((l, i) => ({
      ...s,
      location_id: `city_${i + 1}`,
      location_query: l.location_query,
      packet: artifacts.packets[index],
    })),
  }));
  await send({
    type: "artifact_patch",
    timestamp: 5,
    artifact: "strategies",
    data: parents,
  });
  fireEvent.click(screen.getByRole("button", { name: /Tribe Campaigns/ }));
  expect(screen.getAllByRole("checkbox")).toHaveLength(3);
  expect(screen.getAllByText("Localized execution")).toHaveLength(9);
  fireEvent.click(screen.getAllByRole("checkbox")[0]);
  expect(screen.getByText("1 of 3 selected")).toBeDefined();
  await act(async () => controller.close());
  await screen.findByText(
    "The stream ended early. Restart the session to try again.",
  );
});
