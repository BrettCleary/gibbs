"""Mini cluster-expansion surrogate for the binary-alloy problem.

Linear model over correlation features [1, f_point, f_nn, f_nnn] — exactly the
functional form of a pair cluster expansion. Fitted by least squares on the
queried structures; a bootstrap ensemble provides per-structure predictive
uncertainty, and leave-one-out cross-validation gives the validation error the
agent reasons about. Milestone 4 swaps this for icet without changing callers.
"""

from __future__ import annotations

import numpy as np


class ClusterExpansionSurrogate:
    MIN_POINTS = 4  # number of features; fewer rows would be underdetermined

    def __init__(
        self,
        features: np.ndarray,  # (n, k) design matrix rows for measured structures
        energies: np.ndarray,  # (n,) measured energies per site
        n_ensemble: int = 50,
        ridge: float = 1e-8,
        seed: int = 0,
    ):
        self.X = np.asarray(features, dtype=float)
        self.y = np.asarray(energies, dtype=float)
        if self.X.ndim != 2 or len(self.X) != len(self.y):
            raise ValueError("features must be (n, k) with matching energies (n,)")
        if len(self.y) < self.MIN_POINTS:
            raise ValueError(
                f"cluster expansion requires at least {self.MIN_POINTS} measurements, "
                f"got {len(self.y)}"
            )
        self.ridge = ridge
        self.n_ensemble = n_ensemble
        self._rng = np.random.default_rng(seed)
        self.coefficients = self._solve(self.X, self.y)
        self._ensemble = self._fit_ensemble()

    def _solve(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        k = x.shape[1]
        return np.linalg.solve(x.T @ x + self.ridge * np.eye(k), x.T @ y)

    def _fit_ensemble(self) -> np.ndarray:
        n = len(self.y)
        coefs = []
        for _ in range(self.n_ensemble):
            idx = self._rng.integers(0, n, size=n)
            coefs.append(self._solve(self.X[idx], self.y[idx]))
        return np.stack(coefs)

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(mean, std) energy per site for each feature row."""
        features = np.asarray(features, dtype=float)
        preds = features @ self._ensemble.T  # (m, n_ensemble)
        return preds.mean(axis=1), preds.std(axis=1)

    def loocv_rmse(self) -> float:
        """Leave-one-out cross-validation RMSE (brute force; n is small)."""
        n = len(self.y)
        if n <= self.MIN_POINTS:
            return float("nan")
        errors = []
        for i in range(n):
            mask = np.ones(n, dtype=bool)
            mask[i] = False
            coef = self._solve(self.X[mask], self.y[mask])
            errors.append(float(self.X[i] @ coef - self.y[i]))
        return float(np.sqrt(np.mean(np.square(errors))))

    def coefficient_summary(self) -> dict:
        mean = self._ensemble.mean(axis=0)
        std = self._ensemble.std(axis=0)
        k = self.X.shape[1]
        base = ["J0", "J_point", "J_nn", "J_nnn"]
        names = base[:k] + [f"ECI_{i}" for i in range(len(base), k)]
        return {
            name: {"mean": float(m), "std": float(s)}
            for name, m, s in zip(names, mean, std)
        }
