import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import {
  ArrowUp,
  ArrowUpRight,
  ArrowLeft,
  ChevronRight,
  PanelRightClose,
  PanelRightOpen,
  Check,
  LoaderCircle,
  Sparkles,
  Globe,
  Activity,
  Layers,
} from "lucide-react";
import {
  consumeSSE,
  initialSession,
  jsonRequest,
  sessionReducer,
  sessionRequest,
} from "./stream";
import type {
  AskRequest,
  AskResponse,
  Entity,
  Preset,
  TribeScope,
} from "./types";
import { AudienceView, Campaigns, Geo, Pills } from "./Artifacts";
import { PresetSelector } from "./PresetSelector";
import { useCreativeExecution } from "./creativeExecution";
import {
  CreativeControls,
  CreativeTimeline,
  CreativeArtifacts,
  MetaArtifacts,
} from "./CreativeWorkspace";
const tabs = [
  { name: "Tribe Campaigns", icon: Layers },
  { name: "Geo-Heatmap & Venues", icon: Globe },
  { name: "Audience & Taste Graph", icon: Activity },
  { name: "Ad Creatives", icon: Sparkles },
  { name: "Meta Campaign (Staged)", icon: Layers },
];
export default function App() {
  const [presets, setPresets] = useState<Preset[]>([]),
    [presetError, setPresetError] = useState("");
  const [ask, setAsk] = useState<AskResponse | null>(null),
    [history, setHistory] = useState<{ role: string; text: string }[]>([]),
    [input, setInput] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [crafted, setCrafted] = useState("");
  const [seeds, setSeeds] = useState<Entity[]>([]),
    [competitors, setCompetitors] = useState<Entity[]>([]),
    [location, setLocation] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState(false),
    [collapsed, setCollapsed] = useState(false),
    [tab, setTab] = useState(0),
    [selected, setSelected] = useState<string[]>([]),
    [activeCity, setActiveCity] = useState("");
  const [session, dispatch] = useReducer(
    sessionReducer,
    undefined,
    initialSession,
  );
  const [run, setRun] = useState(0);
  const creativeGrounding = useMemo(
    () =>
      session.output
        ? {
            ...session.output,
            packets: session.output.packets || session.artifacts.packets,
          }
        : null,
    [session.output, session.artifacts.packets],
  );
  const execution = useCreativeExecution(creativeGrounding, selected);
  const abort = useRef<AbortController | null>(null);
  const lastRequest = useRef<AskRequest | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    jsonRequest<{ presets: Preset[] }>("/api/presets")
      .then((v) => setPresets(v.presets))
      .catch((e) => setPresetError(e.message));
    return () => abort.current?.abort();
  }, []);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history, busy]);
  async function askTurn(prompt = input, retry = false, scope?: TribeScope) {
    if (busy) return;
    const request =
      retry && lastRequest.current
        ? lastRequest.current
        : {
            prompt: prompt.trim() || null,
            state: ask?.state || null,
            selected_seeds: seeds,
            selected_competitors: competitors,
            selected_location: location,
            ...(scope ? { selected_tribe_scope: scope } : {}),
          };
    if (
      !request.prompt &&
      !request.selected_seeds.length &&
      !request.selected_competitors.length &&
      !request.selected_location &&
      !request.selected_tribe_scope
    )
      return;
    lastRequest.current = request;
    setBusy(true);
    setError("");
    if (!retry)
      setHistory((h) => [
        ...h,
        {
          role: "You",
          text: [
            request.prompt,
            ...request.selected_seeds.map((x) => x.name),
            ...request.selected_competitors.map(
              (x) => `Compare against ${x.name}`,
            ),
            request.selected_location,
            request.selected_tribe_scope
              ? request.selected_tribe_scope === "overall"
                ? "3 tribes total across all cities"
                : "3 tribes per city"
              : null,
          ]
            .filter(Boolean)
            .join(" · "),
        },
      ]);
    try {
      const result = await jsonRequest<AskResponse>("/api/ask", request);
      setAsk(result);
      setCrafted(result.crafted_prompt);
      setHistory((h) => [
        ...h,
        { role: "advibe", text: result.assistant_message },
      ]);
      setInput("");
      setSeeds([]);
      setCompetitors([]);
      setLocation(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to curate prompt.");
    } finally {
      setBusy(false);
    }
  }
  function start() {
    if (!ask || busy || !crafted.trim()) return;
    abort.current?.abort();
    execution.reset();
    dispatch({ type: "reset" });
    setWorkspace(true);
    setSelected([]);
    setActiveCity("");
    setRun((r) => r + 1);
  }
  useEffect(() => {
    if (!run || !ask) return;
    const controller = new AbortController();
    abort.current = controller;
    let terminal = false;
    const request = sessionRequest(
      crafted,
      ask.crafted_prompt,
      ask.resolved_signals,
    );
    (async () => {
      try {
        const r = await fetch(request.url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(request.body),
          signal: controller.signal,
        });
        if (!r.ok || !r.body)
          throw new Error(`Session request failed (${r.status}).`);
        await consumeSSE(r.body, (e) => {
          if (controller.signal.aborted) return;
          if (e.type === "complete" || e.type === "error") terminal = true;
          dispatch(e);
        });
        if (!terminal && !controller.signal.aborted)
          throw new Error(
            "The stream ended early. Restart the session to try again.",
          );
      } catch (e) {
        if (!controller.signal.aborted)
          dispatch({
            type: "error",
            timestamp: Date.now() / 1000,
            error_type: "StreamError",
            message: e instanceof Error ? e.message : "Session interrupted.",
          });
      }
    })();
    return () => controller.abort();
    // A run snapshots the reviewed Ask result and prompt until explicitly restarted.
  }, [run]);
  const toggle = (items: Entity[], entity: Entity) =>
    items.some((x) => x.entity_id === entity.entity_id)
      ? items.filter((x) => x.entity_id !== entity.entity_id)
      : [...items, entity];
  const campaignSignals =
    (workspace && session.artifacts.resolved_signals) || ask?.resolved_signals;
  const targetLocations =
    campaignSignals?.locations ||
    (campaignSignals?.location_query
      ? [
          {
            location_query: campaignSignals.location_query,
            neighborhood_hints: [],
          },
        ]
      : []);
  const scope = campaignSignals?.tribe_scope || "overall";
  const expectedCount =
    scope === "per_location" ? targetLocations.length * 3 : 3;
  const cityIds = Object.keys(session.cityArtifacts);
  const cityId = cityIds.includes(activeCity) ? activeCity : cityIds[0];
  const visibleArtifacts = cityId
    ? session.cityArtifacts[cityId]
    : session.artifacts;
  const hasDraft = !!(
    seeds.length ||
    competitors.length ||
    location ||
    input.trim()
  );
  const resetSession = () => {
    setWorkspace(false);
    setRun(0);
    abort.current?.abort();
  };
  const renderComposer = () => (
    <form
      className="composer"
      onSubmit={(e) => {
        e.preventDefault();
        void askTurn();
      }}
    >
      <textarea
        aria-label="Campaign prompt"
        disabled={busy}
        placeholder={
          ask
            ? "Add a signal, change the city, or refine your brief..."
            : "Describe your brand, your audience, your ambition..."
        }
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            void askTurn();
          }
        }}
      />
      <div className="composer-bottom">
        <span>
          <Sparkles size={14} />{" "}
          {busy
            ? "Verifying signals with Qloo..."
            : "A little context. A whole cultural world."}
        </span>
        <button
          className="send"
          type="submit"
          disabled={
            busy ||
            (!input.trim() && !seeds.length && !competitors.length && !location)
          }
          aria-label="Send prompt"
        >
          {busy ? (
            <LoaderCircle className="spin" size={19} />
          ) : (
            <ArrowUp size={20} />
          )}
        </button>
      </div>
    </form>
  );
  return (
    <div className={workspace ? "app workspace-app" : "app"}>
      <header className="header">
        <a href="/" className="wordmark" aria-label="advibe home">
          ad<span>vibe</span>
          <span className="brand-dot">✳</span>
        </a>
        <div className="header-center">
          {workspace
            ? "CAMPAIGN WORKSPACE"
            : "CULTURAL INTELLIGENCE, ACTIVATED."}
        </div>
        <span className="connection">
          <i /> Powered by Qloo
        </span>
      </header>
      {!workspace ? (
        <main className={`curation ${history.length ? "has-thread" : ""}`}>
          {!history.length ? (
            <>
              <div className="intro">
                <span className="eyebrow">
                  <span className="tiny-star">✳</span> FROM CULTURE TO CAMPAIGN
                </span>
                <h1>
                  Find your people.
                  <br />
                  <span>Move their world.</span>
                </h1>
                <p>
                  Turn your brand into a cultural signal.
                  <br />
                  Build campaigns around what your audience actually loves.
                </p>
              </div>
              {renderComposer()}
              <div className="quick-start">
                <span className="eyebrow">A PLACE TO START</span>
                <PresetSelector
                  presets={presets}
                  busy={busy}
                  onSelect={(prompt) => askTurn(prompt)}
                />
                {presetError && (
                  <p role="alert" className="error">
                    Presets unavailable. You can still enter your brief.
                  </p>
                )}
              </div>
              <div className="entry-footer">
                <span>01 &nbsp; Curate the brief</span>
                <ChevronRight size={12} />
                <span>02 &nbsp; Ground in culture</span>
                <ChevronRight size={12} />
                <span>03 &nbsp; Meet your tribes</span>
              </div>
            </>
          ) : (
            <>
              <div className="thread-heading">
                <span className="eyebrow">CAMPAIGN SCOPING</span>
                <h2>
                  A strong campaign starts
                  <br />
                  with the right signals.
                </h2>
              </div>
              <div className="thread">
                {history.map((m, i) => (
                  <div
                    className={`message ${m.role === "You" ? "user" : "assistant"}`}
                    key={i}
                  >
                    <span className="avatar">
                      {m.role === "You" ? "Y" : "✳"}
                    </span>
                    <div>
                      <span className="message-role">{m.role}</span>
                      <p>{m.text}</p>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
          {ask && (
            <>
              <section className="readiness card">
                <div className="section-row">
                  <h3>Qloo readiness</h3>
                  <span className="pill">
                    {4 - ask.missing_pillars.length} / 4 signals locked
                  </span>
                </div>
                <div className="pillars">
                  {[
                    [
                      "brand_and_product",
                      "Brand & Product",
                      [ask.state.brand_name, ask.state.product_description]
                        .filter(Boolean)
                        .join(" · "),
                    ],
                    [
                      "location",
                      "Target Location",
                      targetLocations.map((l) => l.location_query).join("; "),
                    ],
                    [
                      "seeds",
                      "Cultural Seeds (2+)",
                      ask.resolved_signals.resolved_entities.seed
                        .map((x) => x.name)
                        .join(", "),
                    ],
                    [
                      "competitor",
                      "Competitor (1+)",
                      ask.resolved_signals.resolved_entities.competitors
                        .map((x) => x.name)
                        .join(", "),
                    ],
                  ].map(([id, title, value]) => (
                    <div
                      className={`pillar ${ask.missing_pillars.includes(id!) ? "missing" : "locked"}`}
                      key={id}
                    >
                      <span className="pillar-status">
                        {ask.missing_pillars.includes(id!) ? (
                          "○"
                        ) : (
                          <Check size={14} />
                        )}
                      </span>
                      <h4>{title}</h4>
                      <p>{value || "Waiting for a signal"}</p>
                      <div className="pillar-line" />
                    </div>
                  ))}
                </div>
              </section>
              {!ask.ready_for_session && (
                <section className="suggestions">
                  <span className="eyebrow">
                    VERIFIED SUGGESTIONS · PICK A FEW
                  </span>
                  {[
                    ["location", "Target city", ask.suggestions.locations],
                    ["seeds", "Cultural inspirations", ask.suggestions.seeds],
                    ["competitor", "Competitor", ask.suggestions.competitors],
                  ].map(([key, title, values]) => {
                    if (!ask.missing_pillars.includes(key as string))
                      return null;
                    return (
                      <div key={key as string}>
                        <h4>{title as string}</h4>
                        <div className="pills">
                          {(values as (string | Entity)[]).map((v) => {
                            const entity = typeof v === "string" ? null : v;
                            const active = entity
                              ? (key === "seeds" ? seeds : competitors).some(
                                  (x) => x.entity_id === entity.entity_id,
                                )
                              : location === v;
                            return (
                              <button
                                className={`suggestion ${active ? "active" : ""}`}
                                disabled={busy}
                                key={entity?.entity_id || String(v)}
                                title={
                                  entity
                                    ? `${entity.subtype} · ${entity.entity_id}`
                                    : String(v)
                                }
                                onClick={() =>
                                  entity
                                    ? key === "seeds"
                                      ? setSeeds(toggle(seeds, entity))
                                      : setCompetitors(
                                          toggle(competitors, entity),
                                        )
                                    : setLocation(
                                        location === v ? null : String(v),
                                      )
                                }
                              >
                                {active && <Check size={13} />}{" "}
                                {entity?.name || String(v)}{" "}
                                {entity && (
                                  <small>
                                    {entity.subtype.split(":").pop()}
                                  </small>
                                )}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                  <button
                    className="primary"
                    disabled={busy || !hasDraft}
                    onClick={() => askTurn()}
                  >
                    Continue with signals <ArrowUpRight size={15} />
                  </button>
                </section>
              )}
              {targetLocations.length > 1 && (
                <section className="card" aria-label="Tribe count preference">
                  <h3>How many cultural tribes?</h3>
                  <p>
                    Default: 3 tribes total across all cities, with localized
                    execution for each city.
                  </p>
                  <div className="pills scope-controls">
                    <button
                      aria-pressed={scope === "overall"}
                      className={scope === "overall" ? "primary" : ""}
                      disabled={busy || hasDraft}
                      onClick={() => askTurn("", false, "overall")}
                    >
                      3 total
                    </button>
                    <button
                      aria-pressed={scope === "per_location"}
                      className={scope === "per_location" ? "primary" : ""}
                      disabled={busy || hasDraft}
                      onClick={() => askTurn("", false, "per_location")}
                    >
                      3 per city
                    </button>
                  </div>
                  <p className="muted">
                    {expectedCount} tribes across {targetLocations.length}{" "}
                    cities. You can start with this setting without another
                    reply.
                  </p>
                </section>
              )}
              {ask.ready_for_session && !busy && (
                <section className="ready-card card">
                  <span className="eyebrow">
                    <Check size={14} /> YOUR CURATED CAMPAIGN PROMPT
                  </span>
                  <textarea
                    aria-label="Curated campaign prompt"
                    value={crafted}
                    onChange={(e) => setCrafted(e.target.value)}
                  />
                  <div className="pills">
                    {[
                      ...ask.resolved_signals.resolved_entities.seed,
                      ...ask.resolved_signals.resolved_entities.competitors,
                    ].map((e) => (
                      <span
                        className="pill"
                        key={e.entity_id}
                        title={`${e.entity_id} · ${e.subtype}`}
                      >
                        {e.name} <small>{e.subtype.split(":").pop()}</small>
                      </span>
                    ))}
                    {targetLocations.map((l) => (
                      <span className="pill" key={l.location_query}>
                        {l.location_query}
                      </span>
                    ))}
                  </div>
                  <Pills items={ask.resolved_signals.resolved_tags} />
                  {ask.resolved_signals.resolved_entities.seed.some(
                    (e) => e.subtype === "urn:entity:place",
                  ) && (
                    <p className="muted">
                      {ask.resolved_signals.resolved_entities.seed
                        .filter((e) => e.subtype === "urn:entity:place")
                        .map((e) => e.name)
                        .join(", ")}{" "}
                      resolved as a specific Qloo place. Its signals describe
                      that venue; you can change the reference before starting.
                    </p>
                  )}
                  <details>
                    <summary>Insights tag identifiers</summary>
                    <p className="preserve">
                      {ask.resolved_signals.insights_tags.join("\n")}
                    </p>
                  </details>
                  <div className="ready-footer">
                    <p>
                      Ready to build the cultural intelligence
                      <br />
                      around this campaign? {expectedCount} tribes ·{" "}
                      {targetLocations.length}{" "}
                      {targetLocations.length === 1 ? "city" : "cities"}.
                    </p>
                    <button
                      className="primary"
                      disabled={hasDraft || !crafted.trim()}
                      onClick={start}
                    >
                      Start Session <ArrowUpRight size={16} />
                    </button>
                  </div>
                  {hasDraft && (
                    <p className="muted">
                      Send or clear your pending changes before starting.
                    </p>
                  )}
                </section>
              )}
            </>
          )}
          {busy && (
            <p className="working" role="status">
              <LoaderCircle size={16} className="spin" /> Listening, resolving,
              connecting the dots...
            </p>
          )}
          {error && (
            <div className="error" role="alert">
              {error} <button onClick={() => askTurn("", true)}>Retry</button>
            </div>
          )}
          {history.length > 0 && (
            <div className="follow-up">
              {renderComposer()}
              <p className="composer-hint">
                Enter to send · Shift + Enter for a new line
              </p>
            </div>
          )}
          <div ref={bottom} />
        </main>
      ) : (
        <main className={`workspace ${collapsed ? "collapsed" : ""}`} key={run}>
          <section className="execution">
            <button className="back" onClick={resetSession}>
              <ArrowLeft size={14} /> Back to brief
            </button>
            <div className="session-heading">
              <span className="eyebrow">
                SESSION {String(run).padStart(2, "0")}
              </span>
              <h2>
                {ask?.state.brand_name || "Campaign"}{" "}
                <span>
                  · {targetLocations.map((l) => l.location_query).join("; ")}
                </span>
              </h2>
              <span className={`session-status ${session.status}`}>
                <i />
                {execution.state.status === "running"
                  ? "Executing creatives & staging Meta..."
                  : execution.state.status === "complete"
                    ? "Checkpoint: Review staged campaign"
                    : session.status === "error"
                      ? "Session interrupted"
                      : session.status === "running"
                        ? "Running Qloo Grounding..."
                        : "Checkpoint: Select Tribes"}
              </span>
            </div>
            <details className="locked-brief" open>
              <summary>
                Curated campaign prompt <span className="pill">Locked</span>
              </summary>
              <p>{crafted}</p>
            </details>
            <div className="timeline">
              {session.steps.length === 0 && session.status === "running" && (
                <p className="working">
                  <LoaderCircle size={16} className="spin" /> Connecting to the
                  session...
                </p>
              )}
              {session.steps.map((step, i) => (
                <div className="timeline-step" key={`${step.phase}-${i}`}>
                  <span className={`step-marker ${step.end ? "done" : ""}`}>
                    {step.end ? (
                      <Check size={13} />
                    ) : (
                      <LoaderCircle
                        size={16}
                        className={session.status === "running" ? "spin" : ""}
                      />
                    )}
                  </span>
                  <div>
                    <div className="section-row">
                      <span className="eyebrow">
                        {step.phase.replaceAll("_", " ")}
                      </span>
                      {step.end && (
                        <small>
                          {Math.max(0, step.end - step.start).toFixed(1)}s
                        </small>
                      )}
                    </div>
                    {step.location_id && (
                      <span className="pill">
                        {session.cityLabels[step.location_id]}
                      </span>
                    )}
                    <p>{step.verb}</p>
                    {step.phase === "qloo_fanout" && (
                      <div className="call-badges">
                        {Object.values(session.calls)
                          .filter((c) => c.location_id === step.location_id)
                          .map((c) => (
                            <span
                              className={`call ${c.status}`}
                              key={c.call_id || c.name}
                              title={[
                                c.entity?.name,
                                c.window
                                  ? `${c.window.start_date} to ${c.window.end_date}`
                                  : "",
                                c.reason,
                                c.http_status != null
                                  ? `HTTP ${c.http_status}`
                                  : "",
                                c.cached ? "Cached for this session" : "",
                              ]
                                .filter(Boolean)
                                .join(" · ")}
                            >
                              {c.status === "running" ? (
                                <LoaderCircle size={12} className="spin" />
                              ) : (
                                <span>{c.status === "ok" ? "✓" : "○"}</span>
                              )}
                              {c.name}
                              {c.entity &&
                                ` · ${c.entity.name} (${c.window_kind || "recorded window"})`}
                              <small>
                                {c.status === "running"
                                  ? "running"
                                  : `${c.status}${c.duration_ms != null ? ` · ${c.duration_ms}ms` : ""}`}
                              </small>
                            </span>
                          ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
            <CreativeTimeline state={execution.state} />
            {session.status !== "running" && (
              <div
                className={`checkpoint card ${session.status === "error" ? "error" : ""}`}
                role="status"
              >
                <span className="eyebrow">
                  {session.status === "error"
                    ? "INTERRUPTED"
                    : "READY FOR YOUR DIRECTION"}
                </span>
                <h3>
                  {session.status === "error"
                    ? "The session needs another try."
                    : execution.state.status === "complete"
                      ? "Your creative test is staged."
                      : "Your cultural tribes are ready."}
                </h3>
                <p>
                  {execution.state.status === "complete"
                    ? "Review the Ad Creatives and Meta Campaign artifacts. The campaign is staged locally and ready for inspection."
                    : execution.state.status === "running"
                      ? "Selected cultural briefs are being developed into creative bundles and a local campaign draft."
                      : session.message ||
                        "Inspect the campaigns and select the tribes you want to take forward."}
                </p>
                {session.status === "error" ? (
                  <button
                    onClick={() => {
                      start();
                    }}
                  >
                    Restart Session
                  </button>
                ) : (
                  <span className="pill">
                    {selected.length}{" "}
                    {selected.length === 1 ? "tribe" : "tribes"} selected
                  </span>
                )}
              </div>
            )}
          </section>
          <section className="artifact-panel">
            <div className="artifact-toolbar">
              <div>
                <span className="eyebrow">LIVE ARTIFACTS</span>
                <span className="live-dot" />
              </div>
              <button
                aria-label={
                  collapsed ? "Expand artifacts" : "Collapse artifacts"
                }
                onClick={() => setCollapsed(!collapsed)}
              >
                {collapsed ? (
                  <PanelRightOpen size={18} />
                ) : (
                  <PanelRightClose size={18} />
                )}
              </button>
            </div>
            {!collapsed && (
              <>
                <nav className="tabs" aria-label="Artifacts">
                  {tabs.map((t, i) => {
                    const ready = [
                      !!session.artifacts.strategies,
                      !!session.artifacts.geo_pins ||
                        cityIds.some(
                          (id) => !!session.cityArtifacts[id].geo_pins,
                        ),
                      !!session.artifacts.audience_insights ||
                        cityIds.some(
                          (id) => !!session.cityArtifacts[id].audience_insights,
                        ),
                      execution.state.bundles.length > 0,
                      !!execution.state.result?.meta,
                    ][i];
                    return (
                      <button
                        key={t.name}
                        className={tab === i ? "active" : ""}
                        onClick={() => setTab(i)}
                      >
                        <t.icon size={14} />
                        {t.name}
                        {i === 0
                          ? ` (${session.status === "complete" ? session.artifacts.strategies?.length || expectedCount : expectedCount})`
                          : ""}
                        {ready && <i />}
                      </button>
                    );
                  })}
                </nav>
                <div className="artifact-content">
                  {(tab === 1 || tab === 2) && cityIds.length > 0 && (
                    <nav
                      className="pills city-selector"
                      aria-label="Artifact city"
                    >
                      {cityIds.map((id) => (
                        <button
                          key={id}
                          aria-pressed={cityId === id}
                          className={cityId === id ? "primary" : ""}
                          onClick={() => setActiveCity(id)}
                        >
                          {session.cityLabels[id] || id}
                        </button>
                      ))}
                    </nav>
                  )}
                  {tab === 0 && (
                    <>
                      <Campaigns
                        session={session}
                        selected={selected}
                        onSelect={(id) =>
                          setSelected((v) =>
                            v.includes(id)
                              ? v.filter((x) => x !== id)
                              : [...v, id],
                          )
                        }
                      />
                      {(session.status === "complete" ||
                        session.status === "checkpoint") && (
                        <CreativeControls
                          execution={execution}
                          onStart={() => setTab(3)}
                        />
                      )}
                    </>
                  )}
                  {tab === 3 && (
                    <CreativeArtifacts
                      state={execution.state}
                      onRetry={
                        execution.state.result && !execution.changed
                          ? () => {
                              execution.run(true);
                            }
                          : undefined
                      }
                    />
                  )}
                  {tab === 4 && <MetaArtifacts state={execution.state} />}
                  {tab === 1 && <Geo artifacts={visibleArtifacts} />}
                  {tab === 2 && (
                    <>
                      <section className="signal-strip">
                        <span className="eyebrow">LOCKED CULTURAL SEEDS</span>
                        <Pills
                          items={
                            (
                              session.artifacts.resolved_signals ||
                              ask?.resolved_signals
                            )?.resolved_entities.seed || []
                          }
                        />
                      </section>
                      <AudienceView
                        data={visibleArtifacts.audience_insights}
                        trending={visibleArtifacts.trending}
                      />
                    </>
                  )}
                </div>
              </>
            )}
          </section>
        </main>
      )}
      <footer className="site-footer">
        <span>advibe</span>
        <span>Cultural intelligence → Campaign precision</span>
        <span>Built on Qloo's Taste Graph</span>
      </footer>
    </div>
  );
}
