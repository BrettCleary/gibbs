/** Shared vocabulary for problem types so labels stay consistent across pages. */

export type ProblemType =
  | "property_v3"
  | "dft_v3"
  | "phase_v2"
  | "fcc_v2"
  | "alloy_v1"
  | "ising_v0";

export const PROBLEMS: Record<
  ProblemType,
  { short: string; long: string; milestone: string; budgetLabel: string }
> = {
  property_v3: {
    short: "Property search",
    long: "Stiffest stable Ni–Al ordering, verified ordered at threshold T",
    milestone: "M8 · stiff & stable",
    budgetLabel: "query budget",
  },
  dft_v3: {
    short: "Real calculator",
    long: "Formation-energy hull with a real ASE energy engine",
    milestone: "M6 · ASE / QE",
    budgetLabel: "query budget",
  },
  phase_v2: {
    short: "Phase diagram",
    long: "Order/disorder boundary Tc(x) from canonical Monte Carlo",
    milestone: "M5 · mchammer",
    budgetLabel: "MC budget",
  },
  fcc_v2: {
    short: "FCC Ni–Al",
    long: "icet cluster expansion over symmetry-enumerated FCC orderings",
    milestone: "V2 · icet",
    budgetLabel: "oracle budget",
  },
  alloy_v1: {
    short: "Binary alloy",
    long: "2D lattice alloy with a hidden pair Hamiltonian",
    milestone: "V1 · lattice",
    budgetLabel: "oracle budget",
  },
  ising_v0: {
    short: "Ising",
    long: "Locate the 2D Ising critical region with finite MC budget",
    milestone: "V0 · ising",
    budgetLabel: "MC budget",
  },
};

export function problemInfo(type: string | undefined) {
  return PROBLEMS[(type ?? "ising_v0") as ProblemType] ?? PROBLEMS.ising_v0;
}

export const isAlloyLike = (t?: string) =>
  t === "alloy_v1" || t === "fcc_v2" || t === "dft_v3" || t === "property_v3";
