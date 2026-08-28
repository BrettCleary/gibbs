"use client";

/**
 * Interactive 3D crystal viewer (three.js via react-three-fiber): the periodic
 * cell repeated 2x2x2 as lit spheres colored by element, with the supercell
 * outline and orbit controls (drag to rotate, wheel to zoom, slow auto-rotate
 * until the user grabs it).
 */

import { useMemo, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Line, OrbitControls } from "@react-three/drei";
import type { StructureRead } from "@gibbs/api-client";

/** Element rendering: the lower atomic number in a cell is drawn neutral, the
 *  higher one in the accent color; radius grows gently with Z. */
export const ELEMENT_NAMES: Record<number, string> = {
  13: "Al",
  26: "Fe",
  27: "Co",
  28: "Ni",
  29: "Cu",
  46: "Pd",
  47: "Ag",
  78: "Pt",
  79: "Au",
  82: "Pb",
  22: "Ti",
  23: "V",
  24: "Cr",
  25: "Mn",
  30: "Zn",
  40: "Zr",
  41: "Nb",
  42: "Mo",
  45: "Rh",
  77: "Ir",
  74: "W",
};
export function elementStyle(
  z: number,
  numbersInCell: number[],
): { color: string; name: string; r: number } {
  const sorted = [...new Set(numbersInCell)].sort((a, b) => a - b);
  const isSecond = sorted.length > 1 && z === sorted[sorted.length - 1];
  return {
    color: isSecond ? "#a4b4d0" : "#c9cdd3",
    name: ELEMENT_NAMES[z] ?? `Z${z}`,
    // Sphere radius in Å-ish units; scaled below relative to the cell.
    r: 0.45 + Math.min(z, 80) / 400,
  };
}

type V3 = [number, number, number];

function add(a: V3, b: V3): V3 {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
}
function scale(a: V3, s: number): V3 {
  return [a[0] * s, a[1] * s, a[2] * s];
}

const REPEAT = 2;

/** Inverse of a 3x3 matrix given as rows (lattice vectors); returns rows of the inverse. */
function invert3(m: V3[]): V3[] {
  const [a, b, c] = m;
  const det =
    a[0] * (b[1] * c[2] - b[2] * c[1]) -
    a[1] * (b[0] * c[2] - b[2] * c[0]) +
    a[2] * (b[0] * c[1] - b[1] * c[0]);
  const d = 1 / det;
  return [
    [
      (b[1] * c[2] - b[2] * c[1]) * d,
      (a[2] * c[1] - a[1] * c[2]) * d,
      (a[1] * b[2] - a[2] * b[1]) * d,
    ],
    [
      (b[2] * c[0] - b[0] * c[2]) * d,
      (a[0] * c[2] - a[2] * c[0]) * d,
      (a[2] * b[0] - a[0] * b[2]) * d,
    ],
    [
      (b[0] * c[1] - b[1] * c[0]) * d,
      (a[1] * c[0] - a[0] * c[1]) * d,
      (a[0] * b[1] - a[1] * b[0]) * d,
    ],
  ];
}
/** Cartesian -> fractional: solve r = f·L, i.e. f = r·L⁻¹ (row-vector convention). */
function matVec(inv: V3[], r: V3): V3 {
  return [
    r[0] * inv[0][0] + r[1] * inv[1][0] + r[2] * inv[2][0],
    r[0] * inv[0][1] + r[1] * inv[1][1] + r[2] * inv[2][1],
    r[0] * inv[0][2] + r[1] * inv[1][2] + r[2] * inv[2][2],
  ];
}

const EDGE_PAIRS: [number, number][] = [
  [0, 1],
  [0, 2],
  [0, 3],
  [1, 4],
  [1, 5],
  [2, 4],
  [2, 6],
  [3, 5],
  [3, 6],
  [4, 7],
  [5, 7],
  [6, 7],
];

function buildScene(structure: StructureRead) {
  const lat = (structure.lattice ?? []) as unknown as V3[];
  const pos = (structure.positions ?? []) as unknown as V3[];
  const nums = structure.atomic_numbers ?? [];
  if (lat.length !== 3 || pos.length === 0) return null;

  const a = scale(lat[0], REPEAT),
    b = scale(lat[1], REPEAT),
    c = scale(lat[2], REPEAT);
  const center = scale(add(add(a, b), c), 0.5);
  const centered = (p: V3): V3 => [p[0] - center[0], p[1] - center[1], p[2] - center[2]];

  // Fractional coordinates (wrapped into [0,1)) so atoms sit inside the drawn
  // cell regardless of how the enumerator placed them; then tile 0..REPEAT
  // *inclusive* and keep atoms on the far faces so corners/edges are populated.
  const inv = invert3(lat);
  const eps = 1e-6;
  const atoms: { p: V3; z: number }[] = [];
  pos.forEach((cart, idx) => {
    const f = matVec(inv, cart).map((v) => ((v % 1) + 1) % 1) as V3;
    for (let i = 0; i <= REPEAT; i++)
      for (let j = 0; j <= REPEAT; j++)
        for (let k = 0; k <= REPEAT; k++) {
          const g: V3 = [f[0] + i, f[1] + j, f[2] + k];
          if (g.some((v) => v > REPEAT + eps)) continue;
          const c = add(add(scale(lat[0], g[0]), scale(lat[1], g[1])), scale(lat[2], g[2]));
          atoms.push({ p: centered(c), z: nums[idx] });
        }
  });

  const rawCorners: V3[] = [[0, 0, 0], a, b, c, add(a, b), add(a, c), add(b, c), add(add(a, b), c)];
  const corners = rawCorners.map(centered);
  const edges = EDGE_PAIRS.map(([i, j]) => [corners[i], corners[j]] as [V3, V3]);

  // Bounding radius for camera fit.
  const radius = Math.max(...corners.map((p) => Math.hypot(...p)));
  return { atoms, edges, radius };
}

function Atoms({ atoms, numbers }: { atoms: { p: V3; z: number }[]; numbers: number[] }) {
  return (
    <>
      {atoms.map((atom, i) => {
        const style = elementStyle(atom.z, numbers);
        return (
          <mesh key={i} position={atom.p}>
            <sphereGeometry args={[style.r, 32, 32]} />
            <meshStandardMaterial color={style.color} metalness={0.35} roughness={0.4} />
          </mesh>
        );
      })}
    </>
  );
}

export function Structure3DViewer({ structure }: { structure: StructureRead }) {
  const scene = useMemo(() => buildScene(structure), [structure]);
  const [interacted, setInteracted] = useState(false);
  const numbers = structure.atomic_numbers ?? [];
  const controls = useRef(null);

  if (!scene) {
    return <p className="p-4 text-sm text-[var(--text-dim)]">No 3D data.</p>;
  }

  const dist = scene.radius * 2.6;

  return (
    <div className="relative h-72 w-full">
      <Canvas
        camera={{
          position: [dist * 0.6, dist * 0.45, dist * 0.7],
          fov: 35,
          near: 0.1,
          far: dist * 10,
        }}
        gl={{ antialias: true, alpha: true }}
        dpr={[1, 2]}
        style={{ background: "transparent" }}
      >
        <ambientLight intensity={0.6} />
        <directionalLight position={[5, 8, 6]} intensity={1.6} />
        <directionalLight position={[-6, -3, -4]} intensity={0.4} />
        <Atoms atoms={scene.atoms} numbers={numbers} />
        {scene.edges.map((e, i) => (
          <Line key={i} points={e} color="#3a3f47" lineWidth={1} transparent opacity={0.9} />
        ))}
        <OrbitControls
          ref={controls}
          enablePan={false}
          enableDamping
          dampingFactor={0.08}
          autoRotate={!interacted}
          autoRotateSpeed={0.8}
          minDistance={scene.radius * 1.2}
          maxDistance={dist * 3}
          onStart={() => setInteracted(true)}
        />
      </Canvas>
      <span className="pointer-events-none absolute right-2 bottom-1 font-mono text-[10px] text-text-muted">
        drag to rotate · scroll to zoom
      </span>
    </div>
  );
}
