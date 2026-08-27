"""Quantum ESPRESSO energy calculator via ASE (Milestone 6).

Single-point SCF at the Vegard-interpolated lattice constant for the
structure's composition. Runs pw.x in an explicit working directory so the
input/output files survive as artifacts; parses the .pwo for SCF convergence
and raises categorised SimulationFailures the agent's retry machinery already
understands (retry parameters: electron_maxstep, mixing_beta).

Demo-grade settings: non-spin-polarised, Marzari-Vanderbilt smearing, PAW
pseudopotentials, modest cutoffs. Not publication physics — the point is the
pipeline: real DFT behind the same EnergyCalculator boundary as the toys.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..errors import SimulationFailure
from ..fcc.system import FccStructure
from .base import EnergyResult, structure_to_atoms, vegard_scale

DEFAULT_PSEUDOS = {
    "Ni": "Ni.pbe-spn-kjpaw_psl.1.0.0.UPF",
    "Al": "Al.pbe-n-kjpaw_psl.1.0.0.UPF",
}


def resolve_pseudopotentials(pseudo_dir: str | Path, elements: list[str]) -> tuple[dict, list[str]]:
    """Find a UPF file per element in `pseudo_dir` (`<El>.*.UPF`, PAW/PBE
    preferred). Returns (mapping, missing_elements)."""
    pseudo_dir = Path(pseudo_dir)
    found: dict[str, str] = {}
    missing: list[str] = []
    for el in elements:
        candidates = sorted(
            [p.name for p in pseudo_dir.glob(f"{el}.*") if p.suffix.lower() == ".upf"],
            key=lambda n: (("kjpaw" not in n), ("pbe" not in n), n),
        )
        if candidates:
            found[el] = candidates[0]
        else:
            missing.append(el)
    return found, missing


@dataclass(frozen=True)
class EspressoConfig:
    pw_command: str = "pw.x"
    pseudo_dir: str = "infra/pseudopotentials"
    pseudopotentials: dict = field(default_factory=lambda: dict(DEFAULT_PSEUDOS))
    ecutwfc: float = 40.0  # Ry
    ecutrho: float = 320.0
    kspacing: float = 0.28  # 1/Angstrom (Monkhorst-Pack grid derived per cell)
    degauss: float = 0.02
    conv_thr: float = 1e-6
    mixing_beta: float = 0.4
    mixing_mode: str = "local-TF"  # robust for metallic, elongated cells
    electron_maxstep: int = 60
    # E(V) scan for bulk modulus (Milestone 9): n_volumes single-points at
    # isotropic scales around the Vegard lattice; 0/1 = single-point only.
    n_volumes: int = 1
    volume_scan_span: float = 0.06  # +/- fractional lattice-scale span
    # Parent FCC lattice constant the pool cells were built at (element A).
    a_parent: float = 3.52

    def to_dict(self) -> dict:
        return {
            "pw_command": self.pw_command,
            "pseudo_dir": self.pseudo_dir,
            "pseudopotentials": dict(self.pseudopotentials),
            "ecutwfc": self.ecutwfc,
            "ecutrho": self.ecutrho,
            "kspacing": self.kspacing,
            "degauss": self.degauss,
            "conv_thr": self.conv_thr,
            "mixing_beta": self.mixing_beta,
            "mixing_mode": self.mixing_mode,
            "electron_maxstep": self.electron_maxstep,
            "n_volumes": self.n_volumes,
            "volume_scan_span": self.volume_scan_span,
            "a_parent": self.a_parent,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EspressoConfig":
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


def espresso_available(config: EspressoConfig) -> tuple[bool, str]:
    if shutil.which(config.pw_command) is None and not Path(config.pw_command).is_file():
        return False, f"pw.x not found at {config.pw_command!r}"
    pseudo_dir = Path(config.pseudo_dir)
    missing = [
        f for f in config.pseudopotentials.values() if not (pseudo_dir / f).is_file()
    ]
    if missing:
        return False, f"missing pseudopotentials in {pseudo_dir}: {missing}"
    return True, "ok"


def _kpoint_grid(cell: np.ndarray, kspacing: float) -> tuple[int, int, int]:
    reciprocal = 2.0 * np.pi * np.linalg.inv(cell).T
    lengths = np.linalg.norm(reciprocal, axis=1)
    return tuple(max(1, int(np.ceil(l / kspacing))) for l in lengths)


class EspressoFccCalculator:
    name = "espresso"

    def __init__(self, config: EspressoConfig, overrides: dict | None = None):
        self.config = config
        # Per-run overrides (retry adjustments): electron_maxstep, mixing_beta.
        self.overrides = overrides or {}

    def compute(self, structure: FccStructure, workdir: Path | None = None) -> EnergyResult:
        ok, reason = espresso_available(self.config)
        if not ok:
            raise SimulationFailure(
                category="ENGINE_UNAVAILABLE", message=reason, metadata={"engine": "espresso"}
            )
        workdir = Path(workdir) if workdir is not None else Path("espresso-run")
        workdir.mkdir(parents=True, exist_ok=True)
        base_scale = vegard_scale(structure, a_reference=self.config.a_parent)
        if self.config.n_volumes <= 1:
            return self._single_point(structure, base_scale, workdir)
        return self._volume_scan(structure, base_scale, workdir)

    def _volume_scan(self, structure: FccStructure, base_scale: float, workdir: Path) -> EnergyResult:
        """E(V) at n_volumes isotropic scales -> parabolic minimum, bulk modulus.

        B = V d2E/dV2 = (d2E/ds2) / (9 V0 s) at the minimum (V = V0 s^3).
        Each point is a full SCF in its own subdirectory (all logs kept).
        """
        n = int(self.config.n_volumes)
        span = float(self.config.volume_scan_span)
        scales = base_scale * (1.0 + np.linspace(-span, span, n))
        energies, iterations = [], []
        for k, s in enumerate(scales):
            r = self._single_point(structure, float(s), workdir / f"v{k}")
            energies.append(r.energy_per_atom * structure.n_sites)
            iterations.append(r.details.get("scf_iterations"))
        e = np.array(energies)
        a, b, c = np.polyfit(scales, e, 2)
        if a <= 0:
            raise SimulationFailure(
                category="EOS_FIT_FAILED",
                message="E(V) scan is not convex; cannot extract a bulk modulus",
                metadata={"scales": [float(v) for v in scales], "energies": [float(v) for v in e]},
            )
        s_opt = float(-b / (2.0 * a))
        s_opt = float(min(max(s_opt, scales[0]), scales[-1]))
        e_opt = float(a * s_opt**2 + b * s_opt + c)
        v0 = float(abs(np.linalg.det(np.array(structure.cell))))
        bulk_modulus_gpa = float((2.0 * a) / (9.0 * v0 * s_opt) * 160.21766)
        return EnergyResult(
            energy_per_atom=e_opt / structure.n_sites,
            lattice_scale=s_opt,
            details={
                "engine": "quantum-espresso pw.x (scf x E(V) scan)",
                "n_volumes": n,
                "scales": [float(v) for v in scales],
                "energies_ev": [float(v) for v in e],
                "optimal_lattice_constant": self.config.a_parent * s_opt,
                "bulk_modulus_gpa": bulk_modulus_gpa,
                "scf_iterations": iterations,
                "vegard_lattice_scale": base_scale,
                "spin_polarised": False,
            },
            log_path=str(workdir / f"v{n // 2}" / "espresso.pwo"),
        )

    def _single_point(self, structure: FccStructure, scale: float, workdir: Path) -> EnergyResult:
        from ase.calculators.espresso import Espresso, EspressoProfile

        workdir.mkdir(parents=True, exist_ok=True)
        atoms = structure_to_atoms(structure, scale=scale)
        electron_maxstep = int(self.overrides.get("electron_maxstep", self.config.electron_maxstep))
        mixing_beta = float(self.overrides.get("mixing_beta", self.config.mixing_beta))
        input_data = {
            "control": {"calculation": "scf", "disk_io": "none"},
            "system": {
                "ecutwfc": self.config.ecutwfc,
                "ecutrho": self.config.ecutrho,
                "occupations": "smearing",
                "smearing": "mv",
                "degauss": self.config.degauss,
            },
            "electrons": {
                "conv_thr": self.config.conv_thr,
                "mixing_beta": mixing_beta,
                "mixing_mode": self.config.mixing_mode,
                "electron_maxstep": electron_maxstep,
            },
        }
        profile = EspressoProfile(
            command=str(self.config.pw_command), pseudo_dir=str(Path(self.config.pseudo_dir).resolve())
        )
        atoms.calc = Espresso(
            profile=profile,
            pseudopotentials=dict(self.config.pseudopotentials),
            input_data=input_data,
            kpts=_kpoint_grid(np.array(atoms.get_cell()), self.config.kspacing),
            directory=str(workdir),
        )

        log_path = workdir / "espresso.pwo"
        try:
            energy = float(atoms.get_potential_energy())
        except Exception as exc:  # noqa: BLE001 — categorise from the pw.x log
            raise _failure_from_log(log_path, exc)

        n_iterations = _parse_iterations(log_path)
        return EnergyResult(
            energy_per_atom=energy / structure.n_sites,
            lattice_scale=scale,
            details={
                "engine": "quantum-espresso pw.x (scf)",
                "ecutwfc_ry": self.config.ecutwfc,
                "kpts": list(_kpoint_grid(np.array(atoms.get_cell()), self.config.kspacing)),
                "scf_iterations": n_iterations,
                "electron_maxstep": electron_maxstep,
                "mixing_beta": mixing_beta,
                "vegard_lattice_scale": scale,
                "spin_polarised": False,
            },
            log_path=str(log_path),
        )


def _parse_iterations(log_path: Path) -> int | None:
    try:
        text = log_path.read_text(errors="replace")
    except OSError:
        return None
    for line in reversed(text.splitlines()):
        if "convergence has been achieved in" in line:
            for token in line.split():
                if token.isdigit():
                    return int(token)
    return None


def _failure_from_log(log_path: Path, exc: Exception) -> SimulationFailure:
    text = ""
    try:
        text = log_path.read_text(errors="replace")
    except OSError:
        pass
    tail = "\n".join(text.splitlines()[-30:])
    if "convergence NOT achieved" in text:
        return SimulationFailure(
            category="SCF_NOT_CONVERGED",
            message="pw.x: electronic self-consistency did not converge",
            metadata={
                "hint": "raise electron_maxstep and/or lower mixing_beta, then retry",
                "log_tail": tail,
                "log_path": str(log_path),
            },
        )
    if "Error in routine" in text:
        return SimulationFailure(
            category="PW_RUNTIME_ERROR",
            message="pw.x reported an internal error",
            metadata={"log_tail": tail, "log_path": str(log_path)},
        )
    return SimulationFailure(
        category="ENGINE_CRASH",
        message=f"pw.x run failed: {exc}",
        metadata={"log_tail": tail, "log_path": str(log_path)},
    )
