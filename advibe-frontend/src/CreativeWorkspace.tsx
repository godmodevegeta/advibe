import { CopyButton, Waiting } from "./Artifacts";
import { LoaderCircle } from "lucide-react";
import type {
  CreativeBundle,
  ExecutionState,
  MetaObject,
  useCreativeExecution,
} from "./creativeExecution";
type Execution = ReturnType<typeof useCreativeExecution>;
const money = (amount: number, currency: string) =>
  new Intl.NumberFormat(undefined, { style: "currency", currency }).format(
    amount / 100,
  );

export function CreativeControls({
  execution,
  onStart,
}: {
  execution: Execution;
  onStart?: () => void;
}) {
  const { settings, setSettings, state, changed, variantCount } = execution;
  return (
    <section className="card creative-controls">
      <span className="eyebrow">FROM STRATEGY TO EXECUTION</span>
      <h3>Build the creative test.</h3>
      <p>
        {variantCount
          ? `${variantCount} localized creative bundle${variantCount === 1 ? "" : "s"} and ad set${variantCount === 1 ? "" : "s"}.`
          : "Select at least one tribe to continue."}{" "}
        Staged locally; no Meta objects will be created.
      </p>
      <div className="execution-settings">
        <label>
          Campaign objective
          <select
            aria-label="Campaign objective"
            value={settings.objective}
            onChange={(e) =>
              setSettings((s) => ({
                ...s,
                objective: e.target.value as typeof s.objective,
              }))
            }
            disabled={state.status === "running"}
          >
            <option value="">Choose objective</option>
            <option value="OUTCOME_SALES">Sales · Purchases</option>
            <option value="OUTCOME_TRAFFIC">Traffic · Link clicks</option>
          </select>
        </label>
        <label>
          Daily budget per ad set
          <input
            aria-label="Daily budget per ad set"
            type="number"
            min="0.01"
            step="0.01"
            value={settings.daily_budget_cents_per_adset / 100}
            onChange={(e) =>
              setSettings((s) => ({
                ...s,
                daily_budget_cents_per_adset: Math.round(
                  Number(e.target.value) * 100,
                ),
              }))
            }
            disabled={state.status === "running"}
          />
        </label>
        <label>
          Draft currency
          <select
            aria-label="Draft currency"
            value={settings.currency}
            onChange={(e) =>
              setSettings((s) => ({
                ...s,
                currency: e.target.value as typeof s.currency,
              }))
            }
            disabled={state.status === "running"}
          >
            {["USD", "GBP", "EUR"].map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
      </div>
      <p className="muted">
        Planned total:{" "}
        {money(
          settings.daily_budget_cents_per_adset * variantCount || 0,
          settings.currency,
        )}
        /day · Draft settings, not an account budget.
      </p>
      {changed && (
        <p role="status">
          Selection or settings changed. Earlier results keep their original
          snapshot; generate again to apply these changes.
        </p>
      )}
      {state.message && <p role="alert">{state.message}</p>}
      {state.result?.staging_error && (
        <p role="alert">
          Staging needs attention: {state.result.staging_error}
        </p>
      )}
      <button
        className="primary"
        disabled={
          !variantCount ||
          !settings.objective ||
          !Number.isFinite(settings.daily_budget_cents_per_adset) ||
          settings.daily_budget_cents_per_adset <= 0 ||
          state.status === "running"
        }
        onClick={() => {
          onStart?.();
          execution.run();
        }}
      >
        {state.status === "running"
          ? "Executing cultural briefs..."
          : "Generate Ad Creatives & Stage Meta Campaign"}
      </button>
      {(state.status === "partial" || state.status === "error") &&
        state.result &&
        !changed && (
          <button
            onClick={() => {
              onStart?.();
              execution.run(true);
            }}
          >
            Retry failed variants / staging
          </button>
        )}
      {state.failures.map((f) => (
        <p role="alert" key={f.variant_id}>
          {f.location_query} · {f.variant_id}: {f.message}
        </p>
      ))}
    </section>
  );
}

export function CreativeTimeline({ state }: { state: ExecutionState }) {
  const phases = state.events.filter((e) => e.type === "phase_change");
  if (state.status === "idle") return null;
  return (
    <section className="execution-progress">
      <span className="eyebrow">CREATIVE EXECUTION & STAGING</span>
      {phases.map((e, i) => (
        <div className="execution-progress-step" key={i}>
          <span>
            {i === phases.length - 1 && state.status === "running" ? (
              <LoaderCircle className="spin" size={18} aria-label="Running" />
            ) : state.status === "partial" || state.status === "error" ? (
              "·"
            ) : (
              "✓"
            )}
          </span>
          <p>
            {e.spinner_verb}
            {e.location_query && <small>{e.location_query}</small>}
          </p>
        </div>
      ))}
      <p role="status">
        {state.bundles.length} bundles ready · {state.failures.length} failed ·{" "}
        {state.status === "complete"
          ? "Meta hierarchy staged locally"
          : state.status}
      </p>
      {state.message && <p className="error">{state.message}</p>}
    </section>
  );
}

function Bundle({ bundle: b }: { bundle: CreativeBundle }) {
  const palette = b.editorial_palette;
  return (
    <article className="card creative-bundle">
      <div className="section-row">
        <span className="pill">{b.location_query}</span>
        <CopyButton text={JSON.stringify(b, null, 2)} />
      </div>
      <h3>{b.local_tribe_name}</h3>
      <div
        className="editorial-ad"
        style={{
          backgroundColor: palette.background_hex,
          color: palette.text_hex,
        }}
      >
        <span className="eyebrow">EDITORIAL FEED CONCEPT</span>
        <div
          className="editorial-rule"
          style={{ backgroundColor: palette.accent_hex }}
        />
        <h2>{b.meta_ad.headline}</h2>
        <p>{b.meta_ad.primary_text}</p>
        <p className="editorial-description">{b.meta_ad.description}</p>
        <span className="editorial-cta">
          {b.meta_ad.call_to_action.replaceAll("_", " ")}
        </span>
      </div>
      <p className="muted">
        Interpretive palette: {palette.mood_label}. Proposed creative, not a
        published ad.
      </p>
      <p>{b.creative_hypothesis}</p>
      <p className="muted">
        Proposed primary metric:{" "}
        {b.measurement_plan.primary_metric.replaceAll("_", " ")}. No measured
        results or targets.
      </p>
      <h4>Three testable hooks</h4>
      {b.creative_hooks.map((h) => (
        <div className="creative-hook" key={h.angle}>
          <h4>{h.angle}</h4>
          <p>{h.hook_text}</p>
          <span className="pill" title={h.qloo_id}>
            {h.qloo_anchor}
          </span>
        </div>
      ))}
      <h4>15-second reel storyboard</h4>
      <p>{b.reel_script_15s.sonic_direction}</p>
      <p>{b.reel_script_15s.visual_direction}</p>
      <div className="storyboard">
        {b.reel_script_15s.shots.map((s) => (
          <section key={s.window}>
            <span className="eyebrow">{s.window}</span>
            <h4>{s.on_screen_text}</h4>
            <p>{s.visual}</p>
            <p className="muted">Audio / VO: {s.audio_or_vo}</p>
          </section>
        ))}
      </div>
      <div className="ooh-card">
        <span className="eyebrow">PROPOSED STREET-LEVEL OOH</span>
        <h2>{b.ooh_concept.poster_headline}</h2>
        <p>{b.ooh_concept.visual_brief}</p>
        <p>{b.ooh_concept.placement_format}</p>
        <div className="pills">
          {b.ooh_concept.venue_anchors.map((v) => (
            <span className="pill" key={v}>
              {v}
            </span>
          ))}
        </div>
        <p className="muted">
          Placement concept only; venue approval and media buying are not
          included.
        </p>
      </div>
      <details>
        <summary>Destination and creative JSON</summary>
        <p className="preserve">{b.meta_ad.destination_url}</p>
        <p className="muted">
          Simulated .example landing page. Replace before any future deployment.
        </p>
        <pre className="json">{JSON.stringify(b, null, 2)}</pre>
      </details>
    </article>
  );
}

export function CreativeArtifacts({
  state,
  onRetry,
}: {
  state: ExecutionState;
  onRetry?: () => void;
}) {
  if (!state.bundles.length)
    return state.status === "error" || state.status === "partial" ? (
      <section className="card">
        <h3>Creative execution needs attention.</h3>
        <p>
          {state.message ||
            "No valid bundles were generated. Retry from the selected tribes."}
        </p>
        {state.failures.map((f) => (
          <p key={f.variant_id}>
            {f.variant_id}: {f.message}
          </p>
        ))}
        {onRetry && (
          <button onClick={onRetry}>Retry failed variants / staging</button>
        )}
      </section>
    ) : (
      <Waiting
        label={
          state.status === "running"
            ? "Executing the cultural briefs"
            : "Select tribes and generate creatives"
        }
      />
    );
  const groups = [...new Set(state.bundles.map((b) => b.strategy_id))];
  return (
    <>
      <div className="artifact-heading">
        <span className="eyebrow">STRUCTURED CREATIVE DEVELOPMENT</span>
        <h2>Culture, ready for the creative team.</h2>
        <p>
          {state.bundles.length} validated city bundles. Text, shot lists, and
          proposed art direction.
        </p>
      </div>
      {(state.status === "partial" || state.status === "error") && (
        <section className="card error" role="alert">
          <h3>Some creative work needs attention.</h3>
          <p>
            {state.message ||
              "Completed bundles are retained. Campaign staging waits for every selected variant."}
          </p>
          {state.failures.map((f) => (
            <p key={f.variant_id}>
              {f.location_query} · {f.variant_id}: {f.message}
            </p>
          ))}
          {state.result?.staging_error && <p>{state.result.staging_error}</p>}
          {onRetry && (
            <button onClick={onRetry}>Retry failed variants / staging</button>
          )}
        </section>
      )}
      {groups.map((id) => (
        <section key={id}>
          {state.bundles.filter((b) => b.strategy_id === id).length > 1 && (
            <h3>
              {state.bundles.find((b) => b.strategy_id === id)?.tribe_name}
            </h3>
          )}
          {state.bundles
            .filter((b) => b.strategy_id === id)
            .map((b) => (
              <Bundle key={b.variant_id} bundle={b} />
            ))}
        </section>
      ))}
    </>
  );
}

function TargetingSummary({ adset }: { adset: MetaObject }) {
  const targeting = adset.payload.targeting as {
    age_min: number;
    age_max: number;
    genders: number[];
    geo_locations: {
      custom_locations: {
        latitude: number;
        longitude: number;
        radius: number;
        distance_unit: string;
      }[];
    };
  };
  return (
    <>
      <p>
        Ages {targeting.age_min}-{targeting.age_max} ·{" "}
        {targeting.genders.map((g) => (g === 1 ? "Men" : "Women")).join(", ")}
      </p>
      {targeting.geo_locations.custom_locations.map((pin, i) => (
        <p key={i}>
          {pin.latitude.toFixed(5)}, {pin.longitude.toFixed(5)} ·{" "}
          {pin.radius.toFixed(1)}-{pin.distance_unit} planned radius
        </p>
      ))}
    </>
  );
}

export function MetaArtifacts({ state }: { state: ExecutionState }) {
  const meta = state.result?.meta;
  if (!meta)
    return (
      <section className="card">
        <h3>Meta campaign staging</h3>
        <p>
          {state.result?.staging_error ||
            (state.status === "partial" || state.status === "error"
              ? "Every selected variant must pass creative validation before campaign assembly."
              : "The local hierarchy appears after all selected creative bundles pass validation.")}
        </p>
        <p className="muted">Live deployment is not enabled in this version.</p>
      </section>
    );
  return (
    <>
      <div className="artifact-heading">
        <span className="eyebrow">LOCAL META STAGING</span>
        <h2>Review before activation.</h2>
        <p>
          One campaign · {meta.adsets.length} ad sets ·{" "}
          {meta.adcreatives.length} draft creatives · {meta.ads.length} ads.
          Nothing has been created in Meta.
        </p>
      </div>
      <section className="card">
        <span className="pill">STAGED · PAUSED REQUESTED</span>
        <h3>{String(meta.campaign.payload.name)}</h3>
        <p>
          {meta.settings.objective} · ABO ·{" "}
          {money(meta.daily_budget_total_minor_units, meta.settings.currency)}
          /day total draft budget
        </p>
        <p className="muted">
          Snapshot {meta.snapshot_id}. These templates have not been validated
          by Meta.
        </p>
        <div className="meta-tree">
          {meta.adsets.map((a, i) => (
            <details key={a.staged_id}>
              <summary>
                {a.tribe_name} · {a.location_query} · PAUSED
              </summary>
              <p>Ad set → Draft creative → Ad (PAUSED)</p>
              <p>
                {money(Number(a.payload.daily_budget), meta.settings.currency)}
                /day · {String(a.payload.optimization_goal)}
              </p>
              <TargetingSummary adset={a} />
              <p className="preserve">
                UTMs: {String(meta.adcreatives[i].payload.url_tags)}
              </p>
              <pre className="json">
                {JSON.stringify(
                  { adset: a, creative: meta.adcreatives[i], ad: meta.ads[i] },
                  null,
                  2,
                )}
              </pre>
            </details>
          ))}
        </div>
      </section>
      {!!meta.warnings.length && (
        <section className="card">
          <h3>Geographic overlap</h3>
          {meta.warnings.map((w, i) => (
            <p key={i}>
              {w.message} {w.variants.join(" · ")}
            </p>
          ))}
        </section>
      )}
      <section className="card">
        <h3>Inputs needed before future deployment</h3>
        <div className="pills">
          {meta.missing_inputs.map((v) => (
            <span className="pill" key={v}>
              {v}
            </span>
          ))}
        </div>
        <button disabled>Deploy to Meta (Paused)</button>
        <p className="muted">
          Live deployment and asset upload are deferred. All IDs shown here are
          staged IDs.
        </p>
      </section>
      <section className="card">
        <details>
          <summary>Graph API request templates</summary>
          <CopyButton text={JSON.stringify(meta, null, 2)} />
          <pre className="json">{JSON.stringify(meta, null, 2)}</pre>
        </details>
        <details>
          <summary>cURL review template</summary>
          <CopyButton text={meta.curl_script} />
          <pre className="json">{meta.curl_script}</pre>
        </details>
      </section>
    </>
  );
}
