"use client";

/**
 * Dependency-free 3D crystal viewer: isometric orthographic projection of the
 * periodic cell repeated 2x2x2, depth-sorted spheres colored by element.
 */

import { useMemo } from "react";
import type { StructureRead } from "@alloylab/api-client";

const ELEMENT_STYLE: Record<number, { color: string; name: string; r: number }> = {
  28: { color: "#aeb9c6", name: "Ni", r: 11 },
  13: { color: "#4cc2ff", name: "Al", r: 13 },
};

type V3 = [number, number, number];

function add(a: V3, b: V3): V3 {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
}
function scale(a: V3, s: number): V3 {
  return [a[0] * s, a[1] * s, a[2] * s];
}

// Fixed isometric-ish rotation: yaw then pitch.
function project(p: V3): { x: number; y: number; depth: number } {
  const yaw = Math.PI / 7;
  const pitch = Math.PI / 5.5;
  const cy = Math.cos(yaw), sy = Math.sin(yaw);
  const cp = Math.cos(pitch), sp = Math.sin(pitch);
  const x1 = p[0] * cy + p[1] * sy;
  const y1 = -p[0] * sy + p[1] * cy;
  const y2 = y1 * cp + p[2] * sp;
  const z2 = -y1 * sp + p[2] * cp;
  return { x: x1, y: -y2, depth: z2 };
}

const REPEAT = 2;
const W = 420;
const H = 340;

export function Structure3DViewer({ structure }: { structure: StructureRead }) {
  const { atoms, edges } = useMemo(() => {
    const lat = (structure.lattice ?? []) as unknown as V3[];
    const pos = (structure.positions ?? []) as unknown as V3[];
    const nums = structure.atomic_numbers ?? [];
    if (lat.length !== 3 || pos.length === 0) return { atoms: [], edges: [] };

    const atoms: { x: number; y: number; depth: number; z: number }[] = [];
    for (let i = 0; i < REPEAT; i++)
      for (let j = 0; j < REPEAT; j++)
        for (let k = 0; k < REPEAT; k++) {
          const shift = add(add(scale(lat[0], i), scale(lat[1], j)), scale(lat[2], k));
          pos.forEach((p, idx) => {
            const proj = project(add(p, shift));
            atoms.push({ ...proj, z: nums[idx] });
          });
        }

    // Edges of the repeated parallelepiped.
    const a = scale(lat[0], REPEAT), b = scale(lat[1], REPEAT), c = scale(lat[2], REPEAT);
    const corners: V3[] = [
      [0, 0, 0], a, b, c, add(a, b), add(a, c), add(b, c), add(add(a, b), c),
    ];
    const pairs: [number, number][] = [
      [0, 1], [0, 2], [0, 3], [1, 4], [1, 5], [2, 4], [2, 6], [3, 5], [3, 6],
      [4, 7], [5, 7], [6, 7],
    ];
    const proj = corners.map(project);
    const edges = pairs.map(([i, j]) => ({ p1: proj[i], p2: proj[j] }));

    // Normalize to viewBox.
    const xs = [...atoms.map((p) => p.x), ...proj.map((p) => p.x)];
    const ys = [...atoms.map((p) => p.y), ...proj.map((p) => p.y)];
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const s = Math.min((W - 60) / (maxX - minX || 1), (H - 60) / (maxY - minY || 1));
    const tx = (x: number) => 30 + (x - minX) * s;
    const ty = (y: number) => 30 + (y - minY) * s;

    return {
      atoms: atoms
        .map((p) => ({ ...p, x: tx(p.x), y: ty(p.y) }))
        .sort((p, q) => p.depth - q.depth),
      edges: edges.map((e) => ({
        x1: tx(e.p1.x), y1: ty(e.p1.y), x2: tx(e.p2.x), y2: ty(e.p2.y),
      })),
    };
  }, [structure]);

  if (atoms.length === 0) {
    return <p className="p-4 text-sm text-[var(--text-dim)]">No 3D data.</p>;
  }

  const depths = atoms.map((a) => a.depth);
  const minD = Math.min(...depths), maxD = Math.max(...depths);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="max-h-72 w-full">
      {edges.map((e, i) => (
        <line key={i} {...e} stroke="var(--border)" strokeWidth={1} />
      ))}
      {atoms.map((a, i) => {
        const style = ELEMENT_STYLE[a.z] ?? { color: "var(--warn)", name: "?", r: 11 };
        const t = maxD > minD ? (a.depth - minD) / (maxD - minD) : 1;
        const r = style.r * (0.55 + 0.45 * t);
        return (
          <circle
            key={i}
            cx={a.x}
            cy={a.y}
            r={r}
            fill={style.color}
            opacity={0.45 + 0.55 * t}
            stroke="#0b0f14"
            strokeWidth={1}
          />
        );
      })}
    </svg>
  );
}
