import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Check, Copy, MapPin } from "lucide-react";
import type {
  Audience,
  Artifacts,
  Pin,
  Place,
  Tag,
  Strategy,
  Packet,
  TrendRecord,
  TrendingResult,
} from "./types";
import type { Session } from "./stream";
import { cartoAttribution, cartoTileUrl } from "./basemap";
export const percent = (n: number | null | undefined) =>
  n == null ? "Unavailable" : `${Math.round(n * 100)}%`;
export function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="copy"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1800);
        } catch {
          setCopied(false);
        }
      }}
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}{" "}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}
export function Pills({
  items,
}: {
  items: { name: string; affinity?: number | null; score?: number | null }[];
}) {
  return (
    <div className="pills">
      {items.map((x, i) => (
        <span className="pill" key={`${x.name}-${i}`}>
          {x.name}
          {x.affinity != null
            ? ` · affinity ${x.affinity.toFixed(3)}`
            : x.score != null
              ? ` · overlap score ${x.score.toFixed(3)}`
              : ""}
        </span>
      ))}
      {!items.length && <span className="muted">No signals returned</span>}
    </div>
  );
}
export function Waiting({ label }: { label: string }) {
  return (
    <div className="waiting">
      <span className="orbit">✳</span>
      <h2>{label}</h2>
      <p>Grounded in real signals. Appearing here as the agent works.</p>
      <div className="skeleton" />
      <div className="skeleton short" />
    </div>
  );
}
function GeoMap({ pins, places }: { pins: Pin[]; places: Place[] }) {
  const el = useRef<HTMLDivElement>(null);
  const tileUrl = cartoTileUrl(import.meta.env.VITE_CARTO_API_KEY);
  useEffect(() => {
    if (!el.current || !pins.length) return;
    const map = L.map(el.current, { scrollWheelZoom: false });
    if (tileUrl) {
      L.tileLayer(tileUrl, {
        attribution: cartoAttribution,
        maxZoom: 19,
      }).addTo(map);
    }
    pins.forEach((p, i) => {
      const color = ["#191919", "#3080ff", "#ff544e"][i % 3];
      L.circle([p.latitude, p.longitude], {
        radius: 1609.344,
        color,
        weight: 1,
        fillOpacity: 0.08,
      }).addTo(map);
      L.marker([p.latitude, p.longitude], {
        icon: L.divIcon({
          className: "pin-marker",
          html: `<span style="background:${color}">${i + 1}</span>`,
          iconSize: [30, 30],
        }),
      })
        .addTo(map)
        .bindTooltip(
          Object.assign(document.createElement("span"), {
            textContent: p.neighborhood_label || `Tribe ${i + 1}`,
          }),
        );
    });
    places.forEach((p) => {
      if (p.latitude != null && p.longitude != null)
        L.circleMarker([p.latitude, p.longitude], {
          radius: 5,
          color: "#3080ff",
          fillOpacity: 1,
        })
          .addTo(map)
          .bindTooltip(
            Object.assign(document.createElement("span"), {
              textContent: p.name,
            }),
          );
    });
    map.fitBounds(
      L.latLngBounds(
        pins.map((p) => [p.latitude, p.longitude] as [number, number]),
      ).pad(0.25),
      { maxZoom: 13 },
    );
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(el.current);
    return () => {
      observer.disconnect();
      map.remove();
    };
  }, [pins, places, tileUrl]);
  return (
    <>
      {!tileUrl && (
        <p role="status" className="error">
          Map background unavailable. Configure a CARTO basemap key to enable
          it. Campaign pins and venue details remain available.
        </p>
      )}
      <div
        className="map"
        ref={el}
        aria-label="Campaign geo-fences and local venues"
      />
    </>
  );
}
export function Geo({ artifacts }: { artifacts: Artifacts }) {
  const geo = artifacts.geo_pins;
  const packets = artifacts.packets;
  const places = packets ? packets.flatMap((p) => p.venues) : geo?.places || [];
  if (!geo) return <Waiting label="Mapping cultural neighborhoods" />;
  return (
    <>
      <div className="artifact-heading">
        <span className="eyebrow">LOCAL INTELLIGENCE</span>
        <h2>Culture has coordinates.</h2>
        <p>Three cultural territories. One walkable mile around each.</p>
      </div>
      {geo.heatmap_pins.length ? (
        <GeoMap pins={geo.heatmap_pins} places={places} />
      ) : (
        <p>No geo pins returned.</p>
      )}
      <div className="geo-cards">
        {geo.heatmap_pins.map((p, i) => (
          <article className="card" key={i}>
            <span className="eyebrow">TERRITORY 0{i + 1}</span>
            <h3>
              <MapPin size={16} />{" "}
              {p.neighborhood_label || "Local neighborhood"}
            </h3>
            <strong>{percent(p.affinity)} affinity</strong>
            <p className="muted">
              {p.latitude}, {p.longitude} · 1.0 mile radius
            </p>
            {packets?.[i]?.venues.map((v) => (
              <p key={v.entity_id}>
                {v.name}{" "}
                <small>
                  {v.distance_km == null
                    ? ""
                    : `${v.distance_km.toFixed(2)} km`}
                </small>
              </p>
            ))}
          </article>
        ))}
      </div>
      {!packets && (
        <section className="card">
          <h3>Discovered venues</h3>
          <Pills items={places} />
          <p className="muted">
            Tribe assignments and walking distances appear after packet slicing.
          </p>
        </section>
      )}
    </>
  );
}
function Lift({ values }: { values: Record<string, number | null> }) {
  return (
    <div className="lift-chart">
      <div className="axis">
        <span>-1.0</span>
        <span>0</span>
        <span>+1.0</span>
      </div>
      {Object.entries(values).map(([key, value]) => (
        <div className="lift-row" key={key}>
          <span>{key.replaceAll("_", " ")}</span>
          <div className="lift-track">
            <i />
            <b
              className={value != null && value < 0 ? "negative" : ""}
              style={{
                left: `${value != null && value < 0 ? 50 + Math.max(-1, value) * 50 : 50}%`,
                width: `${Math.min(1, Math.abs(value || 0)) * 50}%`,
              }}
            />
          </div>
          <span>
            {value == null
              ? "N/A"
              : `${value > 0 ? "+" : ""}${value.toFixed(2)}`}
          </span>
        </div>
      ))}
    </div>
  );
}
export function TrendHistory({ data }: { data?: TrendingResult }) {
  if (!data)
    return (
      <section className="card">
        <h3>Latest trend snapshot</h3>
        <p role="status">Waiting for Qloo trend history...</p>
      </section>
    );
  const latest = data.records.reduce<TrendRecord | undefined>(
    (newest, record) => {
      const date = /^\d{4}-\d{2}-\d{2}$/.test(record.date)
        ? new Date(`${record.date}T00:00:00Z`)
        : null;
      if (
        !date ||
        !Number.isFinite(date.getTime()) ||
        date.toISOString().slice(0, 10) !== record.date
      )
        return newest;
      return !newest || record.date > newest.date ? record : newest;
    },
    undefined,
  );
  const historical =
    latest && (!latest.is_recent || data.reason === "historical_only");
  const messages = {
    available: !latest
      ? "No valid observations available"
      : historical
        ? "Historical coverage only"
        : "Latest observation available",
    no_data: "No records for this window",
    unsupported: "Unsupported entity type",
    error:
      data.reason === "request_rejected"
        ? "Request rejected"
        : "Trend history unavailable",
  };
  const zero =
    latest?.population_rank_velocity === 0 &&
    latest.velocity_fold_change === 0 &&
    latest.population_percent_delta === 0;
  const metrics = latest
    ? ([
        ["Population rank", latest.population_rank],
        ["Population percentile (raw)", latest.population_percentile],
        ["Rank velocity", latest.population_rank_velocity],
        ["Fold change (raw)", latest.velocity_fold_change],
        ["Percent delta (raw)", latest.population_percent_delta],
      ] as const)
    : [];
  return (
    <section className="card">
      <div className="section-row">
        <h3>Latest trend snapshot</h3>
        <span className="pill">Global</span>
      </div>
      <p role="status">{messages[data.status]}</p>
      {data.entity && (
        <p>
          {data.entity.name} ·{" "}
          {data.entity.source === "selected_seed"
            ? "Selected campaign seed"
            : "Related cultural reference"}
        </p>
      )}
      {data.entity?.source === "related_reference" && (
        <p>
          Connected to {data.entity.source_seeds?.map((s) => s.name).join(", ")}{" "}
          through Qloo Insights
          {data.entity.affinity != null
            ? ` · affinity ${data.entity.affinity.toFixed(3)}`
            : ""}
          . This reference does not replace your selected seeds.
        </p>
      )}
      {latest && (
        <p>
          Observation date: <time dateTime={latest.date}>{latest.date}</time>
          {historical && " · Historical observation"}
        </p>
      )}
      {zero && (
        <p>Qloo reports zero change in this observation's movement metrics.</p>
      )}
      {!!metrics.length && (
        <>
          <dl className="trend-snapshot">
            {metrics.map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>
                  {value == null || !Number.isFinite(value)
                    ? "Unavailable"
                    : label === "Population rank"
                      ? value.toLocaleString("en-US")
                      : Number(value.toPrecision(6)).toString()}
                </dd>
              </div>
            ))}
          </dl>
          <p className="muted">
            Qloo's reported scale. Measurements are global; coverage may be
            incomplete.
          </p>
        </>
      )}
      <details>
        <summary>Trend sources and request evidence</summary>
        <p>
          Requested recent window: {data.recent_window.start_date} to{" "}
          {data.recent_window.end_date}.
        </p>
        {data.returned_date_range && (
          <p>
            Returned records: {data.returned_date_range.start_date} to{" "}
            {data.returned_date_range.end_date} · {data.recent_record_count}{" "}
            within the recent window.
          </p>
        )}
        {data.broader_window_used && (
          <p>A broader history request was needed to retrieve these records.</p>
        )}
        <pre className="json">{JSON.stringify(data, null, 2)}</pre>
      </details>
    </section>
  );
}
export function AudienceView({
  data,
  trending,
}: {
  data?: Audience;
  trending?: TrendingResult;
}) {
  if (!data) return <Waiting label="Connecting the taste graph" />;
  const d = data.demographics;
  return (
    <>
      <div className="artifact-heading">
        <span className="eyebrow">AUDIENCE INTELLIGENCE</span>
        <h2>Affinity beyond demographics.</h2>
        <p>
          Qloo affinity scores describe cultural alignment, not audience
          percentages or conversion probabilities.
        </p>
      </div>
      <section className="card">
        <h3>Demographic cohort lift · Global seed profile</h3>
        <p className="muted">
          {d.aggregation_method ||
            "Mean of available seed scores, not a combined-audience estimate."}
        </p>
        {d.coverage && (
          <p role="status">
            Coverage: {d.coverage.returned} of {d.coverage.requested} selected
            seeds.{" "}
            {d.coverage.missing_seeds.length > 0 &&
              `No demographic data returned for ${d.coverage.missing_seeds.map((s) => s.name).join(", ")}.`}
          </p>
        )}
        {!Object.keys(d.aggregate_age).length && (
          <p>No seed demographic data returned.</p>
        )}
        <Lift values={d.aggregate_age} />
        <Lift values={d.aggregate_gender} />
        <div className="cohorts">
          <div>
            <h4>Positive signals</h4>
            {d.top_positive_cohorts.map((c) => (
              <span className="pill positive" key={c.cohort}>
                {c.label} +{c.lift.toFixed(2)}
              </span>
            ))}
          </div>
          <div>
            <h4>Below-average alignment</h4>
            <p className="muted">
              Scores below -0.15, flagged by Advibe. These are not audience
              exclusions.
            </p>
            {d.excluded_cohorts.map((c) => (
              <span className="pill negative" key={c.cohort}>
                {c.label} {c.lift.toFixed(2)}
              </span>
            ))}
          </div>
        </div>
        <details>
          <summary>Per-seed breakdown</summary>
          {d.all_seed_blocks.map((s) => (
            <div key={s.name}>
              <h4>{s.name}</h4>
              <Lift values={s.age} />
              <Lift values={s.gender} />
            </div>
          ))}
        </details>
        {!!d.tag_blocks?.length && (
          <details>
            <summary>
              Verified tag demographic profiles (separate from seed mean)
            </summary>
            {d.tag_blocks.map((t) => (
              <div key={t.entity_id}>
                <h4>{t.entity_id.split(":").at(-1)?.replaceAll("_", " ")}</h4>
                <Lift values={t.query.age || {}} />
                <Lift values={t.query.gender || {}} />
              </div>
            ))}
          </details>
        )}
        <p className="muted">
          {d.targeting_method ||
            "Campaign age ranges and gender settings are Advibe planning heuristics."}
        </p>
      </section>
      <section className="card">
        <h3>Taste vocabulary</h3>
        <p className="muted">
          {data.provenance?.taste_scope === "seed_fallback"
            ? "Taste discovery returned no results. Showing verified input tags without measured affinities."
            : data.provenance
              ? `Ranked using the selected entities, verified taste tags, and a location signal for ${data.provenance.location_query}.`
              : "Qloo tag affinity scores. Geographic scope was not recorded for this session."}{" "}
          Affinity ranges from 0 to 1.
        </p>
        <Pills items={data.taste_vocabulary} />
      </section>
      <section className="card">
        <h3>
          Competitor contrast{" "}
          {data.compare ? `· ${data.compare.competitor_name}` : ""}
        </h3>
        {data.compare ? (
          <>
            <p className="muted">
              {data.compare.interpretation ||
                "Global descriptive metadata overlap between the selected entities, not measured audience exclusivity."}
            </p>
            {data.compare.mixed_entity_types && (
              <p>
                Mixed entity types: this comparison includes different catalog
                categories, such as places and brands.
              </p>
            )}
            <h4>Shared metadata tags</h4>
            <Pills items={data.compare.shared_tags} />
            <h4>Tags returned only for our selected references</h4>
            <Pills
              items={data.compare.all_a_only_tags || data.compare.a_only_tags}
            />
            <h4>Tags returned only for the competitor</h4>
            <Pills
              items={data.compare.all_b_only_tags || data.compare.b_only_tags}
            />
          </>
        ) : (
          <p className="muted">No competitor comparison returned.</p>
        )}
      </section>
      <TrendHistory
        data={
          trending ||
          (data.trending && "scope" in data.trending
            ? data.trending
            : undefined)
        }
      />
      {data.provenance && (
        <section className="card">
          <details>
            <summary>Signal sources and request evidence</summary>
            <p>Selected Qloo entities</p>
            {data.provenance.seed_entities.map((e) => (
              <p key={e.entity_id}>
                {e.name} · {e.subtype.replace("urn:entity:", "")}
                <br />
                <code>{e.entity_id}</code>
              </p>
            ))}
            <p>Verified input tags</p>
            <Pills items={data.provenance.verified_tags} />
            <pre className="json">
              {JSON.stringify(data.provenance.calls, null, 2)}
            </pre>
          </details>
        </section>
      )}
    </>
  );
}
export function Campaigns({
  session,
  selected,
  onSelect,
}: {
  session: Session;
  selected: string[];
  onSelect: (id: string) => void;
}) {
  const strategies = session.artifacts.strategies;
  if (!strategies) return <Waiting label="Building your cultural tribes" />;
  return (
    <>
      <div className="artifact-heading">
        <span className="eyebrow">CAMPAIGN STRATEGIES</span>
        <h2>Your ways into the culture.</h2>
        <p>
          Distinct audiences, local signals, and a creative direction for each.
        </p>
        <span className="pill">
          {selected.length} of {strategies.length} selected
        </span>
      </div>
      {strategies.map((s, i) => {
        const packet =
          s.packet ||
          session.artifacts.packets?.find((p) => p.strategy_id === s.id);
        return (
          <article
            className={`card campaign ${selected.includes(s.id) ? "selected" : ""}`}
            key={s.id}
          >
            <div className="campaign-top">
              <span className="eyebrow">TRIBE 0{i + 1}</span>
              <span className="pill">{s.id}</span>
            </div>
            <label className="tribe-title">
              <input
                type="checkbox"
                checked={selected.includes(s.id)}
                onChange={() => onSelect(s.id)}
              />
              <h2>{s.tribe_name}</h2>
            </label>
            {s.location_query && (
              <span className="pill">{s.location_query}</span>
            )}
            {s.location_variants ? (
              <>
                <p>{s.strategic_angle}</p>
                <p className="muted">{s.qloo_grounding_summary}</p>
                {s.location_variants.map((variant) => (
                  <details className="city-variant" key={variant.location_id}>
                    <summary>
                      {variant.location_query}{" "}
                      <span className="pill">Localized execution</span>
                    </summary>
                    <h3>{variant.tribe_name}</h3>
                    <StrategyDetails s={variant} packet={variant.packet} />
                  </details>
                ))}
              </>
            ) : (
              <StrategyDetails s={s} packet={packet} />
            )}
          </article>
        );
      })}
    </>
  );
}

function StrategyDetails({ s, packet }: { s: Strategy; packet?: Packet }) {
  const spec = s.meta_adset_spec;
  const prompt = s.cultural_system_prompt;
  if (!spec || !prompt) return null;
  return (
    <>
      <p>{s.strategic_angle}</p>
      <h4>Qloo grounding</h4>
      <p className="grounding">{s.qloo_grounding_summary}</p>
      {packet &&
        (
          [
            ["Artists", packet.artists],
            ["Films", packet.movies],
            ["Venues", packet.venues],
            ["Podcasts", packet.podcasts],
            ["Brands", packet.brands],
            ["Taste tags", packet.taste_tags],
          ] as [string, (Place | Tag)[]][]
        ).map(([name, items]) => (
          <div className="signal-group" key={name}>
            <span className="muted">{name}</span>
            <Pills items={items} />
          </div>
        ))}
      {packet?.compare && (
        <>
          <h4>Competitor divergence</h4>
          <Pills items={packet.compare.a_only_tags} />
        </>
      )}
      <details className="prompt-block">
        <summary>
          Cultural System Prompt{" "}
          <span className="pill">
            {prompt.trim().split(/\s+/).length} words
          </span>
        </summary>
        <CopyButton text={prompt} />
        <p className="preserve">{prompt}</p>
      </details>
      <div className="meta-spec">
        <div className="section-row">
          <h4>Meta Ad Set Spec</h4>
          <span className="pill">{spec.status}</span>
        </div>
        <p>{spec.name}</p>
        <div className="spec-grid">
          <div>
            <small>AGE RANGE</small>
            <p>
              {spec.age_min}-{spec.age_max}
            </p>
          </div>
          <div>
            <small>GENDERS</small>
            <p>
              {spec.genders
                .map((g) => (g === 1 ? "Men" : g === 2 ? "Women" : String(g)))
                .join(", ") || "All"}
            </p>
          </div>
        </div>
        {spec.geo_locations.custom_locations.map((l, i) => (
          <p className="muted" key={i}>
            {l.latitude}, {l.longitude} · {l.radius.toFixed(1)}{" "}
            {l.distance_unit} radius
          </p>
        ))}
      </div>
    </>
  );
}
