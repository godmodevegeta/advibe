// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { AudienceView, TrendHistory } from "./Artifacts";
import type { Audience, TrendingResult } from "./types";
afterEach(cleanup);
const history: TrendingResult = {
  status: "available",
  reason: "recent_history",
  scope: "global",
  entity: {
    name: "Erewhon",
    entity_id: "seed",
    subtype: "urn:entity:brand",
    source: "selected_seed",
  },
  recent_window: { start_date: "2026-10-01", end_date: "2026-10-28" },
  returned_date_range: { start_date: "2026-10-27", end_date: "2026-10-27" },
  records: [
    {
      date: "2026-10-27",
      is_recent: true,
      population_rank: 11991,
      population_percentile: 0.8784,
      population_rank_velocity: 0,
      velocity_fold_change: 0,
      population_percent_delta: 0,
    },
  ],
  recent_record_count: 1,
  broader_window_used: true,
  attempts: [],
  skipped_entities: [],
};
it("renders retrieved history and zero metrics without asserting growth", () => {
  render(<TrendHistory data={history} />);
  expect(screen.getByText("Latest observation available")).toBeTruthy();
  expect(
    screen.getByRole("heading", { name: "Latest trend snapshot" }),
  ).toBeTruthy();
  expect(screen.getByText(/Qloo reports zero change/)).toBeTruthy();
  expect(screen.getByText("11,991")).toBeTruthy();
  expect(screen.getByText("0.8784")).toBeTruthy();
  expect(screen.getByText(/broader history request/)).toBeTruthy();
  expect(screen.queryByText(/rising/i)).toBeNull();
});
it("shows only the newest of identical weekly records and retains full evidence collapsed", () => {
  const records = ["2026-10-07", "2026-10-28", "2026-10-21", "2026-10-14"].map(
    (date) => ({
      ...history.records[0],
      date,
      population_rank: 51310,
      population_percentile: 0.10941893603659665,
    }),
  );
  const data = {
    ...history,
    records,
    attempts: [{ http_status: 200, window_kind: "history" }],
  };
  const { container } = render(<TrendHistory data={data} />);
  expect(container.querySelectorAll("time")).toHaveLength(1);
  expect(screen.getByText("2026-10-28")).toBeTruthy();
  expect(screen.queryByText("2026-10-21")).toBeNull();
  expect(screen.queryByRole("table")).toBeNull();
  expect(screen.getByText("51,310")).toBeTruthy();
  expect(screen.getByText("0.109419")).toBeTruthy();
  const evidence = screen
    .getByText("Trend sources and request evidence")
    .closest("details")!;
  expect(evidence.open).toBe(false);
  expect(JSON.parse(evidence.querySelector("pre")!.textContent!)).toEqual(data);
});
it("selects by valid calendar date without changing history and describes only the latest movement", () => {
  const records = [
    { ...history.records[0], date: "2026-10-07" },
    { ...history.records[0], date: "invalid", population_rank: 1 },
    { ...history.records[0], date: "2026-13-01", population_rank: 1 },
    { ...history.records[0], date: "2026-02-30", population_rank: 1 },
    {
      ...history.records[0],
      date: "2026-10-28",
      population_rank: 50,
      population_rank_velocity: 2,
    },
    { ...history.records[0], date: "2026-10-21" },
  ];
  const original = structuredClone(records);
  render(<TrendHistory data={{ ...history, records }} />);
  expect(screen.getByText("2026-10-28")).toBeTruthy();
  expect(screen.getByText("50")).toBeTruthy();
  expect(screen.getByText("2")).toBeTruthy();
  expect(screen.queryByText(/Qloo reports zero change/)).toBeNull();
  expect(records).toEqual(original);
});
it("preserves zero movement on the latest observation when earlier values differ", () => {
  render(
    <TrendHistory
      data={{
        ...history,
        records: [
          {
            ...history.records[0],
            date: "2026-10-21",
            population_rank_velocity: 10,
          },
          history.records[0],
        ],
      }}
    />,
  );
  expect(
    screen.getByText(/Qloo reports zero change in this observation/),
  ).toBeTruthy();
});
it("keeps missing metrics unavailable instead of treating them as zero", () => {
  render(
    <TrendHistory
      data={{
        ...history,
        records: [
          {
            ...history.records[0],
            population_rank: null,
            velocity_fold_change: null,
          },
        ],
      }}
    />,
  );
  expect(screen.getAllByText("Unavailable")).toHaveLength(2);
  expect(screen.getAllByText("0")).toHaveLength(2);
  expect(screen.queryByText(/Qloo reports zero change/)).toBeNull();
});
it("labels an older latest observation as historical and handles invalid-only observations", () => {
  const view = render(
    <TrendHistory
      data={{
        ...history,
        reason: "historical_only",
        records: [
          { ...history.records[0], date: "2026-09-30", is_recent: false },
        ],
        recent_record_count: 0,
      }}
    />,
  );
  expect(screen.getByText("Historical coverage only")).toBeTruthy();
  expect(screen.getByText(/Historical observation/)).toBeTruthy();
  expect(screen.getByText("2026-09-30")).toBeTruthy();
  view.rerender(
    <TrendHistory
      data={{
        ...history,
        records: [{ ...history.records[0], date: "2026-02-30" }],
      }}
    />,
  );
  expect(screen.getByText("No valid observations available")).toBeTruthy();
  expect(screen.queryByText("11,991")).toBeNull();
});
it("distinguishes loading, empty data, rejected requests and historical coverage", () => {
  const view = render(<TrendHistory />);
  expect(screen.getByText(/Waiting for Qloo/)).toBeTruthy();
  view.rerender(
    <TrendHistory data={{ ...history, status: "no_data", records: [] }} />,
  );
  expect(screen.getByText("No records for this window")).toBeTruthy();
  view.rerender(
    <TrendHistory
      data={{
        ...history,
        status: "error",
        reason: "request_rejected",
        records: [],
      }}
    />,
  );
  expect(screen.getByText("Request rejected")).toBeTruthy();
  view.rerender(
    <TrendHistory
      data={{ ...history, reason: "historical_only", recent_record_count: 0 }}
    />,
  );
  expect(screen.getByText("Historical coverage only")).toBeTruthy();
});
it("shows missing coverage and global methodology without inventing percentages", () => {
  const data: Audience = {
    demographics: {
      aggregate_age: { "25_to_29": 0.4, "30_to_34": null },
      aggregate_gender: {},
      all_seed_blocks: [],
      top_positive_cohorts: [],
      excluded_cohorts: [],
      coverage: {
        requested: 2,
        returned: 1,
        missing_seeds: [{ name: "Chamberlain Coffee", entity_id: "venue" }],
      },
    },
    taste_vocabulary: [
      { name: "Wellness", tag_id: "urn:tag:wellness", affinity: 0.99 },
    ],
    compare: null,
    trending: null,
  };
  render(<AudienceView data={data} />);
  expect(screen.getByText(/Coverage: 1 of 2/).textContent).toContain(
    "Chamberlain Coffee",
  );
  expect(screen.getByText("N/A")).toBeTruthy();
  expect(screen.getByText(/Wellness · affinity 0.990/)).toBeTruthy();
  expect(screen.queryByText(/99%/)).toBeNull();
  expect(screen.getByText(/Global seed profile/)).toBeTruthy();
});
