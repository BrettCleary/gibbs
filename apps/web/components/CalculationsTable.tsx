"use client";

import { ExternalLink } from "lucide-react";
import type { Calculation } from "@alloylab/api-client";
import { apiFetch } from "@/lib/api";
import { DataValue, EmptyState, StatusBadge, Table, Td, Th, Tr } from "@/components/ui/primitives";

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
      return `C = ${Number(c.output.heat_capacity).toFixed(2)} k_B · SRO ${Number(c.output.sro).toFixed(3)}`;
    }
    return `χ = ${Number(c.output.susceptibility).toFixed(2)} ± ${Number(c.output.susceptibility_err).toFixed(2)}`;
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
      <EmptyState
        title="No calculations yet"
        description="Every simulation the agent launches appears here with its target, result, and failure lineage."
      />
    );
  }
  return (
    <div className="scroll-thin max-h-[520px] overflow-y-auto">
      <Table>
        <thead className="sticky top-0 z-10 bg-bg-elevated">
          <tr>
            <Th>ID</Th>
            <Th>Type</Th>
            <Th>Target</Th>
            <Th>Status</Th>
            <Th>Result</Th>
            <Th>Failure / retry lineage</Th>
          </tr>
        </thead>
        <tbody>
          {calculations.map((c) => (
            <Tr key={c.id}>
              <Td className="whitespace-nowrap">
                {c.stdout_artifact ? (
                  <a
                    href={`/calculations/${c.id}/log`}
                    onClick={(e) => {
                      e.preventDefault();
                      void openLog(c.id);
                    }}
                    title="open engine log"
                    className="inline-flex items-center gap-1 font-mono text-[12px] text-accent-bright underline decoration-accent/40 decoration-dotted underline-offset-4 hover:decoration-accent"
                  >
                    {c.id.slice(0, 8)}
                    <ExternalLink className="h-3 w-3 opacity-60" />
                  </a>
                ) : (
                  <DataValue dim className="text-[12px]">
                    {c.id.slice(0, 8)}
                  </DataValue>
                )}
                {c.retry_of && (
                  <span className="ml-2 font-mono text-[10px] text-brass">
                    ↻ retry of {c.retry_of.slice(0, 8)}
                  </span>
                )}
              </Td>
              <Td>
                <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
                  {c.calculation_type.replace(/_/g, " ")}
                </span>
              </Td>
              <Td>
                <DataValue className="text-[12.5px]">{target(c)}</DataValue>
              </Td>
              <Td>
                <StatusBadge status={c.status} />
              </Td>
              <Td>
                <DataValue className="text-[12.5px]">{result(c)}</DataValue>
              </Td>
              <Td className="text-[12px] text-text-secondary">
                {c.failure_category && (
                  <span className="font-mono text-oxide">{c.failure_category}</span>
                )}
                {c.resolution && <span> → {c.resolution}</span>}
                {c.reason_for_change && (
                  <span className="text-text-muted"> ({c.reason_for_change})</span>
                )}
              </Td>
            </Tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}

/** The log endpoint needs the bearer token, so fetch it and open the result in a new tab. */
async function openLog(id: string) {
  const res = await apiFetch(`/calculations/${id}/log`);
  const blob = await res.blob();
  const url = URL.createObjectURL(new Blob([blob], { type: "text/plain" }));
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
