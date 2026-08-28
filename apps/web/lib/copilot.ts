/**
 * Copilot client: transcript types, the SSE-over-POST reply stream, and the
 * citation helpers the sidebar renders `[calc:…]` / `[campaign:…]` tokens with.
 */

import { apiFetch } from "./api";

export type ToolPart = {
  type: "tool";
  id: string;
  name: string;
  args: Record<string, unknown>;
  result: unknown;
  ok: boolean | null;
};
export type TextPart = { type: "text"; text: string };
export type PatchPart = {
  type: "patch";
  patch: Record<string, unknown>;
  rationale: string;
};
export type AssistantPart = ToolPart | TextPart | PatchPart;

export type Turn =
  | { role: "user"; text: string }
  | { role: "assistant"; parts: AssistantPart[]; streaming?: boolean };

export type PageContext = {
  page: "new_campaign" | "campaign" | "other";
  campaign_id?: string | null;
  form?: Record<string, unknown> | null;
};

export type StreamEvent =
  | { type: "text"; delta: string }
  | { type: "tool_call"; id: string; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; id: string; name: string; ok: boolean }
  | { type: "patch"; patch: Record<string, unknown>; rationale: string }
  | { type: "done"; transcript: Turn[] }
  | { type: "error"; detail: string };

/** POST a message and yield the copilot's reply events as they arrive. */
export async function* streamReply(
  chatId: string,
  content: string,
  context: PageContext,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const res = await apiFetch(`/copilot/chats/${chatId}/messages`, {
    method: "POST",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    body: JSON.stringify({ content, context }),
    signal,
  });
  if (!res.ok || !res.body) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (body.detail) detail = String(body.detail);
    } catch {
      /* not JSON */
    }
    yield { type: "error", detail };
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let sep = buffer.indexOf("\n\n");
    while (sep !== -1) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const data = block
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("\n");
      if (data) {
        try {
          yield JSON.parse(data) as StreamEvent;
        } catch {
          /* keep-alive or malformed chunk */
        }
      }
      sep = buffer.indexOf("\n\n");
    }
  }
}

/** Apply a stream event to the in-progress assistant turn (mutably, for React state cloning). */
export function applyEvent(turn: Extract<Turn, { role: "assistant" }>, event: StreamEvent) {
  const parts = turn.parts;
  switch (event.type) {
    case "text": {
      const last = parts[parts.length - 1];
      if (last && last.type === "text") last.text += event.delta;
      else parts.push({ type: "text", text: event.delta });
      break;
    }
    case "tool_call":
      parts.push({
        type: "tool",
        id: event.id,
        name: event.name,
        args: event.args,
        result: null,
        ok: null,
      });
      break;
    case "tool_result": {
      const tool = parts.find((p) => p.type === "tool" && p.id === event.id) as
        ToolPart | undefined;
      if (tool) tool.ok = event.ok;
      break;
    }
    case "patch":
      parts.push({ type: "patch", patch: event.patch, rationale: event.rationale });
      break;
  }
}

/** Open a calculation's engine log in a new tab (authenticated fetch → blob URL). */
export async function openCalculationLog(calculationId: string): Promise<boolean> {
  const res = await apiFetch(`/calculations/${calculationId}/log`);
  if (!res.ok) return false;
  const text = await res.text();
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
  return true;
}

/** Tool names → the verb the sidebar shows, and whether it is an eyes- or hands-tool. */
export const TOOL_LABELS: Record<string, { label: string; kind: "eyes" | "hands" }> = {
  list_campaigns: { label: "listed campaigns", kind: "eyes" },
  get_campaign: { label: "read campaign", kind: "eyes" },
  get_report: { label: "read report", kind: "eyes" },
  get_hull: { label: "read hull", kind: "eyes" },
  get_phase_diagram: { label: "read phase diagram", kind: "eyes" },
  get_candidates: { label: "read candidates", kind: "eyes" },
  list_calculations: { label: "listed calculations", kind: "eyes" },
  get_calculation: { label: "inspected calculation", kind: "eyes" },
  list_decisions: { label: "read decision trail", kind: "eyes" },
  list_elements: { label: "read element catalog", kind: "eyes" },
  propose_campaign_params: { label: "proposed form changes", kind: "hands" },
};

/** Human labels for form fields in patch cards. */
export const FIELD_LABELS: Record<string, string> = {
  name: "campaign name",
  problem_type: "problem",
  element_a: "element A",
  element_b: "element B",
  strategy: "strategy",
  simulation_budget: "budget",
  failure_rate: "failure rate",
  target_uncertainty: "uncertainty target",
  dft_engine: "energy engine",
  property_engine: "property engine",
  temperature_threshold: "stability threshold (K)",
  lattice_size: "lattice size",
  temperature_min: "T min",
  temperature_max: "T max",
  phase_t_min: "T min (K)",
  phase_t_max: "T max (K)",
};
