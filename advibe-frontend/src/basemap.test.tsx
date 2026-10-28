// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import L from "leaflet";
import { Geo } from "./Artifacts";
import { cartoAttribution } from "./basemap";
import type { Artifacts } from "./types";

vi.mock("leaflet", () => {
  const layer = {
    addTo: vi.fn().mockReturnThis(),
    bindTooltip: vi.fn().mockReturnThis(),
  };
  return {
    default: {
      map: vi.fn(() => ({
        fitBounds: vi.fn(),
        invalidateSize: vi.fn(),
        remove: vi.fn(),
      })),
      tileLayer: vi.fn(() => layer),
      circle: vi.fn(() => layer),
      marker: vi.fn(() => layer),
      circleMarker: vi.fn(() => layer),
      divIcon: vi.fn(),
      latLngBounds: vi.fn(() => ({ pad: vi.fn() })),
    },
  };
});

const artifacts: Artifacts = {
  geo_pins: {
    heatmap_pins: [
      {
        latitude: 40.72,
        longitude: -73.99,
        affinity: 0.8,
        neighborhood_label: "SoHo",
      },
    ],
    places: [
      {
        name: "Local listening bar",
        entity_id: "test-venue",
        latitude: 40.721,
        longitude: -73.991,
      },
    ],
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("CARTO map configuration", () => {
  it("uses the configured key, attribution, and campaign overlays", () => {
    vi.stubEnv("VITE_CARTO_API_KEY", " example-key ");
    const view = render(<Geo artifacts={artifacts} />);
    expect(L.tileLayer).toHaveBeenCalledWith(
      "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png?key=example-key",
      { attribution: cartoAttribution, maxZoom: 19 },
    );
    expect(cartoAttribution).toContain("OpenStreetMap contributors");
    expect(cartoAttribution).toContain("CARTO");
    expect(L.circle).toHaveBeenCalledWith(
      [40.72, -73.99],
      expect.objectContaining({ radius: 1609.344 }),
    );
    expect(L.marker).toHaveBeenCalledTimes(1);
    expect(L.circleMarker).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("status")).toBeNull();
    const map = vi.mocked(L.map).mock.results[0].value;
    view.unmount();
    expect(map.remove).toHaveBeenCalledOnce();
  });

  it.each([undefined, "", "   "])(
    "keeps pins and venues without a usable key (%s)",
    (key) => {
      vi.stubEnv("VITE_CARTO_API_KEY", key);
      render(<Geo artifacts={artifacts} />);
      expect(screen.getByRole("status").textContent).toContain(
        "Configure a CARTO basemap key",
      );
      expect(L.tileLayer).not.toHaveBeenCalled();
      expect(L.marker).toHaveBeenCalledTimes(1);
      expect(screen.getByText("Local listening bar")).toBeDefined();
      expect(screen.getByText("SoHo")).toBeDefined();
    },
  );
});
