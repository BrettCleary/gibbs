"use client";

/**
 * Structure viewer for the 2D lattice problem: renders the periodic tile
 * repeated 3x3 so the ordering pattern is visually obvious (plan section 19's
 * "same composition ≠ same material").
 */

import type { StructureRead, HullPoint } from "@alloylab/api-client";

const REPEAT = 3;
const CELL = 22;

export function StructureViewer({
  structure,
  point,
}: {
  structure: StructureRead;
  point?: HullPoint | null;
}) {
  const occ = structure.occupations;
  const rows = occ.length;
  const cols = occ[0]?.length ?? 0;
  const width = cols * REPEAT * CELL;
  const height = rows * REPEAT * CELL;

  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex items-baseline justify-between">
        <span className="mono text-sm font-bold">{structure.label}</span>
        <span className="mono text-[11px] text-[var(--text-dim)]">
          {structure.chemical_formula} · x={structure.composition.toFixed(3)} ·{" "}
          {structure.shape[0]}×{structure.shape[1]} tile
        </span>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="max-h-64 w-full"
        style={{ maxWidth: width * 1.5 }}
      >
        {Array.from({ length: rows * REPEAT }, (_, i) =>
          Array.from({ length: cols * REPEAT }, (_, j) => {
            const v = occ[i % rows][j % cols];
            return (
              <rect
                key={`${i}-${j}`}
                x={j * CELL}
                y={i * CELL}
                width={CELL - 1}
                height={CELL - 1}
                rx={2}
                fill={v === 1 ? "var(--accent)" : "#2a3644"}
              />
            );
          }),
        )}
        {/* tile boundary of the repeating unit */}
        <rect
          x={cols * CELL}
          y={rows * CELL}
          width={cols * CELL}
          height={rows * CELL}
          fill="none"
          stroke="var(--warn)"
          strokeWidth={1.5}
          strokeDasharray="4 3"
        />
      </svg>
      <div className="mono flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-[var(--text-dim)]">
        <span>
          <span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-[#2a3644] align-middle" /> A
        </span>
        <span>
          <span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-[var(--accent)] align-middle" /> B
        </span>
        {point?.e_form != null && (
          <span>
            ΔE_form = {point.e_form.toFixed(4)}
            {!point.measured && point.e_form_std != null
              ? ` ± ${point.e_form_std.toFixed(4)} (predicted)`
              : " (measured)"}
          </span>
        )}
        {point?.predicted_stable && (
          <span className="text-[var(--good)]">on predicted hull</span>
        )}
      </div>
    </div>
  );
}
