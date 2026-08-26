"use client";

import type { Calculation } from "@alloylab/api-client";
import { API_URL } from "@/lib/api";
import { StatusBadge } from "./StatusBadge";

function target(c: Calculation): string {
  const p = c.input_parameters ?? {};
  if (c.calculation_type === "MONTE_CARLO") {
    if (p.composition != null) {
      return `x=${Number(p.composition).toFixed(2)}, T=${Number(p.temperature ?? 0).toFixed(0)} K`;
    }
    return `T=${Number(p.temperature ?? 0).toFixed(3)}`;
  }
  return `${p.structure_label ?? "?"} (x=${Number(p.composition ?? 0).toFixed(2)})`;
}

function result(c: Calculation): string {
  if (!c.output) return "—";
  if (c.calculation_type === "MONTE_CARLO") {
    if (c.output.heat_capacity != null) {
      return `C = ${Number(c.output.heat_capacity).toFixed(2)} k_B · SRO ${Number(
        c.output.sro,
      ).toFixed(3)}`;
    }
    return `χ = ${Number(c.output.susceptibility).toFixed(2)} ± ${Number(
      c.output.susceptibility_err,
    ).toFixed(2)}`;
  }
  const base = `E/site = ${Number(c.output.energy_per_site).toFixed(4)}`;
  if (c.output.optimal_lattice_constant != null) {
    return `${base} · a₀=${Number(c.output.optimal_lattice_constant).toFixed(3)} Å`;
  }
  return base;
}

export function CalculationsTable({ calculations }: { calculations: Calculation[] }) {
  if (calculations.length === 0) {
    return (
      <p className="p-4 text-sm text-[var(--text-dim)]">No calculations yet.</p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="mono border-b border-[var(--border)] text-left text-[11px] text-[var(--text-dim)]">
            <th className="px-3 py-2">ID</th>
            <th className="px-3 py-2">type</th>
            <th className="px-3 py-2">target</th>
            <th className="px-3 py-2">status</th>
            <th className="px-3 py-2">result</th>
            <th className="px-3 py-2">failure / retry lineage</th>
          </tr>
        </thead>
        <tbody>
          {calculations.map((c) => (
            <tr key={c.id} className="border-b border-[var(--border)] last:border-b-0">
              <td className="mono px-3 py-1.5 text-[var(--text-dim)]">
                {c.stdout_artifact ? (
                  <a
                    href={`${API_URL}/calculations/${c.id}/log`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[var(--accent)] underline decoration-dotted"
                    title="open engine log"
                  >
                    {c.id.slice(0, 8)}
                  </a>
                ) : (
                  c.id.slice(0, 8)
                )}
                {c.retry_of && (
                  <span className="ml-1 text-[var(--warn)]">
                    ↻ retry of {c.retry_of.slice(0, 8)}
                  </span>
                )}
              </td>
              <td className="mono px-3 py-1.5 text-[11px] text-[var(--text-dim)]">
                {c.calculation_type}
              </td>
              <td className="mono px-3 py-1.5">{target(c)}</td>
              <td className="px-3 py-1.5">
                <StatusBadge status={c.status} />
              </td>
              <td className="mono px-3 py-1.5">{result(c)}</td>
              <td className="px-3 py-1.5 text-[12px] text-[var(--text-dim)]">
                {c.failure_category && (
                  <span className="text-[var(--bad)]">{c.failure_category}</span>
                )}
                {c.resolution && <span> → {c.resolution}</span>}
                {c.reason_for_change && <span> ({c.reason_for_change})</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
