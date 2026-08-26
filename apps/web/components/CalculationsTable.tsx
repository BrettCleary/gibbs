"use client";

import type { Calculation } from "@alloylab/api-client";
import { StatusBadge } from "./StatusBadge";

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
            <th className="px-3 py-2">T</th>
            <th className="px-3 py-2">status</th>
            <th className="px-3 py-2">χ</th>
            <th className="px-3 py-2">E/site</th>
            <th className="px-3 py-2">failure / retry lineage</th>
          </tr>
        </thead>
        <tbody>
          {calculations.map((c) => (
            <tr key={c.id} className="border-b border-[var(--border)] last:border-b-0">
              <td className="mono px-3 py-1.5 text-[var(--text-dim)]">
                {c.id.slice(0, 8)}
                {c.retry_of && (
                  <span className="ml-1 text-[var(--warn)]">
                    ↻ retry of {c.retry_of.slice(0, 8)}
                  </span>
                )}
              </td>
              <td className="mono px-3 py-1.5">
                {Number(c.input_parameters?.temperature ?? 0).toFixed(3)}
              </td>
              <td className="px-3 py-1.5">
                <StatusBadge status={c.status} />
              </td>
              <td className="mono px-3 py-1.5">
                {c.output
                  ? `${Number(c.output.susceptibility).toFixed(2)} ± ${Number(
                      c.output.susceptibility_err,
                    ).toFixed(2)}`
                  : "—"}
              </td>
              <td className="mono px-3 py-1.5">
                {c.output ? Number(c.output.energy_per_site).toFixed(4) : "—"}
              </td>
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
