"use client";

import { use, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, FileText, Pause, Play } from "lucide-react";
import { api } from "@/lib/api";
import { engineLabel, isAlloyLike, problemInfo } from "@/lib/problems";
import {
  Button,
  ErrorNote,
  LoadingNote,
  Metric,
  PanelHeader,
  ProgressBar,
  StatusBadge,
  Surface,
  Tag,
  TechnicalLabel,
} from "@/components/ui/primitives";
import { ResponseChart } from "@/components/ResponseChart";
import { EventFeed } from "@/components/EventFeed";
import { CalculationsTable } from "@/components/CalculationsTable";
import { AlloyDashboard } from "@/components/AlloyDashboard";
import { PhaseDashboard } from "@/components/PhaseDashboard";
import { PropertyDashboard } from "@/components/PropertyDashboard";
import { useCopilotPage } from "@/components/copilot/CopilotProvider";

export default function CampaignDashboard({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
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
  const status = campaign.data?.status;
  useCopilotPage(id, campaign.data?.name ?? null);

  // Fast engines (EMT) can finish between two poll ticks; once the campaign
  // leaves RUNNING the interval polls stop, so force one final refresh of
  // every derived view whenever the status changes.
  useEffect(() => {
    if (status == null) return;
    for (const key of [
      "hull",
      "structures",
      "surrogate",
      "phase-diagram",
      "candidates",
      "calculations",
      "agent-events",
    ]) {
      queryClient.invalidateQueries({ queryKey: [key, id] });
    }
  }, [status, id, queryClient]);
  const problemType = campaign.data?.problem_type;
  const isPhase = problemType === "phase_v2";
  const isProperty = problemType === "property_v3";
  const isAlloy = isAlloyLike(problemType) && !isProperty;
  const isIsing = !isPhase && !isProperty && !isAlloy;

  const surrogate = useQuery({
    queryKey: ["surrogate", id],
    queryFn: async () => {
      const { data } = await api.GET("/campaigns/{campaign_id}/surrogate", {
        params: { path: { campaign_id: id } },
      });
      return data!;
    },
    refetchInterval: running ? 2500 : false,
    enabled: campaign.data != null && isIsing,
  });

  const hull = useQuery({
    queryKey: ["hull", id],
    queryFn: async () => {
      const { data } = await api.GET("/campaigns/{campaign_id}/hull", {
        params: { path: { campaign_id: id } },
      });
      return data!;
    },
    refetchInterval: running ? 2500 : false,
    enabled: campaign.data != null && isAlloy,
  });

  const phaseDiagram = useQuery({
    queryKey: ["phase-diagram", id],
    queryFn: async () => {
      const { data } = await api.GET("/campaigns/{campaign_id}/phase-diagram", {
        params: { path: { campaign_id: id } },
      });
      return data!;
    },
    refetchInterval: running ? 2500 : false,
    enabled: campaign.data != null && isPhase,
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
    return campaign.isError ? (
      <ErrorNote>Campaign not found or API unreachable.</ErrorNote>
    ) : (
      <LoadingNote>Loading campaign</LoadingNote>
    );
  }

  const s = surrogate.data;
  const info = problemInfo(problemType);
  const terminal = c.status === "COMPLETED" || c.status === "FAILED";
  const mutationError = start.error ?? pause.error;

  // Problem-specific headline metric.
  let headline: React.ReactNode;
  if (isProperty) {
    headline = (
      <Metric
        label="objective"
        value="max B · stable · ordered"
        tone="good"
        detail={`strategy ${c.strategy}`}
      />
    );
  } else if (isPhase) {
    const slices = phaseDiagram.data?.slices ?? [];
    const fitted = slices.filter((sl) => sl.tc_mean != null);
    const maxStd = fitted.length ? Math.max(...fitted.map((sl) => sl.tc_std ?? 0)) : null;
    headline = (
      <Metric
        label="phase boundary"
        tone="warn"
        value={
          fitted.length === 0
            ? "no boundary yet"
            : `${fitted.length}/${slices.length} slices · max σ ${maxStd?.toFixed(0)} K`
        }
        detail={`boundary v${phaseDiagram.data?.model_version ?? "—"} · strategy ${c.strategy}`}
      />
    );
  } else if (isAlloy) {
    headline = (
      <Metric
        label="predicted stable phases"
        tone="good"
        value={hull.data ? hull.data.stable_labels.length : "—"}
        detail={`CE v${hull.data?.model_version ?? "—"}${hull.data?.loocv_rmse != null ? ` · LOOCV ${hull.data.loocv_rmse.toFixed(4)}` : ""} · strategy ${c.strategy}`}
      />
    );
  } else {
    headline = (
      <Metric
        label="Tc estimate"
        tone="warn"
        value={
          s?.tc_mean != null
            ? `${s.tc_mean.toFixed(3)} ± ${s.tc_std?.toFixed(3) ?? "?"}`
            : "no model yet"
        }
        detail={`surrogate v${s?.model_version ?? "—"} · strategy ${c.strategy}`}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* ------------------------------------------------ mission header */}
      <div className="flex flex-col gap-5">
        <Link
          href="/campaigns"
          className="inline-flex w-fit items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-text-muted transition-colors hover:text-text"
        >
          <ArrowLeft className="h-3 w-3" /> campaigns
        </Link>

        <div className="flex flex-wrap items-start justify-between gap-x-8 gap-y-4">
          <div className="min-w-0 max-w-3xl">
            <div className="flex flex-wrap items-center gap-2.5">
              <Tag>{info.milestone}</Tag>
              {c.synthetic ? (
                <span title="Hidden-model ground truth: a benchmark, not a simulation. Launch these from the Benchmarks page.">
                  <Tag className="border-brass/40 text-brass">synthetic benchmark</Tag>
                </span>
              ) : (
                c.engine && <Tag>{engineLabel(c.engine)}</Tag>
              )}
              <StatusBadge status={c.status} />
              <span className="font-mono text-[10px] text-text-muted">{c.id}</span>
            </div>
            <h1 className="mt-3 text-2xl font-medium tracking-tight text-text md:text-[30px] md:leading-tight">
              {c.name}
            </h1>
            <p className="mt-2 text-[13.5px] leading-relaxed text-text-secondary">{c.objective}</p>
            {c.stopping_rationale && (
              <p className="mt-3 flex items-start gap-2 text-[13px] text-verdigris">
                <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-verdigris" />
                {c.stopping_rationale}
              </p>
            )}
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <Button
              variant="ghost"
              icon={<FileText className="h-3.5 w-3.5" />}
              onClick={() => router.push(`/campaigns/${id}/report`)}
            >
              {c.status === "COMPLETED" ? "Final report" : "Provisional report"}
            </Button>
            {!terminal && !running && (
              <Button
                variant="good"
                icon={<Play className="h-3.5 w-3.5" />}
                loading={start.isPending}
                onClick={() => start.mutate()}
              >
                {c.status === "PAUSED" ? "Resume" : "Start"}
              </Button>
            )}
            {running && (
              <Button
                variant="warn"
                icon={<Pause className="h-3.5 w-3.5" />}
                loading={pause.isPending}
                onClick={() => pause.mutate()}
              >
                Pause
              </Button>
            )}
          </div>
        </div>

        {mutationError != null && (
          <ErrorNote>
            {String((mutationError as { detail?: unknown })?.detail ?? mutationError)}
          </ErrorNote>
        )}

        {/* instrument strip */}
        <Surface className="grid grid-cols-2 divide-y divide-line md:grid-cols-4 md:divide-x md:divide-y-0">
          <div className="flex flex-col gap-2 px-5 py-4">
            <TechnicalLabel>{info.budgetLabel}</TechnicalLabel>
            <div className="font-mono text-[15px] tabular-nums text-text">
              {c.simulations_used}
              <span className="text-text-muted"> / {c.simulation_budget}</span>
            </div>
            <ProgressBar
              value={c.simulations_used}
              max={c.simulation_budget}
              tone={c.status === "COMPLETED" ? "good" : "accent"}
            />
          </div>
          <div className="px-5 py-4 md:col-span-2">{headline}</div>
          <div className="px-5 py-4">
            <Metric
              label="calculations"
              value={calculations.data?.length ?? "—"}
              detail={(() => {
                const list = calculations.data ?? [];
                const failed = list.filter((x) => x.status === "FAILED").length;
                const retried = list.filter((x) => x.retry_of).length;
                return `${failed} failed · ${retried} retried`;
              })()}
            />
          </div>
        </Surface>
      </div>

      {/* ------------------------------------------ problem-specific view */}
      {isProperty ? (
        <PropertyDashboard campaignId={id} running={running} />
      ) : isPhase ? (
        <PhaseDashboard campaignId={id} running={running} />
      ) : isAlloy ? (
        <AlloyDashboard campaignId={id} running={running} />
      ) : (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
          <Surface className="xl:col-span-3">
            <PanelHeader title="Susceptibility χ(T) — measurements vs surrogate" />
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
          </Surface>
          <Surface className="xl:col-span-2">
            <PanelHeader
              title={c.strategy === "agent" ? "Agent activity" : "Campaign activity"}
              aside={running ? "live" : undefined}
            />
            <EventFeed campaignId={id} live={running} strategy={c.strategy} />
          </Surface>
        </div>
      )}

      {!isIsing && (
        <Surface>
          <PanelHeader
            title={c.strategy === "agent" ? "Agent activity" : "Campaign activity"}
            aside={running ? "live" : undefined}
          />
          <EventFeed campaignId={id} live={running} strategy={c.strategy} />
        </Surface>
      )}

      <Surface>
        <PanelHeader title={`Calculations · ${calculations.data?.length ?? 0}`} />
        <CalculationsTable calculations={calculations.data ?? []} />
      </Surface>
    </div>
  );
}
