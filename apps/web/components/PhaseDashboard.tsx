"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { PhaseDiagramChart } from "./PhaseDiagramChart";
import { ResponseChart } from "./ResponseChart";

export function PhaseDashboard({
  campaignId,
  running,
}: {
  campaignId: string;
  running: boolean;
}) {
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
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-5">
      <div className="panel xl:col-span-3">
        <div className="border-b border-[var(--border)] px-4 py-2.5">
          <h2 className="mono text-[11px] font-bold tracking-wider text-[var(--text-dim)]">
            COMPOSITION–TEMPERATURE PHASE DIAGRAM — ORDER/DISORDER BOUNDARY
          </h2>
        </div>
        <div className="p-4">
          {d && slices.length > 0 ? (
            <PhaseDiagramChart
              slices={slices}
              tMin={d.temperature_min}
              tMax={d.temperature_max}
              selectedX={selectedX}
              onSelect={setSelectedX}
            />
          ) : (
            <p className="p-6 text-sm text-[var(--text-dim)]">
              No Monte Carlo data yet — start the campaign to map the boundary.
            </p>
          )}
        </div>
      </div>

      <div className="panel xl:col-span-2">
        <div className="border-b border-[var(--border)] px-4 py-2.5">
          <h2 className="mono text-[11px] font-bold tracking-wider text-[var(--text-dim)]">
            SLICE INSPECTOR — HEAT CAPACITY C(T)
            {slice ? ` AT x=${slice.x.toFixed(3)}` : ""}
          </h2>
        </div>
        <div className="p-4">
          {slice && d ? (
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
          ) : (
            <p className="p-6 text-sm text-[var(--text-dim)]">
              Click a boundary point to inspect its heat-capacity curve.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
