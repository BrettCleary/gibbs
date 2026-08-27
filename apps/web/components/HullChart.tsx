"use client";

/**
 * Formation-energy convex hull: measured points (solid), surrogate predictions
 * with uncertainty bars (hollow), the predicted lower hull, and highlighted
 * predicted-stable structures. Click a point to inspect the structure.
 */

import type { HullPoint } from "@alloylab/api-client";

type Props = {
  points: HullPoint[];
  hullX: number[];
  hullE: number[];
  selectedLabel?: string | null;
  onSelect?: (p: HullPoint) => void;
};

const W = 760;
const H = 400;
const M = { top: 18, right: 16, bottom: 42, left: 60 };

export function HullChart({ points, hullX, hullE, selectedLabel, onSelect }: Props) {
  const values = points
    .filter((p) => p.e_form != null)
    .flatMap((p) => [(p.e_form ?? 0) - (p.e_form_std ?? 0), (p.e_form ?? 0) + (p.e_form_std ?? 0)]);
  const yMin = Math.min(...values, ...hullE, -0.1) * 1.12;
  const yMax = Math.max(...values, 0.05) * 1.12;

  const x = (v: number) => M.left + v * (W - M.left - M.right);
  const y = (v: number) => M.top + ((yMax - v) / (yMax - yMin)) * (H - M.top - M.bottom);

  const hullPath =
    hullX.length > 1
      ? hullX.map((hx, i) => `${i === 0 ? "M" : "L"}${x(hx)},${y(hullE[i])}`).join(" ")
      : "";

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
        const v = yMin + ((yMax - yMin) * i) / 5;
        return (
          <g key={`y${i}`}>
            <line x1={M.left} x2={W - M.right} y1={y(v)} y2={y(v)} stroke="var(--border)" />
            <text x={M.left - 8} y={y(v) + 4} textAnchor="end" fontSize={11} fill="var(--text-dim)">
              {v.toFixed(2)}
            </text>
          </g>
        );
      })}
      {/* zero line */}
      <line
        x1={M.left}
        x2={W - M.right}
        y1={y(0)}
        y2={y(0)}
        stroke="var(--text-dim)"
        strokeWidth={1}
        strokeDasharray="2 3"
      />
      <text x={(W + M.left) / 2} y={H - 6} textAnchor="middle" fontSize={11} fill="var(--text-dim)">
        composition x (B fraction)
      </text>
      <text
        x={14}
        y={(H - M.bottom + M.top) / 2}
        textAnchor="middle"
        fontSize={11}
        fill="var(--text-dim)"
        transform={`rotate(-90 14 ${(H - M.bottom + M.top) / 2})`}
      >
        formation energy ΔE_form / site
      </text>

      {/* predicted lower hull */}
      {hullPath && <path d={hullPath} fill="none" stroke="var(--good)" strokeWidth={1.75} />}

      {/* pool points */}
      {points.map((p) => {
        if (p.e_form == null) return null;
        const cx = x(p.x);
        const cy = y(p.e_form);
        const selected = p.label === selectedLabel;
        const color = p.predicted_stable
          ? "var(--good)"
          : p.measured
            ? "var(--text)"
            : "var(--accent)";
        return (
          <g
            key={p.label}
            onClick={() => onSelect?.(p)}
            style={{ cursor: onSelect ? "pointer" : "default" }}
          >
            {!p.measured && (p.e_form_std ?? 0) > 0 && (
              <line
                x1={cx}
                x2={cx}
                y1={y(p.e_form - (p.e_form_std ?? 0))}
                y2={y(p.e_form + (p.e_form_std ?? 0))}
                stroke={color}
                strokeWidth={1}
                opacity={0.6}
              />
            )}
            {selected && (
              <circle cx={cx} cy={cy} r={8} fill="none" stroke="var(--warn)" strokeWidth={1.5} />
            )}
            <circle
              cx={cx}
              cy={cy}
              r={p.predicted_stable ? 4.5 : 3.5}
              fill={p.measured ? color : "var(--bg)"}
              stroke={color}
              strokeWidth={1.5}
            />
          </g>
        );
      })}

      {/* legend */}
      <g fontSize={11} fill="var(--text-dim)">
        <circle cx={M.left + 12} cy={M.top + 8} r={3.5} fill="var(--text)" />
        <text x={M.left + 22} y={M.top + 12}>
          measured (oracle)
        </text>
        <circle
          cx={M.left + 152}
          cy={M.top + 8}
          r={3.5}
          fill="var(--panel)"
          stroke="var(--accent)"
          strokeWidth={1.5}
        />
        <text x={M.left + 162} y={M.top + 12}>
          CE prediction ±σ
        </text>
        <circle cx={M.left + 288} cy={M.top + 8} r={4.5} fill="var(--good)" />
        <text x={M.left + 300} y={M.top + 12}>
          predicted stable / hull
        </text>
      </g>
    </svg>
  );
}
