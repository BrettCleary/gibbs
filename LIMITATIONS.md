# Limitations

Gibbs is a working demonstration of an autonomous materials-discovery loop — agent
decisions, typed simulation jobs, surrogate models with uncertainty, failure recovery,
finite-temperature verification, and a scientific report with provenance. It is **not**
a validated tool for producing publishable alloy thermodynamics, and this page says
exactly where the line falls.

Every campaign report generates its own limitations section from the persisted record
(`_limitations()` in `apps/api/src/gibbs/report.py`), so a run always states its own
caveats. This document is the standing version.

## Physics

**DFT settings are demo-grade.** The Quantum ESPRESSO path
(`packages/science/src/alloyscience/calculators/espresso.py`) runs PBE at `ecutwfc`
40 Ry / `ecutrho` 320 Ry, a Monkhorst-Pack grid derived from `kspacing` 0.28 Å⁻¹,
Marzari-Vanderbilt smearing with `degauss` 0.02 Ry, and `conv_thr` 1e-6. These are
chosen so a campaign finishes in minutes, not so the numbers converge. None of them
has been subjected to a convergence study.

**Calculations are non-spin-polarised.** This is the most consequential setting here.
Ni is ferromagnetic, and a non-spin-polarised calculation gets its energetics wrong —
so any Ni-containing result is qualitative at best. The same applies to Fe and Co.

**Geometries are not relaxed.** The default is a single-point SCF at a Vegard-scaled
lattice. With `n_volumes > 1` the E(V) scan adds isotropic volume relaxation and a
curvature-derived bulk modulus, but ionic positions are never relaxed, so ordered
structures are evaluated at ideal FCC sites rather than at their true geometry.

**EMT is qualitative only.** The `emt` engine is ASE's classical effective-medium
potential, fitted to pure-element properties. Its mixing energetics are not reliable —
for Ni-Al it predicts phase separation, so a Ni-Al hull campaign on EMT returns the
pure endpoints and nothing else. It is useful as a fast, deterministic stand-in for a
real engine, not as a source of alloy chemistry.

**The cluster expansion is pair-only and small.** The default cluster space uses a
single pair cutoff of 5.5 Å (~1.5 lattice constants, scaled per element pair), with no
triplet or higher-order clusters, over orderings enumerated on cells of at most 5
atoms (`fcc/system.py`). Real cluster expansions for these systems use multi-body
clusters and larger cells. Fits are LOOCV-validated with bootstrap uncertainty, but a
typical campaign trains on 10-20 points; the reported ensemble spread is the honest
uncertainty on that, and predictions for unmeasured structures should be treated as
extrapolation.

**Finite-temperature verification runs on the agent's own fitted model.** Canonical MC
(`fcc/mc.py`, mchammer) samples the *fitted* cluster expansion in a 4x4x4 (64-atom)
supercell, not the reference engine. The order/disorder verdict therefore inherits the
surrogate's error, and 64 atoms is small for a transition temperature.

**Phase-boundary estimates pinned at a window edge are bounds, not locations.** When
the heat-capacity peak for a composition slice falls at the edge of the scanned
temperature range, the reported Tc is an upper or lower bound. These are flagged as
such in the dashboard, the report, and the recommendation text — but they are still
frequently what a short campaign produces.

**Non-FCC elements are modelled on a hypothetical lattice.** Elements that are not FCC
at ambient conditions (Fe, Ti, …) are allowed, placed on an equal-atomic-volume FCC
lattice, and flagged wherever they appear. Results for those pairs describe a lattice
that does not exist.

**The synthetic problems validate the method, not the chemistry.** `ising_v0`,
`alloy_v1`, `fcc_v2`, `phase_v2` and the `property_v3` oracle draw energies from hidden
Hamiltonians with exact ground truth. That is the point — it is how search quality is
measured at all — but no result from those problems says anything about real materials.

## Evaluation

**The benchmark scores acquisition strategies, not the LLM.** `POST /benchmarks`
explicitly rejects the `agent` strategy: it compares the deterministic baselines
(`random`, `grid`, `uncertainty`) so a stochastic decider is never averaged into a
table of deterministic ones. An LLM-driven run is assessed by reading its campaign
report. There is no automated measurement of whether the LLM decider beats the coded
baselines.

**Active selection has not been shown to beat random here.** At the settings currently
run — budget 20, three seeds — plain `random` beats `uncertainty` sampling on both the
binary-alloy hull (RMSE 0.0161 vs 0.0185) and the Ni-Al phase boundary (mean |Tc error|
78 K vs 93 K). Three seeds is too few to conclude much in either direction, and the
regime where active selection pays for itself (larger budgets, costlier engines, more
seeds) has not been mapped. The harness exists to answer that; it has not yet.

## Engineering

**The hosted instance's compute depends on which workers are connected.** With
`executor=temporal`, the API does not run calculations at all: it hands each campaign
to the `gibbs-calculations` task queue, and a worker process runs the loop and its
calculations in-process. So [gibbs.app](https://gibbs.app) can run real Quantum
ESPRESSO whenever a worker with a `pw.x` binary is polling that queue — but there is no
always-on worker pool, so DFT availability and throughput track whoever currently has a
worker up. When no worker is connected, campaigns queue durably and resume when one
returns rather than failing; that is the durability property behaving as designed, but
it does mean the hosted demo is not self-contained.

## What would have to change for research use

In rough order of how much each one matters:

1. Spin-polarised calculations, and a convergence study over `ecutwfc`, k-mesh, and
   smearing before any number is quoted.
2. Ionic relaxation, so ordered structures are evaluated at their real geometry.
3. A cluster expansion with multi-body clusters, larger enumerated cells, and enough
   training data for the LOOCV error to be meaningful.
4. Larger MC supercells with finite-size scaling, and verification against the
   reference engine rather than only the fitted surrogate.
5. A benchmark regime where the acquisition strategy demonstrably beats random,
   established across enough seeds to be a result rather than a run.
