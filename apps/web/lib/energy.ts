/**
 * Display units for formation energies. The API reports real-engine energies in
 * eV/atom; on screen we show meV/atom (hull depths are typically tens of meV,
 * so "0.032" reads worse than "32"). Dimensionless hidden-Hamiltonian energies
 * pass through untouched.
 */

export type EnergyDisplay = {
  /** Unit label to show. */
  unit: string;
  /** Multiply an API value by this before displaying. */
  scale: number;
  /** Decimal places that make sense at this scale. */
  digits: number;
};

export function energyDisplay(apiUnit: string | null | undefined): EnergyDisplay {
  if (apiUnit === "eV/atom") return { unit: "meV/atom", scale: 1000, digits: 1 };
  return { unit: apiUnit ?? "", scale: 1, digits: 3 };
}

/** Format an API energy value in display units (no unit suffix). */
export function fmtEnergy(v: number | null | undefined, d: EnergyDisplay): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return (v * d.scale).toFixed(d.digits);
}
