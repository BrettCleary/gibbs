"use client";

/**
 * Property-search dashboard (Milestone 8): the ranked candidate table (plan
 * section 14), a bulk-modulus-vs-composition chart colored by stability, the
 * hull, and the structure viewer for the selected candidate.
 */

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { CandidateRead } from "@alloylab/api-client";
import { api } from "@/lib/api";
import { HullChart } from "./HullChart";
import { StructureViewer } from "./StructureViewer";

const W = 760;
const H = 360;
const M = { top: 18, right: 16, bottom: 42, left: 60 };

function BulkModulusChart({
  candidates,
  selected,
  onSelect,
}: {
  candidates: CandidateRead[];
  selected: string | null;
  onSelect: (label: string) => void;
}) {
  const bs = candidates.flatMap((c) => [c.bulk_modulus - c.bulk_modulus_std, c.bulk_modulus + c.bulk_modulus_std]).filter(Number.isFinite);
  const yMin = Math.min(...bs, 60) - 5;
  const yMax = Math.max(...bs, 200) + 5;
  const x = (v: number) => M.left + v * (W - M.left - M.right);
  const y = (b: number) => M.top + ((yMax - b) / (yMax - yMin)) * (H - M.top - M.bottom);
  const color = (c: CandidateRead) =>
    !c.stable_0k ? "var(--text-dim)" : c.stability_at_threshold === "disordered" ? "var(--bad)" : c.stability_at_threshold === "ordered" ? "var(--good)" : "var(--accent)";
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {Array.from({ length: 6 }, (_, i) => {
        const v = i / 5;
        return (
          <g key={`x${i}`}>
            <line x1={x(v)} x2={x(v)} y1={M.top} y2={H - M.bottom} stroke="var(--border)" />
            <text x={x(v)} y={H - M.bottom + 18} textAnchor="middle" fontSize={11} fill="var(--text-dim)">{v.toFixed(1)}</text>
          </g>
        );
      })}
      {Array.from({ length: 6 }, (_, i) => {
        const b = yMin + ((yMax - yMin) * i) / 5;
        return (
          <g key={`y${i}`}>
            <line x1={M.left} x2={W - M.right} y1={y(b)} y2={y(b)} stroke="var(--border)" />
            <text x={M.left - 8} y={y(b) + 4} textAnchor="end" fontSize={11} fill="var(--text-dim)">{b.toFixed(0)}</text>
          </g>
        );
      })}
      <text x={(W + M.left) / 2} y={H - 6} textAnchor="middle" fontSize={12} fill="var(--text-dim)">composition x_Al</text>
      <text x={14} y={(H - M.bottom + M.top) / 2} textAnchor="middle" fontSize={12} fill="var(--text-dim)" transform={`rotate(-90 14 ${(H - M.bottom + M.top) / 2})`}>bulk modulus B (GPa)</text>
      {candidates.map((c) => {
        if (!Number.isFinite(c.bulk_modulus)) return null;
        const cx = x(c.x), cy = y(c.bulk_modulus);
        return (
          <g key={c.label} onClick={() => onSelect(c.label)} style={{ cursor: "pointer" }}>
            {!c.measured && Number.isFinite(c.bulk_modulus_std) && c.bulk_modulus_std > 0 && (
              <line x1={cx} x2={cx} y1={y(c.bulk_modulus - c.bulk_modulus_std)} y2={y(c.bulk_modulus + c.bulk_modulus_std)} stroke={color(c)} strokeWidth={1} opacity={0.5} />
            )}
            {c.label === selected && <circle cx={cx} cy={cy} r={8} fill="none" stroke="var(--warn)" strokeWidth={1.5} />}
            <circle cx={cx} cy={cy} r={c.stable_0k ? 4.5 : 3} fill={c.measured ? color(c) : "var(--bg)"} stroke={color(c)} strokeWidth={1.5} />
          </g>
        );
      })}
      <g fontSize={11} fill="var(--text-dim)">
        <circle cx={M.left + 12} cy={M.top + 8} r={4.5} fill="var(--good)" /><text x={M.left + 22} y={M.top + 12}>stable · ordered at T</text>
        <circle cx={M.left + 162} cy={M.top + 8} r={4.5} fill="var(--accent)" /><text x={M.left + 172} y={M.top + 12}>stable · unverified</text>
        <circle cx={M.left + 302} cy={M.top + 8} r={4.5} fill="var(--bad)" /><text x={M.left + 312} y={M.top + 12}>disorders at T</text>
        <circle cx={M.left + 422} cy={M.top + 8} r={3} fill="var(--text-dim)" /><text x={M.left + 432} y={M.top + 12}>unstable</text>
      </g>
    </svg>
  );
}

export function PropertyDashboard({ campaignId, running }: { campaignId: string; running: boolean }) {
  const [selected, setSelected] = useState<string | null>(null);

  const candidates = useQuery({
    queryKey: ["candidates", campaignId],
    queryFn: async () => {
      const { data } = await api.GET("/campaigns/{campaign_id}/candidates", { params: { path: { campaign_id: campaignId } } });
      return data!;
    },
    refetchInterval: running ? 2500 : false,
  });
  const hull = useQuery({
    queryKey: ["hull", campaignId],
    queryFn: async () => {
      const { data } = await api.GET("/campaigns/{campaign_id}/hull", { params: { path: { campaign_id: campaignId } } });
      return data!;
    },
    refetchInterval: running ? 2500 : false,
  });
  const structures = useQuery({
    queryKey: ["structures", campaignId],
    queryFn: async () => {
      const { data } = await api.GET("/campaigns/{campaign_id}/structures", { params: { path: { campaign_id: campaignId } } });
      return data ?? [];
    },
  });

  const list = useMemo(() => candidates.data?.candidates ?? [], [candidates.data]);
  useEffect(() => {
    if (!selected && candidates.data?.top_candidate_label) setSelected(candidates.data.top_candidate_label);
  }, [selected, candidates.data]);
  const byLabel = useMemo(() => new Map((structures.data ?? []).map((s) => [s.label, s])), [structures.data]);
  const selectedStructure = selected ? byLabel.get(selected) : null;
  const selectedPoint = hull.data?.points.find((p) => p.label === selected) ?? null;
  const tThr = candidates.data?.temperature_threshold;

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-5">
        <div className="panel xl:col-span-3">
          <div className="border-b border-[var(--border)] px-4 py-2.5">
            <h2 className="mono text-[11px] font-bold tracking-wider text-[var(--text-dim)]">
              BULK MODULUS vs COMPOSITION — STABILITY AT {tThr != null ? `${tThr.toFixed(0)} K` : "THRESHOLD"}
            </h2>
          </div>
          <div className="p-4">
            {list.length > 0 ? (
              <BulkModulusChart candidates={list} selected={selected} onSelect={setSelected} />
            ) : (
              <p className="p-6 text-sm text-[var(--text-dim)]">No candidates yet — measurements and surrogate fits will populate this.</p>
            )}
          </div>
        </div>
        <div className="panel xl:col-span-2">
          <div className="border-b border-[var(--border)] px-4 py-2.5">
            <h2 className="mono text-[11px] font-bold tracking-wider text-[var(--text-dim)]">STRUCTURE VIEWER</h2>
          </div>
          {selectedStructure ? (
            <StructureViewer structure={selectedStructure} point={selectedPoint} />
          ) : (
            <p className="p-4 text-sm text-[var(--text-dim)]">Select a candidate to view its ordering.</p>
          )}
        </div>
      </div>

      <div className="panel">
        <div className="flex items-baseline justify-between border-b border-[var(--border)] px-4 py-2.5">
          <h2 className="mono text-[11px] font-bold tracking-wider text-[var(--text-dim)]">RANKED CANDIDATES ({list.length})</h2>
          {candidates.data?.top_candidate_label && (
            <span className="mono text-[11px] text-[var(--good)]">recommendation: {candidates.data.top_candidate_label}</span>
          )}
        </div>
        <div className="max-h-80 overflow-y-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="mono border-b border-[var(--border)] text-left text-[11px] text-[var(--text-dim)]">
                <th className="px-3 py-2">#</th><th className="px-3 py-2">label</th><th className="px-3 py-2">x_Al</th>
                <th className="px-3 py-2">ΔE_form (eV)</th><th className="px-3 py-2">above hull</th><th className="px-3 py-2">B (GPa)</th>
                <th className="px-3 py-2">0 K</th><th className="px-3 py-2">at {tThr?.toFixed(0) ?? "T"} K</th><th className="px-3 py-2">source</th>
              </tr>
            </thead>
            <tbody>
              {list.slice(0, 40).map((c, i) => (
                <tr key={c.label} onClick={() => setSelected(c.label)}
                    className={`cursor-pointer border-b border-[var(--border)] last:border-b-0 hover:bg-[var(--panel-2)] ${selected === c.label ? "bg-[var(--panel-2)]" : ""}`}>
                  <td className="mono px-3 py-1.5 text-[var(--text-dim)]">{i + 1}</td>
                  <td className="mono px-3 py-1.5" style={{ color: c.label === candidates.data?.top_candidate_label ? "var(--good)" : "inherit" }}>{c.label}</td>
                  <td className="mono px-3 py-1.5">{c.x.toFixed(3)}</td>
                  <td className="mono px-3 py-1.5">{c.e_form.toFixed(3)}{!c.measured && c.e_form_std > 0 ? <span className="text-[var(--text-dim)]"> ±{c.e_form_std.toFixed(3)}</span> : null}</td>
                  <td className="mono px-3 py-1.5">{c.e_above_hull.toFixed(3)}</td>
                  <td className="mono px-3 py-1.5">{Number.isFinite(c.bulk_modulus) ? c.bulk_modulus.toFixed(0) : "—"}{!c.measured && Number.isFinite(c.bulk_modulus_std) ? <span className="text-[var(--text-dim)]"> ±{c.bulk_modulus_std.toFixed(0)}</span> : null}</td>
                  <td className="px-3 py-1.5" style={{ color: c.stable_0k ? "var(--good)" : "var(--text-dim)" }}>{c.stable_0k ? "stable" : "—"}</td>
                  <td className="px-3 py-1.5" style={{ color: c.stability_at_threshold === "ordered" ? "var(--good)" : c.stability_at_threshold === "disordered" ? "var(--bad)" : "var(--text-dim)" }}>{c.stability_at_threshold}</td>
                  <td className="mono px-3 py-1.5 text-[11px]" style={{ color: c.measured ? "var(--text)" : "var(--accent)" }}>{c.measured ? "measured" : "predicted"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <div className="border-b border-[var(--border)] px-4 py-2.5">
          <h2 className="mono text-[11px] font-bold tracking-wider text-[var(--text-dim)]">FORMATION-ENERGY HULL</h2>
        </div>
        <div className="p-4">
          {hull.data && hull.data.points.some((p) => p.e_form != null) ? (
            <HullChart points={hull.data.points} hullX={hull.data.hull_x} hullE={hull.data.hull_e} selectedLabel={selected} onSelect={(p) => setSelected(p.label)} />
          ) : (
            <p className="p-4 text-sm text-[var(--text-dim)]">No formation energies yet.</p>
          )}
        </div>
      </div>
    </div>
  );
}
