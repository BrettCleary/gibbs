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
import { cn } from "@/lib/cn";
import {
  DataValue,
  EmptyState,
  PanelHeader,
  Surface,
  Table,
  Td,
  Th,
  Tr,
} from "@/components/ui/primitives";
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
  const bs = candidates
    .flatMap((c) => [c.bulk_modulus - c.bulk_modulus_std, c.bulk_modulus + c.bulk_modulus_std])
    .filter(Number.isFinite);
  const yMin = Math.min(...bs, 60) - 5;
  const yMax = Math.max(...bs, 200) + 5;
  const x = (v: number) => M.left + v * (W - M.left - M.right);
  const y = (b: number) => M.top + ((yMax - b) / (yMax - yMin)) * (H - M.top - M.bottom);
  const color = (c: CandidateRead) =>
    !c.stable_0k
      ? "var(--text-muted)"
      : c.stability_at_threshold === "disordered"
        ? "var(--bad)"
        : c.stability_at_threshold === "ordered"
          ? "var(--good)"
          : "var(--accent)";
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {Array.from({ length: 6 }, (_, i) => {
        const v = i / 5;
        return (
          <g key={`x${i}`}>
            <line x1={x(v)} x2={x(v)} y1={M.top} y2={H - M.bottom} stroke="var(--border)" />
            <text
              x={x(v)}
              y={H - M.bottom + 18}
              textAnchor="middle"
              fontSize={11}
              fill="var(--text-dim)"
            >
              {v.toFixed(1)}
            </text>
          </g>
        );
      })}
      {Array.from({ length: 6 }, (_, i) => {
        const b = yMin + ((yMax - yMin) * i) / 5;
        return (
          <g key={`y${i}`}>
            <line x1={M.left} x2={W - M.right} y1={y(b)} y2={y(b)} stroke="var(--border)" />
            <text x={M.left - 8} y={y(b) + 4} textAnchor="end" fontSize={11} fill="var(--text-dim)">
              {b.toFixed(0)}
            </text>
          </g>
        );
      })}
      <text x={(W + M.left) / 2} y={H - 6} textAnchor="middle" fontSize={11} fill="var(--text-dim)">
        composition x (fraction of B)
      </text>
      <text
        x={14}
        y={(H - M.bottom + M.top) / 2}
        textAnchor="middle"
        fontSize={11}
        fill="var(--text-dim)"
        transform={`rotate(-90 14 ${(H - M.bottom + M.top) / 2})`}
      >
        bulk modulus B (GPa)
      </text>
      {candidates.map((c) => {
        if (!Number.isFinite(c.bulk_modulus)) return null;
        const cx = x(c.x),
          cy = y(c.bulk_modulus);
        return (
          <g key={c.label} onClick={() => onSelect(c.label)} style={{ cursor: "pointer" }}>
            {!c.measured && Number.isFinite(c.bulk_modulus_std) && c.bulk_modulus_std > 0 && (
              <line
                x1={cx}
                x2={cx}
                y1={y(c.bulk_modulus - c.bulk_modulus_std)}
                y2={y(c.bulk_modulus + c.bulk_modulus_std)}
                stroke={color(c)}
                strokeWidth={1}
                opacity={0.5}
              />
            )}
            {c.label === selected && (
              <circle cx={cx} cy={cy} r={8} fill="none" stroke="var(--warn)" strokeWidth={1.5} />
            )}
            <circle
              cx={cx}
              cy={cy}
              r={c.stable_0k ? 4.5 : 3}
              fill={c.measured ? color(c) : "var(--panel)"}
              stroke={color(c)}
              strokeWidth={1.5}
            />
          </g>
        );
      })}
      <g fontSize={10} fill="var(--text-dim)">
        <circle cx={M.left + 12} cy={M.top + 8} r={4.5} fill="var(--good)" />
        <text x={M.left + 22} y={M.top + 12}>
          stable · ordered at T
        </text>
        <circle cx={M.left + 162} cy={M.top + 8} r={4.5} fill="var(--accent)" />
        <text x={M.left + 172} y={M.top + 12}>
          stable · unverified
        </text>
        <circle cx={M.left + 302} cy={M.top + 8} r={4.5} fill="var(--bad)" />
        <text x={M.left + 312} y={M.top + 12}>
          disorders at T
        </text>
        <circle cx={M.left + 422} cy={M.top + 8} r={3} fill="var(--text-muted)" />
        <text x={M.left + 432} y={M.top + 12}>
          unstable
        </text>
      </g>
    </svg>
  );
}

export function PropertyDashboard({
  campaignId,
  running,
}: {
  campaignId: string;
  running: boolean;
}) {
  const [selected, setSelected] = useState<string | null>(null);

  const candidates = useQuery({
    queryKey: ["candidates", campaignId],
    queryFn: async () => {
      const { data } = await api.GET("/campaigns/{campaign_id}/candidates", {
        params: { path: { campaign_id: campaignId } },
      });
      return data!;
    },
    refetchInterval: running ? 2500 : false,
  });
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

  const list = useMemo(() => candidates.data?.candidates ?? [], [candidates.data]);
  useEffect(() => {
    if (!selected && candidates.data?.top_candidate_label)
      setSelected(candidates.data.top_candidate_label);
  }, [selected, candidates.data]);
  const byLabel = useMemo(
    () => new Map((structures.data ?? []).map((s) => [s.label, s])),
    [structures.data],
  );
  const selectedStructure = selected ? byLabel.get(selected) : null;
  const selectedPoint = hull.data?.points.find((p) => p.label === selected) ?? null;
  const tThr = candidates.data?.temperature_threshold;
  const top = candidates.data?.top_candidate_label;

  const stabilityTone = (s: string) =>
    s === "ordered" ? "text-verdigris" : s === "disordered" ? "text-oxide" : "text-text-muted";

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Surface className="xl:col-span-3">
          <PanelHeader
            title="Bulk modulus vs composition"
            aside={
              <span className="font-mono">
                stability at {tThr != null ? `${tThr.toFixed(0)} K` : "threshold"}
              </span>
            }
          />
          {list.length > 0 ? (
            <div className="p-4">
              <BulkModulusChart candidates={list} selected={selected} onSelect={setSelected} />
            </div>
          ) : (
            <EmptyState
              title="No candidates yet"
              description="Measurements and surrogate fits populate this chart as the agent scores structures."
            />
          )}
        </Surface>
        <Surface className="xl:col-span-2">
          <PanelHeader title="Structure" />
          {selectedStructure ? (
            <StructureViewer structure={selectedStructure} point={selectedPoint} />
          ) : (
            <EmptyState
              title="Nothing selected"
              description="Select a candidate to view its ordering."
            />
          )}
        </Surface>
      </div>

      <Surface>
        <PanelHeader
          title={`Ranked candidates · ${list.length}`}
          aside={top && <span className="font-mono text-verdigris">recommendation {top}</span>}
        />
        <div className="scroll-thin max-h-80 overflow-y-auto">
          <Table>
            <thead className="sticky top-0 z-10 bg-bg-elevated">
              <tr>
                <Th>#</Th>
                <Th>Label</Th>
                <Th align="right">x_B</Th>
                <Th align="right">ΔE_form (eV)</Th>
                <Th align="right">Above hull</Th>
                <Th align="right">B (GPa)</Th>
                <Th>0 K</Th>
                <Th>At {tThr?.toFixed(0) ?? "T"} K</Th>
                <Th>Source</Th>
              </tr>
            </thead>
            <tbody>
              {list.slice(0, 40).map((c, i) => (
                <Tr
                  key={c.label}
                  clickable
                  selected={selected === c.label}
                  onClick={() => setSelected(c.label)}
                >
                  <Td>
                    <DataValue dim className="text-[11px]">
                      {i + 1}
                    </DataValue>
                  </Td>
                  <Td>
                    <DataValue className={cn("text-[12.5px]", c.label === top && "text-verdigris")}>
                      {c.label}
                    </DataValue>
                  </Td>
                  <Td align="right">
                    <DataValue className="text-[12.5px]">{c.x.toFixed(3)}</DataValue>
                  </Td>
                  <Td align="right">
                    <DataValue className="text-[12.5px]">
                      {c.e_form.toFixed(3)}
                      {!c.measured && c.e_form_std > 0 ? (
                        <span className="text-text-muted"> ±{c.e_form_std.toFixed(3)}</span>
                      ) : null}
                    </DataValue>
                  </Td>
                  <Td align="right">
                    <DataValue className="text-[12.5px]">{c.e_above_hull.toFixed(3)}</DataValue>
                  </Td>
                  <Td align="right">
                    <DataValue className="text-[12.5px]">
                      {Number.isFinite(c.bulk_modulus) ? c.bulk_modulus.toFixed(0) : "—"}
                      {!c.measured && Number.isFinite(c.bulk_modulus_std) ? (
                        <span className="text-text-muted"> ±{c.bulk_modulus_std.toFixed(0)}</span>
                      ) : null}
                    </DataValue>
                  </Td>
                  <Td
                    className={cn(
                      "font-mono text-[11px] uppercase tracking-[0.12em]",
                      c.stable_0k ? "text-verdigris" : "text-text-muted",
                    )}
                  >
                    {c.stable_0k ? "stable" : "—"}
                  </Td>
                  <Td
                    className={cn(
                      "font-mono text-[11px] uppercase tracking-[0.12em]",
                      stabilityTone(c.stability_at_threshold),
                    )}
                  >
                    {c.stability_at_threshold}
                  </Td>
                  <Td
                    className={cn(
                      "font-mono text-[10px] uppercase tracking-[0.14em]",
                      c.measured ? "text-text-muted" : "text-accent",
                    )}
                  >
                    {c.measured ? "measured" : "predicted"}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </div>
      </Surface>

      <Surface>
        <PanelHeader title="Formation-energy hull" />
        {hull.data && hull.data.points.some((p) => p.e_form != null) ? (
          <div className="p-4">
            <HullChart
              points={hull.data.points}
              hullX={hull.data.hull_x}
              hullE={hull.data.hull_e}
              selectedLabel={selected}
              onSelect={(p) => setSelected(p.label)}
            />
          </div>
        ) : (
          <EmptyState title="No formation energies yet" />
        )}
      </Surface>
    </div>
  );
}
