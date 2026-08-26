"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { HullPoint } from "@alloylab/api-client";
import { api } from "@/lib/api";
import { HullChart } from "./HullChart";
import { StructureViewer } from "./StructureViewer";

export function AlloyDashboard({
  campaignId,
  running,
}: {
  campaignId: string;
  running: boolean;
}) {
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
    return points
      .filter((p) => p.predicted_stable)
      .sort((a, b) => a.x - b.x);
  }, [hull.data]);

  // Default the viewer to the deepest predicted-stable structure.
  useEffect(() => {
    if (!selected && candidates.length > 0) {
      const deepest = [...candidates].sort(
        (a, b) => (a.e_form ?? 0) - (b.e_form ?? 0),
      )[0];
      setSelected(deepest);
    }
  }, [selected, candidates]);

  const selectedStructure = selected ? byLabel.get(selected.label) : null;

  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-5">
      <div className="panel xl:col-span-3">
        <div className="flex items-baseline justify-between border-b border-[var(--border)] px-4 py-2.5">
          <h2 className="mono text-[11px] font-bold tracking-wider text-[var(--text-dim)]">
            FORMATION-ENERGY CONVEX HULL — MEASURED vs CLUSTER-EXPANSION PREDICTION
          </h2>
          {hull.data?.loocv_rmse != null && (
            <span className="mono text-[11px] text-[var(--text-dim)]">
              CE v{hull.data.model_version} · LOOCV RMSE {hull.data.loocv_rmse.toFixed(4)}
            </span>
          )}
        </div>
        <div className="p-4">
          {hull.data && hull.data.points.some((p) => p.e_form != null) ? (
            <HullChart
              points={hull.data.points}
              hullX={hull.data.hull_x}
              hullE={hull.data.hull_e}
              selectedLabel={selected?.label}
              onSelect={setSelected}
            />
          ) : (
            <p className="p-6 text-sm text-[var(--text-dim)]">
              No formation energies yet — the agent measures the pure-element
              references first, then the hull appears here.
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-5 xl:col-span-2">
        <div className="panel">
          <div className="border-b border-[var(--border)] px-4 py-2.5">
            <h2 className="mono text-[11px] font-bold tracking-wider text-[var(--text-dim)]">
              PREDICTED STABLE STRUCTURES ({candidates.length})
            </h2>
          </div>
          <div className="max-h-56 overflow-y-auto">
            {candidates.length === 0 && (
              <p className="p-4 text-sm text-[var(--text-dim)]">
                No hull predictions yet.
              </p>
            )}
            {candidates.map((p) => (
              <button
                key={p.label}
                onClick={() => setSelected(p)}
                className={`flex w-full items-baseline gap-3 border-b border-[var(--border)] px-4 py-2 text-left last:border-b-0 hover:bg-[var(--panel-2)] ${
                  selected?.label === p.label ? "bg-[var(--panel-2)]" : ""
                }`}
              >
                <span className="mono text-[12px] text-[var(--good)]">{p.label}</span>
                <span className="mono text-[12px] text-[var(--text-dim)]">
                  x={p.x.toFixed(3)}
                </span>
                <span className="mono ml-auto text-[12px]">
                  {p.e_form != null ? p.e_form.toFixed(4) : "—"}
                  {!p.measured && p.e_form_std != null && (
                    <span className="text-[var(--text-dim)]"> ±{p.e_form_std.toFixed(4)}</span>
                  )}
                </span>
                <span
                  className="mono text-[10px]"
                  style={{ color: p.measured ? "var(--text)" : "var(--accent)" }}
                >
                  {p.measured ? "measured" : "predicted"}
                </span>
              </button>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="border-b border-[var(--border)] px-4 py-2.5">
            <h2 className="mono text-[11px] font-bold tracking-wider text-[var(--text-dim)]">
              STRUCTURE VIEWER
            </h2>
          </div>
          {selectedStructure ? (
            <StructureViewer structure={selectedStructure} point={selected} />
          ) : (
            <p className="p-4 text-sm text-[var(--text-dim)]">
              Click a point on the hull or a candidate to view its atomic ordering.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
