"use client";

/**
 * Structure viewer for the 2D lattice problem: renders the periodic tile
 * repeated 3x3 so the ordering pattern is visually obvious (plan section 19's
 * "same composition ≠ same material"). 3D cells defer to Structure3DViewer.
 */

import type { StructureRead, HullPoint } from "@alloylab/api-client";
import { DataValue, TechnicalLabel } from "@/components/ui/primitives";
import { ELEMENT_NAMES, Structure3DViewer } from "./Structure3DViewer";

const REPEAT = 3;
const CELL = 22;

function Legend({
  swatches,
  point,
}: {
  swatches: Array<{ color: string; label: string; square?: boolean }>;
  point?: HullPoint | null;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 font-mono text-[11px] text-text-secondary">
      {swatches.map((s) => (
        <span key={s.label} className="flex items-center gap-1.5">
          <span
            className={
              s.square
                ? "inline-block h-2.5 w-2.5 rounded-xs"
                : "inline-block h-2.5 w-2.5 rounded-full"
            }
            style={{ background: s.color }}
          />
          {s.label}
        </span>
      ))}
      {point?.e_form != null && (
        <span>
          ΔE_form = {point.e_form.toFixed(4)}
          {!point.measured && point.e_form_std != null ? ` ± ${point.e_form_std.toFixed(4)}` : ""}
          <span className="text-text-muted"> {point.measured ? "measured" : "predicted"}</span>
        </span>
      )}
      {point?.predicted_stable && <span className="text-verdigris">on predicted hull</span>}
    </div>
  );
}

export function StructureViewer({
  structure,
  point,
}: {
  structure: StructureRead;
  point?: HullPoint | null;
}) {
  const is3d = (structure.atomic_numbers?.length ?? 0) > 0;
  const zs = [...new Set(structure.atomic_numbers ?? [])].sort((a, b) => a - b);
  const name = (z: number | undefined) => (z == null ? "?" : (ELEMENT_NAMES[z] ?? `Z${z}`));
  // Element A is the parent (x = 0); with one species present, use composition to tell A from B.
  const [elA, elB] =
    zs.length === 2
      ? [name(zs[0]), name(zs[1])]
      : structure.composition >= 1
        ? ["A", name(zs[0])]
        : [name(zs[0]), "B"];

  const header = (meta: string) => (
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <DataValue className="text-[14px] font-medium">{structure.label}</DataValue>
      <TechnicalLabel className="normal-case tracking-[0.06em]">{meta}</TechnicalLabel>
    </div>
  );

  if (is3d) {
    return (
      <div className="flex flex-col gap-3 p-4">
        {header(
          `${structure.chemical_formula} · x_${elB}=${structure.composition.toFixed(3)} · ${structure.n_sites}-atom cell, shown 2×2×2`,
        )}
        <Structure3DViewer structure={structure} />
        <Legend
          swatches={[
            { color: "#c9cdd3", label: elA },
            { color: "var(--accent)", label: elB },
          ]}
          point={point}
        />
      </div>
    );
  }

  const occ = structure.occupations;
  const rows = occ.length;
  const cols = occ[0]?.length ?? 0;
  const width = cols * REPEAT * CELL;
  const height = rows * REPEAT * CELL;

  return (
    <div className="flex flex-col gap-3 p-4">
      {header(
        `${structure.chemical_formula} · x=${structure.composition.toFixed(3)} · ${structure.shape[0]}×${structure.shape[1]} tile`,
      )}
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
                fill={v === 1 ? "var(--accent)" : "var(--panel-2)"}
              />
            );
          }),
        )}
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
      <Legend
        swatches={[
          { color: "var(--panel-2)", label: "A", square: true },
          { color: "var(--accent)", label: "B", square: true },
        ]}
        point={point}
      />
    </div>
  );
}
