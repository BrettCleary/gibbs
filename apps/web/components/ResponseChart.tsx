"use client";

/**
 * Susceptibility-vs-temperature chart: surrogate mean curve, ±2σ ensemble
 * uncertainty band, measured points with error bars, and the current Tc
 * estimate. Hand-rolled SVG: dense, dependency-free, scientific.
 */

type Props = {
  curveT: number[];
  curveMean: number[];
  curveStd: number[];
  pointsT: number[];
  pointsY: number[];
  pointsErr: number[];
  tcMean: number | null | undefined;
  tcStd: number | null | undefined;
  tMin: number;
  tMax: number;
  xLabel?: string;
  yLabel?: string;
  peakPrefix?: string;
  legendCurve?: string;
};

const W = 760;
const H = 380;
const M = { top: 16, right: 16, bottom: 40, left: 56 };

export function ResponseChart(props: Props) {
  const { curveT, curveMean, curveStd, pointsT, pointsY, pointsErr } = props;

  const allY = [
    ...pointsY.map((y, i) => y + (pointsErr[i] ?? 0)),
    ...curveMean.map((m, i) => m + 2 * (curveStd[i] ?? 0)),
    1,
  ];
  const yMax = Math.max(...allY) * 1.08;
  const x = (t: number) =>
    M.left + ((t - props.tMin) / (props.tMax - props.tMin)) * (W - M.left - M.right);
  const y = (v: number) => H - M.bottom - (Math.max(v, 0) / yMax) * (H - M.top - M.bottom);

  const bandPath =
    curveT.length > 1
      ? [
          ...curveT.map((t, i) => `${i === 0 ? "M" : "L"}${x(t)},${y(curveMean[i] + 2 * curveStd[i])}`),
          ...[...curveT].reverse().map((t, ri) => {
            const i = curveT.length - 1 - ri;
            return `L${x(t)},${y(Math.max(curveMean[i] - 2 * curveStd[i], 0))}`;
          }),
          "Z",
        ].join(" ")
      : "";

  const meanPath =
    curveT.length > 1
      ? curveT.map((t, i) => `${i === 0 ? "M" : "L"}${x(t)},${y(curveMean[i])}`).join(" ")
      : "";

  const xTicks = 6;
  const yTicks = 5;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {/* grid + axes */}
      {Array.from({ length: xTicks + 1 }, (_, i) => {
        const t = props.tMin + ((props.tMax - props.tMin) * i) / xTicks;
        return (
          <g key={`x${i}`}>
            <line x1={x(t)} x2={x(t)} y1={M.top} y2={H - M.bottom} stroke="var(--border)" strokeWidth={1} />
            <text x={x(t)} y={H - M.bottom + 18} textAnchor="middle" fontSize={11} fill="var(--text-dim)">
              {t.toFixed(props.tMax > 100 ? 0 : 2)}
            </text>
          </g>
        );
      })}
      {Array.from({ length: yTicks + 1 }, (_, i) => {
        const v = (yMax * i) / yTicks;
        return (
          <g key={`y${i}`}>
            <line x1={M.left} x2={W - M.right} y1={y(v)} y2={y(v)} stroke="var(--border)" strokeWidth={1} />
            <text x={M.left - 8} y={y(v) + 4} textAnchor="end" fontSize={11} fill="var(--text-dim)">
              {v.toFixed(yMax < 10 ? 1 : 0)}
            </text>
          </g>
        );
      })}
      <text x={(W + M.left) / 2} y={H - 6} textAnchor="middle" fontSize={11} fill="var(--text-dim)">
        {props.xLabel ?? "temperature T (J/k_B)"}
      </text>
      <text
        x={14}
        y={(H - M.bottom + M.top) / 2}
        textAnchor="middle"
        fontSize={11}
        fill="var(--text-dim)"
        transform={`rotate(-90 14 ${(H - M.bottom + M.top) / 2})`}
      >
        {props.yLabel ?? "susceptibility χ"}
      </text>

      {/* Tc estimate band + line */}
      {props.tcMean != null && (
        <>
          {props.tcStd != null && props.tcStd > 0 && (
            <rect
              x={x(Math.max(props.tcMean - props.tcStd, props.tMin))}
              width={
                x(Math.min(props.tcMean + props.tcStd, props.tMax)) -
                x(Math.max(props.tcMean - props.tcStd, props.tMin))
              }
              y={M.top}
              height={H - M.top - M.bottom}
              fill="var(--warn)"
              opacity={0.12}
            />
          )}
          <line
            x1={x(props.tcMean)}
            x2={x(props.tcMean)}
            y1={M.top}
            y2={H - M.bottom}
            stroke="var(--warn)"
            strokeDasharray="4 3"
            strokeWidth={1.5}
          />
          <text x={x(props.tcMean) + 5} y={M.top + 30} fontSize={11} fill="var(--warn)">
            {props.peakPrefix ?? "T̂c = "}
            {props.tcMean.toFixed(props.tMax > 100 ? 0 : 3)}
            {props.tcStd != null ? ` ± ${props.tcStd.toFixed(props.tMax > 100 ? 0 : 3)}` : ""}
          </text>
        </>
      )}

      {/* surrogate: uncertainty band (prediction, NOT measurement) + mean */}
      {bandPath && <path d={bandPath} fill="var(--accent)" opacity={0.14} />}
      {meanPath && (
        <path d={meanPath} fill="none" stroke="var(--accent)" strokeWidth={1.75} strokeDasharray="6 3" />
      )}

      {/* measured points: solid — these are real simulation results */}
      {pointsT.map((t, i) => (
        <g key={i}>
          <line
            x1={x(t)}
            x2={x(t)}
            y1={y(pointsY[i] - (pointsErr[i] ?? 0))}
            y2={y(pointsY[i] + (pointsErr[i] ?? 0))}
            stroke="var(--text)"
            strokeWidth={1.25}
          />
          <circle cx={x(t)} cy={y(pointsY[i])} r={3.5} fill="var(--text)" />
        </g>
      ))}

      {/* legend */}
      <g fontSize={11} fill="var(--text-dim)">
        <circle cx={W - 220} cy={M.top + 8} r={3.5} fill="var(--text)" />
        <text x={W - 210} y={M.top + 12}>measured (MC)</text>
        <line x1={W - 118} x2={W - 92} y1={M.top + 8} y2={M.top + 8} stroke="var(--accent)" strokeWidth={1.75} strokeDasharray="6 3" />
        <text x={W - 86} y={M.top + 12}>{props.legendCurve ?? "surrogate ±2σ"}</text>
      </g>
    </svg>
  );
}
