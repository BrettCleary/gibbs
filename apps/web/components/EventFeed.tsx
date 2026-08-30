"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { AgentEvent } from "@gibbs/api-client";
import { api, apiUrlWithToken } from "@/lib/api";
import { cn } from "@/lib/cn";
import { EmptyState, type Tone } from "@/components/ui/primitives";

const TYPE_TONE: Record<string, Tone> = {
  CAMPAIGN_STARTED: "accent",
  AGENT_DECISION: "accent",
  MODEL_UPDATED: "good",
  JOB_SUCCEEDED: "neutral",
  JOB_STARTED: "neutral",
  JOB_FAILED: "bad",
  CAMPAIGN_ERROR: "bad",
  CAMPAIGN_COMPLETED: "good",
};

const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-text-muted",
  accent: "text-accent-bright",
  good: "text-verdigris",
  warn: "text-brass",
  bad: "text-oxide",
};
const TONE_RAIL: Record<Tone, string> = {
  neutral: "bg-steel/50",
  accent: "bg-accent",
  good: "bg-verdigris",
  warn: "bg-brass",
  bad: "bg-oxide",
};

type LiveEvent = Partial<AgentEvent> & {
  id?: string;
  event_type: string;
  created_at: string;
};

/** How a decision was actually produced. The heuristic baselines emit the same
 *  ScientificDecision schema as the LLM scientist, so an argmax over a surrogate
 *  ensemble would otherwise read as model reasoning in this feed. `source` is
 *  per-decision: under strategy "agent" the endpoint bootstrap, the stopping rule
 *  and failure recovery are still code. */
type DecisionProvenance = { source: "code" | "llm" | "unknown"; decider: string | null };

function provenance(e: LiveEvent, strategy?: string): DecisionProvenance {
  const payload = (e.payload ?? {}) as Record<string, unknown>;
  const decider =
    typeof payload.decider_name === "string" ? payload.decider_name : (strategy ?? null);
  const source = payload.source;
  if (source === "code" || source === "llm") return { source, decider };
  // Events written before decisions carried provenance: a non-agent campaign was
  // entirely coded, an agent campaign is a mix we cannot reconstruct.
  if (strategy && strategy !== "agent") return { source: "code", decider };
  return { source: "unknown", decider };
}

export function EventFeed({
  campaignId,
  live,
  strategy,
}: {
  campaignId: string;
  live: boolean;
  strategy?: string;
}) {
  const [liveEvents, setLiveEvents] = useState<LiveEvent[]>([]);
  const seen = useRef(new Set<string>());

  const history = useQuery({
    queryKey: ["agent-events", campaignId],
    queryFn: async () => {
      const { data } = await api.GET("/campaigns/{campaign_id}/agent-events", {
        params: { path: { campaign_id: campaignId } },
      });
      return data ?? [];
    },
    refetchInterval: live ? 4000 : false,
  });

  useEffect(() => {
    if (!live) return;
    const source = new EventSource(apiUrlWithToken(`/campaigns/${campaignId}/events`));
    const handler = (e: MessageEvent) => {
      try {
        const event = JSON.parse(e.data) as LiveEvent;
        if (event.id && seen.current.has(event.id)) return;
        if (event.id) seen.current.add(event.id);
        setLiveEvents((prev) => [...prev, event]);
      } catch {
        /* ignore malformed events */
      }
    };
    const types = [
      "CAMPAIGN_STARTED",
      "AGENT_DECISION",
      "JOB_STARTED",
      "JOB_SUCCEEDED",
      "JOB_FAILED",
      "MODEL_UPDATED",
      "CAMPAIGN_COMPLETED",
      "CAMPAIGN_ERROR",
      "message",
    ];
    types.forEach((t) => source.addEventListener(t, handler));
    return () => source.close();
  }, [campaignId, live]);

  const merged: LiveEvent[] = [...(history.data ?? [])];
  for (const e of liveEvents) {
    if (!e.id || !merged.some((m) => m.id === e.id)) merged.push(e);
  }
  merged.sort((a, b) => (a.created_at < b.created_at ? 1 : -1));

  if (merged.length === 0) {
    return (
      <EmptyState
        title="No agent activity yet"
        description="Start the campaign to begin the autonomous run. Decisions, model updates, and failures stream here as they happen."
      />
    );
  }

  return (
    <ol className="scroll-thin flex max-h-[560px] flex-col overflow-y-auto">
      {merged.map((e, i) => {
        const isDecision = e.event_type === "AGENT_DECISION";
        const prov = isDecision ? provenance(e, strategy) : null;
        const isCoded = prov?.source === "code";
        const tone: Tone = isCoded ? "neutral" : (TYPE_TONE[e.event_type] ?? "neutral");
        const label =
          isCoded && e.event_type === "AGENT_DECISION"
            ? "COMPUTED DECISION"
            : e.event_type.replace(/_/g, " ");
        return (
          <li
            key={e.id ?? i}
            className={cn(
              "relative border-b border-line py-3 pl-5 pr-4 last:border-b-0",
              isDecision && !isCoded && "bg-white/[0.015]",
            )}
          >
            <span className={cn("absolute left-0 top-0 h-full w-[2px]", TONE_RAIL[tone])} />
            <div className="flex items-baseline gap-3">
              <span className="shrink-0 font-mono text-[10px] tabular-nums text-text-muted">
                {new Date(e.created_at).toLocaleTimeString()}
              </span>
              <span
                className={cn(
                  "shrink-0 font-mono text-[10px] uppercase tracking-[0.14em]",
                  TONE_TEXT[tone],
                )}
              >
                {label}
              </span>
              {prov && prov.source !== "unknown" && (
                <span
                  className="shrink-0 rounded-xs border border-line bg-white/[0.02] px-1.5 py-[2px] font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted"
                  title={
                    prov.source === "llm"
                      ? "Written by the LLM scientist."
                      : "Selected by a coded rule, not model inference."
                  }
                >
                  {prov.source === "llm"
                    ? "llm"
                    : prov.decider && prov.decider !== "agent"
                      ? `no inference · ${prov.decider}`
                      : "no inference"}
                </span>
              )}
            </div>
            {e.hypothesis && (
              <p className="mt-1.5 text-[13px] leading-snug text-text">{e.hypothesis}</p>
            )}
            {e.action && (
              <p className="mt-1 text-[13px] leading-snug text-text-secondary">→ {e.action}</p>
            )}
            {e.reasoning_summary && (
              <p className="mt-1 text-[12px] leading-snug text-text-muted">
                <span className="font-mono text-[10px] uppercase tracking-[0.14em]">evidence </span>
                {e.reasoning_summary}
              </p>
            )}
          </li>
        );
      })}
    </ol>
  );
}
