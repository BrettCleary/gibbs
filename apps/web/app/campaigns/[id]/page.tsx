"use client";

import { use } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { ResponseChart } from "@/components/ResponseChart";
import { EventFeed } from "@/components/EventFeed";
import { CalculationsTable } from "@/components/CalculationsTable";

export default function CampaignDashboard({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  const campaign = useQuery({
    queryKey: ["campaign", id],
    queryFn: async () => {
      const { data, error } = await api.GET("/campaigns/{campaign_id}", {
        params: { path: { campaign_id: id } },
      });
      if (error) throw error;
      return data!;
    },
    refetchInterval: (q) => (q.state.data?.status === "RUNNING" ? 2000 : 8000),
  });

  const running = campaign.data?.status === "RUNNING";

  const surrogate = useQuery({
    queryKey: ["surrogate", id],
    queryFn: async () => {
      const { data } = await api.GET("/campaigns/{campaign_id}/surrogate", {
        params: { path: { campaign_id: id } },
      });
      return data!;
    },
    refetchInterval: running ? 2500 : false,
  });

  const calculations = useQuery({
    queryKey: ["calculations", id],
    queryFn: async () => {
      const { data } = await api.GET("/campaigns/{campaign_id}/calculations", {
        params: { path: { campaign_id: id } },
      });
      return data ?? [];
    },
    refetchInterval: running ? 2500 : false,
  });

  const start = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/campaigns/{campaign_id}/start", {
        params: { path: { campaign_id: id } },
      });
      if (error) throw error;
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["campaign", id] }),
  });

  const pause = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/campaigns/{campaign_id}/pause", {
        params: { path: { campaign_id: id } },
      });
      if (error) throw error;
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["campaign", id] }),
  });

  const c = campaign.data;
  if (!c) {
    return <p className="text-[var(--text-dim)]">Loading campaign…</p>;
  }

  const s = surrogate.data;
  const budgetPct = Math.min((c.simulations_used / c.simulation_budget) * 100, 100);

  return (
    <div className="flex flex-col gap-5">
      {/* Header: objective + status + budget */}
      <div className="panel flex flex-wrap items-center gap-x-8 gap-y-3 px-5 py-4">
        <div className="min-w-64 flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-base font-semibold">{c.name}</h1>
            <StatusBadge status={c.status} />
          </div>
          <p className="mt-1 text-[13px] text-[var(--text-dim)]">{c.objective}</p>
          {c.stopping_rationale && (
            <p className="mt-1 text-[13px] text-[var(--good)]">
              ■ {c.stopping_rationale}
            </p>
          )}
        </div>
        <div className="mono text-[12px]">
          <div className="text-[var(--text-dim)]">MC budget</div>
          <div className="mt-1 text-sm">
            {c.simulations_used} / {c.simulation_budget}
          </div>
          <div className="mt-1 h-1.5 w-40 rounded-full bg-[var(--panel-2)]">
            <div
              className="h-1.5 rounded-full bg-[var(--accent)]"
              style={{ width: `${budgetPct}%` }}
            />
          </div>
        </div>
        <div className="mono text-[12px]">
          <div className="text-[var(--text-dim)]">Tc estimate</div>
          <div className="mt-1 text-sm text-[var(--warn)]">
            {s?.tc_mean != null
              ? `${s.tc_mean.toFixed(3)} ± ${s.tc_std?.toFixed(3) ?? "?"}`
              : "no model yet"}
          </div>
          <div className="mt-0.5 text-[11px] text-[var(--text-dim)]">
            surrogate v{s?.model_version ?? "—"} · strategy: {c.strategy}
          </div>
        </div>
        <div className="flex gap-2">
          {c.status !== "COMPLETED" && c.status !== "FAILED" && !running && (
            <button
              onClick={() => start.mutate()}
              disabled={start.isPending}
              className="rounded-sm bg-[var(--good)] px-4 py-1.5 text-sm font-semibold text-black disabled:opacity-50"
            >
              {c.status === "PAUSED" ? "Resume" : "Start"}
            </button>
          )}
          {running && (
            <button
              onClick={() => pause.mutate()}
              disabled={pause.isPending}
              className="rounded-sm bg-[var(--warn)] px-4 py-1.5 text-sm font-semibold text-black disabled:opacity-50"
            >
              Pause
            </button>
          )}
        </div>
        {(start.error || pause.error) && (
          <p className="w-full text-sm text-[var(--bad)]">
            {String(
              ((start.error ?? pause.error) as any)?.detail ??
                (start.error ?? pause.error),
            )}
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-5">
        {/* Main visualization */}
        <div className="panel xl:col-span-3">
          <div className="border-b border-[var(--border)] px-4 py-2.5">
            <h2 className="mono text-[11px] font-bold tracking-wider text-[var(--text-dim)]">
              SUSCEPTIBILITY χ(T) — MEASUREMENTS vs SURROGATE PREDICTION
            </h2>
          </div>
          <div className="p-4">
            <ResponseChart
              curveT={s?.temperatures ?? []}
              curveMean={s?.mean ?? []}
              curveStd={s?.std ?? []}
              pointsT={s?.measured_temperatures ?? []}
              pointsY={s?.measured_values ?? []}
              pointsErr={s?.measured_errors ?? []}
              tcMean={s?.tc_mean}
              tcStd={s?.tc_std}
              tMin={c.temperature_min}
              tMax={c.temperature_max}
            />
          </div>
        </div>

        {/* Agent activity */}
        <div className="panel xl:col-span-2">
          <div className="border-b border-[var(--border)] px-4 py-2.5">
            <h2 className="mono text-[11px] font-bold tracking-wider text-[var(--text-dim)]">
              AGENT ACTIVITY
            </h2>
          </div>
          <EventFeed campaignId={id} live={running} />
        </div>
      </div>

      {/* Run inspector table */}
      <div className="panel">
        <div className="border-b border-[var(--border)] px-4 py-2.5">
          <h2 className="mono text-[11px] font-bold tracking-wider text-[var(--text-dim)]">
            CALCULATIONS ({calculations.data?.length ?? 0})
          </h2>
        </div>
        <CalculationsTable calculations={calculations.data ?? []} />
      </div>
    </div>
  );
}
