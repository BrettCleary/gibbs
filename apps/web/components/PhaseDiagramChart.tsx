"use client";

/**
 * T-x phase diagram: per-slice boundary estimates Tc(x) with uncertainty
 * bars, the inferred boundary line, the ordered region shaded below it, and
 * measured MC points colored by short-range order. Click a slice to inspect
 * its C(T) curve.
 */

import type { PhaseSliceView } from "@alloylab/api-client";

type Props = {
  slices: PhaseSliceView[];
  tMin: number;
  tMax: number;
  selectedX?: number | null;
  onSelect?: (x: number) => void;
};

const W = 760;
const H = 420;
const M = { top: 18, right: 20, bottom: 44, left: 64 };

export function PhaseDiagramChart({ slices, tMin, tMax, selectedX, onSelect }: Props) {
  const x = (v: number) => M.left + v * (W - M.left - M.right);
  const y = (t: number) =>
    M.top + ((tMax - t) / (tMax - tMin)) * (H - M.top - M.bottom);

  const boundary = slices
    .filter((s) => s.tc_mean != null)
    .sort((a, b) => a.x - b.x);

  const boundaryPath =
    boundary.length > 1
      ? boundary.map((s, i) => `${i === 0 ? "M" : "L"}${x(s.x)},${y(s.tc_mean!)}`).join(" ")
      : "";

  // Ordered region: below the boundary line (down to tMin).
  const orderedPath =
    boundary.length > 1
      ? boundaryPath +
        ` L${x(boundary[boundary.length - 1].x)},${y(tMin)}` +
        ` L${x(boundary[0].x)},${y(tMin)} Z`
      : "";

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {Array.from({ length: 6 }, (_, i) => {
        const v = i / 5;
        return (
          <g key={`x${i}`}>
            <line x1={x(v)} x2={x(v)} y1={M.top} y2={H - M.bottom} stroke="var(--border)" />
            <text x={x(v)} y={H - M.bottom + 18} textAnchor="middle" fontSize={11} fill="var(--text-dim)">
              {v.toFixed(1)}
            </text>
          </g>
        );
      })}
      {Array.from({ length: 6 }, (_, i) => {
        const t = tMin + ((tMax - tMin) * i) / 5;
        return (
          <g key={`y${i}`}>
            <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} stroke="var(--border)" />
            <text x={M.left - 8} y={y(t) + 4} textAnchor="end" fontSize={11} fill="var(--text-dim)">
              {t.toFixed(0)}
            </text>
          </g>
        );
      })}
      <text x={(W + M.left) / 2} y={H - 6} textAnchor="middle" fontSize={12} fill="var(--text-dim)">
        composition x_Al
      </text>
      <text
        x={14}
        y={(H - M.bottom + M.top) / 2}
        textAnchor="middle"
        fontSize={12}
        fill="var(--text-dim)"
        transform={`rotate(-90 14 ${(H - M.bottom + M.top) / 2})`}
      >
        temperature (K)
      </text>

      {/* ordered region + boundary */}
      {orderedPath && <path d={orderedPath} fill="var(--good)" opacity={0.08} />}
      {boundaryPath && (
        <path d={boundaryPath} fill="none" stroke="var(--good)" strokeWidth={1.75} />
      )}
      {boundary.length > 0 && (
        <>
          <text
            x={x(boundary.reduce((a, s) => a + s.x, 0) / boundary.length)}
            y={y(tMin + 0.12 * (tMax - tMin))}
            textAnchor="middle"
            fontSize={12}
            fill="var(--good)"
          >
            ordered
          </text>
          <text
            x={x(boundary.reduce((a, s) => a + s.x, 0) / boundary.length)}
            y={y(tMax - 0.08 * (tMax - tMin))}
            textAnchor="middle"
            fontSize={12}
            fill="var(--text-dim)"
          >
            disordered solid solution
          </text>
        </>
      )}

      {/* measured MC points, colored by SRO (ordered = green, disordered = dim) */}
      {slices.flatMap((s) =>
        s.measured.map((m, i) => (
          <circle
            key={`${s.x}-${i}`}
            cx={x(s.x)}
            cy={y(m.temperature)}
            r={2.5}
            fill={m.sro < -0.15 ? "var(--good)" : "var(--text-dim)"}
            opacity={0.75}
          />
        )),
      )}

      {/* boundary estimates with uncertainty bars */}
      {slices.map((s) => {
        if (s.tc_mean == null) return null;
        const selected = s.x === selectedX;
        return (
          <g
            key={s.x}
            onClick={() => onSelect?.(s.x)}
            style={{ cursor: onSelect ? "pointer" : "default" }}
          >
            {s.tc_std != null && s.tc_std > 0 && (
              <line
                x1={x(s.x)}
                x2={x(s.x)}
                y1={y(Math.min(s.tc_mean + s.tc_std, tMax))}
                y2={y(Math.max(s.tc_mean - s.tc_std, tMin))}
                stroke="var(--warn)"
                strokeWidth={3}
                opacity={0.5}
              />
            )}
            {selected && (
              <circle cx={x(s.x)} cy={y(s.tc_mean)} r={9} fill="none" stroke="var(--warn)" strokeWidth={1.5} />
            )}
            <circle cx={x(s.x)} cy={y(s.tc_mean)} r={4.5} fill="var(--warn)" stroke="#0b0f14" strokeWidth={1} />
            <text x={x(s.x) + 8} y={y(s.tc_mean) - 8} fontSize={11} fill="var(--warn)">
              {s.tc_edge_pinned
                ? `≲ ${s.tc_mean.toFixed(0)} K (edge)`
                : `${s.tc_mean.toFixed(0)}±${s.tc_std?.toFixed(0) ?? "?"} K`}
            </text>
          </g>
        );
      })}

      {/* legend */}
      <g fontSize={11} fill="var(--text-dim)">
        <circle cx={M.left + 12} cy={M.top + 8} r={4.5} fill="var(--warn)" />
        <text x={M.left + 22} y={M.top + 12}>T̂c(x) ± σ (boundary)</text>
        <circle cx={M.left + 172} cy={M.top + 8} r={2.5} fill="var(--good)" />
        <text x={M.left + 182} y={M.top + 12}>MC run (ordered)</text>
        <circle cx={M.left + 302} cy={M.top + 8} r={2.5} fill="var(--text-dim)" />
        <text x={M.left + 312} y={M.top + 12}>MC run (disordered)</text>
      </g>
    </svg>
  );
}
