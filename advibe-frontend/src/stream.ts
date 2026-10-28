import type { Artifacts, Output, StreamEvent } from "./types";
export async function consumeSSE(
  body: ReadableStream<Uint8Array>,
  onEvent: (e: StreamEvent) => void,
) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  function frame(raw: string) {
    const data = raw
      .split("\n")
      .filter((l) => l.startsWith("data:"))
      .map((l) => l.slice(5).trimStart())
      .join("\n");
    if (data) onEvent(JSON.parse(data));
  }
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      buffer = buffer.replace(/\r\n/g, "\n");
      let end;
      while ((end = buffer.indexOf("\n\n")) >= 0) {
        frame(buffer.slice(0, end));
        buffer = buffer.slice(end + 2);
      }
      if (done) {
        if (buffer.trim()) frame(buffer);
        break;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
export type Session = {
  artifacts: Artifacts;
  cityArtifacts: Record<string, Artifacts>;
  cityLabels: Record<string, string>;
  steps: {
    location_id?: string;
    phase: string;
    verb: string;
    start: number;
    end?: number;
  }[];
  calls: Record<string, Extract<StreamEvent, { type: "qloo_call" }>>;
  events: StreamEvent[];
  status: "running" | "checkpoint" | "complete" | "error";
  message?: string;
  output?: Output;
};
export const initialSession = (): Session => ({
  artifacts: {},
  cityArtifacts: {},
  cityLabels: {},
  steps: [],
  calls: {},
  events: [],
  status: "running",
});
export function sessionReducer(
  state: Session,
  e: StreamEvent | { type: "reset" },
): Session {
  if (e.type === "reset") return initialSession();
  const next = { ...state, events: [...state.events, e] };
  if (e.location_id && e.location_query)
    next.cityLabels = {
      ...state.cityLabels,
      [e.location_id]: e.location_query,
    };
  if (e.type === "artifact_patch") {
    if (e.location_id)
      next.cityArtifacts = {
        ...state.cityArtifacts,
        [e.location_id]: {
          ...state.cityArtifacts[e.location_id],
          [e.artifact]: e.data,
        },
      };
    else next.artifacts = { ...state.artifacts, [e.artifact]: e.data };
  }
  if (e.type === "phase_change")
    next.steps = [
      ...state.steps.map((s) =>
        s.end === undefined ? { ...s, end: e.timestamp } : s,
      ),
      {
        location_id: e.location_id,
        phase: e.phase,
        verb: e.spinner_verb,
        start: e.timestamp,
      },
    ];
  if (e.type === "qloo_call")
    next.calls = {
      ...state.calls,
      [`${e.location_id || "global"}:${e.call_id || e.name}`]: e,
    };
  if (e.type === "checkpoint" || e.type === "complete") {
    next.status = e.type;
    next.output = e.data;
    next.artifacts = { ...state.artifacts, strategies: e.data.strategies };
    next.steps = state.steps.map((s) =>
      s.end === undefined ? { ...s, end: e.timestamp } : s,
    );
    if (e.type === "checkpoint") next.message = e.spinner_verb;
  }
  if (e.type === "error") {
    next.status = "error";
    next.message = e.message;
    next.steps = state.steps.map((s) =>
      s.end === undefined ? { ...s, end: e.timestamp } : s,
    );
  }
  return next;
}
export async function jsonRequest<T>(url: string, data?: unknown): Promise<T> {
  const r = await fetch(
    url,
    data === undefined
      ? undefined
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        },
  );
  if (!r.ok) throw new Error(`Request failed (${r.status}). Please try again.`);
  return r.json();
}
export function sessionRequest(
  prompt: string,
  askPrompt: string,
  signals: Artifacts["resolved_signals"],
) {
  return prompt.trim() === askPrompt.trim()
    ? {
        url: "/api/session/stream",
        body: {
          resolved_signals: signals,
          prompt,
          location: signals?.location_query,
        },
      }
    : {
        url: "/api/grounding/stream",
        body: {
          prompt,
          location: signals?.locations?.length
            ? undefined
            : signals?.location_query,
          locations: signals?.locations,
          tribe_scope: signals?.tribe_scope,
        },
      };
}
