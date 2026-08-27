"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { HullPoint } from "@alloylab/api-client";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { DataValue, EmptyState, PanelHeader, Surface } from "@/components/ui/primitives";
import { HullChart } from "./HullChart";
import { StructureViewer } from "./StructureViewer";

export function AlloyDashboard({ campaignId, running }: { campaignId: string; running: boolean }) {
  const [selected, setSelected] = useState<HullPoint | null>(null);

  const hull = useQuery({
    queryKey: ["hull", campaignId],
    queryFn: async () => {
      const { data } = await api.GET("/campaigns/{campaign_id}/hull", {
        params: { path: { campaign_id: campaignId } },
      });
      return data!;
    },
    refetchInterval: running ? 2500 : false,
  });

  const structures = useQuery({
    queryKey: ["structures", campaignId],
    queryFn: async () => {
      const { data } = await api.GET("/campaigns/{campaign_id}/structures", {
        params: { path: { campaign_id: campaignId } },
      });
      return data ?? [];
    },
  });

  const byLabel = useMemo(
    () => new Map((structures.data ?? []).map((s) => [s.label, s])),
    [structures.data],
  );

  const candidates = useMemo(() => {
    const points = hull.data?.points ?? [];
    return points.filter((p) => p.predicted_stable).sort((a, b) => a.x - b.x);
  }, [hull.data]);

  // Default the viewer to the deepest predicted-stable structure.
  useEffect(() => {
    if (!selected && candidates.length > 0) {
      const deepest = [...candidates].sort((a, b) => (a.e_form ?? 0) - (b.e_form ?? 0))[0];
      setSelected(deepest);
    }
  }, [selected, candidates]);

  const selectedStructure = selected ? byLabel.get(selected.label) : null;
  const hasHull = hull.data && hull.data.points.some((p) => p.e_form != null);

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
      <Surface className="xl:col-span-3">
        <PanelHeader
          title="Formation-energy convex hull — measured vs cluster expansion"
          aside={
            hull.data?.loocv_rmse != null && (
              <span className="font-mono">
                CE v{hull.data.model_version} · LOOCV {hull.data.loocv_rmse.toFixed(4)}
              </span>
            )
          }
        />
        {hasHull ? (
          <div className="p-4">
            <HullChart
              points={hull.data!.points}
              hullX={hull.data!.hull_x}
              hullE={hull.data!.hull_e}
              selectedLabel={selected?.label}
              onSelect={setSelected}
            />
          </div>
        ) : (
          <EmptyState
            title="No formation energies yet"
            description="The agent measures the pure-element references first; the hull appears here as soon as the first mixed structure is scored."
          />
        )}
      </Surface>

      <div className="flex flex-col gap-6 xl:col-span-2">
        <Surface>
          <PanelHeader title={`Predicted stable structures · ${candidates.length}`} />
          {candidates.length === 0 ? (
            <EmptyState title="No hull predictions yet" />
          ) : (
            <ul className="scroll-thin max-h-56 overflow-y-auto">
              {candidates.map((p) => {
                const active = selected?.label === p.label;
                return (
                  <li key={p.label}>
                    <button
                      onClick={() => setSelected(p)}
                      aria-pressed={active}
                      className={cn(
                        "flex w-full items-baseline gap-3 border-b border-line px-4 py-2 text-left transition-colors last:border-b-0",
                        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/50",
                        active ? "bg-accent/[0.07]" : "hover:bg-white/[0.03]",
                      )}
                    >
                      <DataValue className="text-[12.5px] text-verdigris">{p.label}</DataValue>
                      <DataValue dim className="text-[12px]">x={p.x.toFixed(3)}</DataValue>
                      <DataValue className="ml-auto text-[12px]">
                        {p.e_form != null ? p.e_form.toFixed(4) : "—"}
                        {!p.measured && p.e_form_std != null && (
                          <span className="text-text-muted"> ±{p.e_form_std.toFixed(4)}</span>
                        )}
                      </DataValue>
                      <span
                        className={cn(
                          "font-mono text-[9px] uppercase tracking-[0.14em]",
                          p.measured ? "text-text-muted" : "text-accent",
                        )}
                      >
                        {p.measured ? "measured" : "predicted"}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Surface>

        <Surface>
          <PanelHeader title="Structure" />
          {selectedStructure ? (
            <StructureViewer structure={selectedStructure} point={selected} />
          ) : (
            <EmptyState
              title="Nothing selected"
              description="Click a point on the hull or a candidate above to view its atomic ordering."
            />
          )}
        </Surface>
      </div>
    </div>
  );
}
