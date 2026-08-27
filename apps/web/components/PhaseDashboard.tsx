"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { EmptyState, PanelHeader, Surface } from "@/components/ui/primitives";
import { PhaseDiagramChart } from "./PhaseDiagramChart";
import { ResponseChart } from "./ResponseChart";

export function PhaseDashboard({ campaignId, running }: { campaignId: string; running: boolean }) {
  const [selectedX, setSelectedX] = useState<number | null>(null);

  const diagram = useQuery({
    queryKey: ["phase-diagram", campaignId],
    queryFn: async () => {
      const { data } = await api.GET("/campaigns/{campaign_id}/phase-diagram", {
        params: { path: { campaign_id: campaignId } },
      });
      return data!;
    },
    refetchInterval: running ? 2500 : false,
  });

  const slices = useMemo(() => diagram.data?.slices ?? [], [diagram.data]);

  // Default the slice inspector to the most uncertain boundary.
  useEffect(() => {
    if (selectedX == null && slices.some((s) => s.tc_mean != null)) {
      const most = [...slices]
        .filter((s) => s.tc_std != null)
        .sort((a, b) => (b.tc_std ?? 0) - (a.tc_std ?? 0))[0];
      if (most) setSelectedX(most.x);
    }
  }, [selectedX, slices]);

  const slice = slices.find((s) => s.x === selectedX) ?? null;
  const d = diagram.data;

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
      <Surface className="xl:col-span-3">
        <PanelHeader
          title="Composition–temperature phase diagram — order/disorder boundary"
          aside={d && <span className="font-mono">boundary v{d.model_version}</span>}
        />
        {d && slices.length > 0 ? (
          <div className="p-4">
            <PhaseDiagramChart
              slices={slices}
              tMin={d.temperature_min}
              tMax={d.temperature_max}
              selectedX={selectedX}
              onSelect={setSelectedX}
            />
          </div>
        ) : (
          <EmptyState
            title="No Monte Carlo data yet"
            description="Start the campaign to map the boundary. Each composition slice gets a heat-capacity scan; peaks locate the transition."
          />
        )}
      </Surface>

      <Surface className="xl:col-span-2">
        <PanelHeader
          title="Slice inspector — heat capacity C(T)"
          aside={slice && <span className="font-mono">x = {slice.x.toFixed(3)}</span>}
        />
        {slice && d ? (
          <div className="p-4">
            <ResponseChart
              curveT={slice.curve_t}
              curveMean={slice.curve_mean}
              curveStd={slice.curve_std}
              pointsT={slice.measured.map((m) => m.temperature)}
              pointsY={slice.measured.map((m) => m.heat_capacity)}
              pointsErr={slice.measured.map((m) => m.heat_capacity_err)}
              tcMean={slice.tc_mean}
              tcStd={slice.tc_std}
              tMin={d.temperature_min}
              tMax={d.temperature_max}
              xLabel="temperature (K)"
              yLabel="heat capacity C (k_B / atom)"
              legendCurve="boundary fit ±2σ"
            />
          </div>
        ) : (
          <EmptyState
            title="No slice selected"
            description="Click a boundary point on the diagram to inspect its heat-capacity curve."
          />
        )}
      </Surface>
    </div>
  );
}
