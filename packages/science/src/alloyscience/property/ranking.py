"""Candidate ranking (plan section 14): stable + high property + uncertainty.

Score = predicted bulk modulus for structures within `stable_tol` of the
predicted hull; candidates additionally carry a finite-temperature verdict
(ordered / disordered / unverified at the threshold temperature) supplied by
canonical Monte Carlo on the fitted cluster expansion.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Candidate:
    label: str
    x: float
    e_form: float
    e_form_std: float
    e_above_hull: float
    bulk_modulus: float
    bulk_modulus_std: float
    measured: bool
    stable_0k: bool
    stability_at_threshold: str  # "ordered" | "disordered" | "unverified" | "n/a"
    score: float

    def to_dict(self) -> dict:
        return asdict(self)


def rank_candidates(
    labels: list[str],
    x: list[float],
    e_form: list[float],
    e_form_std: list[float],
    e_above_hull: list[float],
    bulk_modulus: list[float],
    bulk_modulus_std: list[float],
    measured: list[bool],
    stable_tol: float,
    verification_by_x: dict[float, str] | None = None,
) -> list[Candidate]:
    """Rank by bulk modulus among (near-)hull structures; endpoints excluded
    from the intermetallic search but kept as references in the table."""
    verification_by_x = verification_by_x or {}
    candidates: list[Candidate] = []
    for i, label in enumerate(labels):
        stable = e_above_hull[i] <= stable_tol + 1e-12
        is_endpoint = x[i] in (0.0, 1.0)
        verdict = "n/a" if is_endpoint else verification_by_x.get(round(x[i], 6), "unverified")
        penalty = 0.0 if verdict in ("ordered", "unverified", "n/a") else 1e6
        score = (bulk_modulus[i] - penalty) if stable else -1e9
        candidates.append(
            Candidate(
                label=label,
                x=x[i],
                e_form=e_form[i],
                e_form_std=e_form_std[i],
                e_above_hull=e_above_hull[i],
                bulk_modulus=bulk_modulus[i],
                bulk_modulus_std=bulk_modulus_std[i],
                measured=measured[i],
                stable_0k=stable,
                stability_at_threshold=verdict,
                score=score,
            )
        )
    candidates.sort(key=lambda c: (-c.score, c.e_form))
    return candidates
