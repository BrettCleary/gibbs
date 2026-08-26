"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { AgentEvent } from "@alloylab/api-client";
import { api, API_URL } from "@/lib/api";

const TYPE_COLOR: Record<string, string> = {
  AGENT_DECISION: "var(--accent)",
  MODEL_UPDATED: "var(--good)",
  JOB_FAILED: "var(--bad)",
  CAMPAIGN_ERROR: "var(--bad)",
  CAMPAIGN_COMPLETED: "var(--good)",
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
    const source = new EventSource(`${API_URL}/campaigns/${campaignId}/events`);
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

  return (
    <div className="flex max-h-[560px] flex-col gap-0 overflow-y-auto">
      {merged.length === 0 && (
        <p className="p-4 text-sm text-[var(--text-dim)]">
          No agent activity yet. Start the campaign to begin the autonomous run.
        </p>
      )}
      {merged.map((e, i) => (
        <div
          key={e.id ?? i}
          className="border-b border-[var(--border)] px-4 py-2.5 last:border-b-0"
        >
          <div className="flex items-baseline gap-3">
            <span className="mono shrink-0 text-[11px] text-[var(--text-dim)]">
              {new Date(e.created_at).toLocaleTimeString()}
            </span>
            <span
              className="mono shrink-0 text-[11px] font-bold"
              style={{ color: TYPE_COLOR[e.event_type] ?? "var(--text-dim)" }}
            >
              {e.event_type}
            </span>
          </div>
          {e.hypothesis && (
            <p className="mt-1 text-[13px] leading-snug">{e.hypothesis}</p>
          )}
          {e.action && (
            <p className="mt-0.5 text-[13px] leading-snug text-[var(--text-dim)]">
              → {e.action}
            </p>
          )}
          {e.reasoning_summary && (
            <p className="mt-0.5 text-[12px] italic leading-snug text-[var(--text-dim)]">
              evidence: {e.reasoning_summary}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
