"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { AgentEvent } from "@alloylab/api-client";
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

export function EventFeed({ campaignId, live }: { campaignId: string; live: boolean }) {
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
        const tone = TYPE_TONE[e.event_type] ?? "neutral";
        const isDecision = e.event_type === "AGENT_DECISION";
        return (
          <li
            key={e.id ?? i}
            className={cn(
              "relative border-b border-line py-3 pl-5 pr-4 last:border-b-0",
              isDecision && "bg-white/[0.015]",
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
                {e.event_type.replace(/_/g, " ")}
              </span>
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
