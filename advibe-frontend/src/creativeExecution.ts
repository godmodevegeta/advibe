import { useEffect, useRef, useState } from "react";
import type { Output } from "./types";
import { consumeSSE } from "./stream";

export type CampaignSettings = {
  objective: "OUTCOME_SALES" | "OUTCOME_TRAFFIC" | "";
  daily_budget_cents_per_adset: number;
  currency: "USD" | "GBP" | "EUR";
};
export type CreativeBundle = {
  strategy_id: string;
  variant_id: string;
  location_query: string;
  tribe_name: string;
  local_tribe_name: string;
  creative_id: string;
  meta_ad: {
    primary_text: string;
    headline: string;
    description: string;
    call_to_action: string;
    destination_url: string;
  };
  creative_hooks: {
    angle: string;
    hook_text: string;
    qloo_anchor: string;
    qloo_id: string;
  }[];
  reel_script_15s: {
    sonic_direction: string;
    visual_direction: string;
    shots: {
      window: string;
      visual: string;
      audio_or_vo: string;
      on_screen_text: string;
    }[];
  };
  ooh_concept: {
    venue_anchors: string[];
    placement_format: string;
    poster_headline: string;
    visual_brief: string;
  };
  editorial_palette: {
    background_hex: string;
    text_hex: string;
    accent_hex: string;
    mood_label: string;
  };
  creative_hypothesis: string;
  measurement_plan: {
    primary_metric: string;
    diagnostic_metrics: string[];
    targets: null;
    measured_results: null;
  };
};
export type Failure = {
  variant_id: string;
  strategy_id: string;
  location_query: string;
  message: string;
};
export type MetaObject = {
  staged_id: string;
  strategy_id?: string;
  variant_id?: string;
  tribe_name?: string;
  location_query?: string;
  asset_status?: string;
  payload: Record<string, unknown>;
};
export type MetaStage = {
  mode: string;
  snapshot_id: string;
  api_validated: boolean;
  campaign: MetaObject;
  adsets: MetaObject[];
  adcreatives: MetaObject[];
  ads: MetaObject[];
  settings: CampaignSettings;
  daily_budget_total_minor_units: number;
  missing_inputs: string[];
  warnings: { message: string; variants: string[] }[];
  curl_script: string;
};
export type ExecutionResult = {
  snapshot_id: string;
  status: string;
  settings: CampaignSettings;
  selected_strategy_ids: string[];
  creatives: {
    input_fingerprint: string;
    expected_count: number;
    status: string;
    bundles: CreativeBundle[];
    failures: Failure[];
  };
  meta: MetaStage | null;
  staging_error: string | null;
};
export type ExecutionEvent = {
  type: string;
  timestamp: number;
  phase?: string;
  spinner_verb?: string;
  variant_id?: string;
  location_query?: string;
  message?: string;
  data?: unknown;
};
export type ExecutionState = {
  status: "idle" | "running" | "partial" | "complete" | "error";
  bundles: CreativeBundle[];
  failures: Failure[];
  events: ExecutionEvent[];
  result?: ExecutionResult;
  requestKey?: string;
  message?: string;
};
const initial = (): ExecutionState => ({
  status: "idle",
  bundles: [],
  failures: [],
  events: [],
});

export function useCreativeExecution(
  grounding: Output | null,
  selection: string[],
) {
  const [settings, setSettings] = useState<CampaignSettings>({
    objective: "",
    daily_budget_cents_per_adset: 5000,
    currency: "USD",
  });
  const [state, setState] = useState<ExecutionState>(initial);
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  useEffect(() => () => controller.current?.abort(), []);
  const body = {
    grounding,
    selected_strategy_ids: selection,
    campaign_settings: settings,
  };
  const requestKey = JSON.stringify(body);
  const changed = !!state.requestKey && state.requestKey !== requestKey;
  const variantCount =
    grounding?.strategies
      .filter((s) => selection.includes(s.id))
      .reduce((n, s) => n + (s.location_variants?.length || 1), 0) || 0;
  function reset() {
    generation.current++;
    controller.current?.abort();
    setState(initial());
  }
  async function run(retry = false) {
    if (
      !grounding ||
      !selection.length ||
      !settings.objective ||
      state.status === "running"
    )
      return;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    const id = ++generation.current;
    const previous = retry && !changed ? state.result : undefined;
    const captured = JSON.parse(
      JSON.stringify({ ...body, previous_result: previous }),
    );
    const progress: ExecutionResult = previous
      ? structuredClone(previous)
      : {
          snapshot_id: "",
          status: "partial",
          settings: { ...settings },
          selected_strategy_ids: [...selection],
          creatives: {
            input_fingerprint: "",
            expected_count: variantCount,
            status: "partial",
            bundles: [],
            failures: [],
          },
          meta: null,
          staging_error: null,
        };
    progress.creatives.failures = [];
    progress.meta = null;
    setState({
      status: "running",
      requestKey,
      bundles: progress.creatives.bundles,
      failures: [],
      events: [],
    });
    let terminal = false;
    try {
      const response = await fetch("/api/session/creatives/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(captured),
        signal: abort.signal,
      });
      if (!response.ok || !response.body) {
        const detail = await response.json().catch(() => null);
        throw new Error(
          typeof detail?.detail === "string"
            ? detail.detail
            : `Creative request failed (${response.status})`,
        );
      }
      await consumeSSE(response.body, (raw) => {
        if (id !== generation.current) return;
        const event = raw as unknown as ExecutionEvent;
        if (event.type === "execution_started")
          Object.assign(progress, event.data);
        if (event.type === "creative_snapshot")
          Object.assign(progress.creatives, event.data);
        if (event.type === "creative_bundle") {
          const bundle = event.data as CreativeBundle;
          progress.creatives.bundles = [
            ...progress.creatives.bundles.filter(
              (b) => b.variant_id !== bundle.variant_id,
            ),
            bundle,
          ];
        }
        if (event.type === "variant_error")
          progress.creatives.failures.push(event.data as Failure);
        if (event.type === "meta_staged")
          progress.meta = event.data as MetaStage;
        if (event.type === "execution_complete") {
          Object.assign(progress, event.data);
          terminal = true;
        }
        if (event.type === "execution_error") {
          terminal = true;
          throw new Error(event.message || "Execution interrupted");
        }
        setState((s) => ({
          ...s,
          status: terminal
            ? (progress.status as ExecutionState["status"])
            : "running",
          bundles: [...progress.creatives.bundles],
          failures: [...progress.creatives.failures],
          result: structuredClone(progress),
          events: [...s.events, event],
        }));
      });
      if (!terminal)
        throw new Error(
          "Creative stream ended early. Completed bundles have been retained.",
        );
    } catch (error) {
      if (id === generation.current && !abort.signal.aborted)
        setState((s) => ({
          ...s,
          status: s.bundles.length ? "partial" : "error",
          result:
            progress.snapshot_id && progress.creatives.input_fingerprint
              ? structuredClone(progress)
              : undefined,
          message: error instanceof Error ? error.message : "Execution failed",
        }));
    }
  }
  return { settings, setSettings, state, changed, variantCount, run, reset };
}
