# Long-term goal: from a stability engine to a research agent

This document records where the platform sits today, what the *actual* top-level
objectives look like, and how we intend to build toward them. It is a direction,
not a schedule. `docs/project_description.md` is the original nine-milestone plan
(implemented); this is what comes after it.

## 1. The hierarchy of objectives

A materials scientist's real question is never "which FCC ordering of Cu and Au
is lowest in energy". That is an *instrumental* question several levels below
the goal they actually care about:

```
application goal        "a better electrode for a Na-ion battery"
   ↓ figures of merit    voltage, capacity, volume change on cycling, ionic mobility, cost, safety
   ↓ candidate systems   which chemistries / lattices could plausibly deliver them
   ↓ structure & thermo  which orderings are stable, at what compositions, up to what T   ← what we built
   ↓ experiments         DFT energies, MC runs
```

What exists today is the **structure & thermodynamics layer**, done properly for
one class of system (binary orderings on a fixed FCC parent lattice), with the
**experiments layer** real (Quantum ESPRESSO, EMT, mchammer, Temporal-durable).

That is worth having: thermodynamic stability is the universal constraint every
application goal has to pass — "does this phase even exist?" — and it is the
layer most demos skip. But it is one engine, not the scientist.

## 2. Who decides what, at each level

The benchmarks taught us a design principle: **an LLM should not do what a
deterministic tool does better.** Choosing the numerically optimal next
experiment is an acquisition problem; bootstrap-ensemble uncertainty sampling
does it in microseconds and, in our benchmarks, does it at least as well as any
narrated choice. Where a language model earns its keep is one level up — the
judgement calls about a specific state that have no closed form.

| level | who | examples of the decision |
|---|---|---|
| point selection | deterministic tools | `propose_by_uncertainty`, `propose_by_coverage`, `propose_property_directed`, `propose_peak_refinement` |
| campaign reasoning | the **campaign agent** | which acquisition rule fits this stage; how to split budget across hull discovery, verification, and boundary mapping; whether the hull is resolved enough to advance; which candidates deserve finite-T verification and at what threshold; how to react to failures and anomalies; whether to widen the composition window or the cell-size pool; when to stop; what to report |
| system selection | the **research agent** | translate the goal into figures of merit and constraints; propose candidate chemistries from prior knowledge and databases *before* spending compute; launch campaigns per system; compare, deepen, and recommend |
| objective | the user | "find a better electrode composition for a battery" |

Today the campaign-reasoning layer is mostly hard-coded rules ("verify after 70%
of budget", "endpoints first", "stop on budget or target σ"). Those are exactly
the decisions an agent should own. The `strategy` dropdown — `agent` versus the
`random` / `grid` / `uncertainty` heuristics — is a leftover of treating point
selection as the agent's job; in the target architecture the heuristics are the
agent's *instruments*, and "strategy" collapses to *agent* versus *fixed
pipeline* (kept only for benchmarking).

The guardrails stay in code at every level: hard budgets, pure-element
references measured first, every proposal validated and repaired before it
runs, and every number in a report traceable to a persisted calculation.

## 3. Candidate top-level goals and what each needs

| goal | figures of merit we would have to compute | distance from today |
|---|---|---|
| **better battery electrode** | average voltage (falls *directly* out of formation-energy hulls versus the metal anode — our hull machinery almost verbatim); capacity; volume change on cycling (the E(V) scan already gives this); ion diffusion barriers (new: nudged-elastic-band calculations); electrochemical stability window | **closest** — voltage and volume are already-computed quantities reinterpreted; validation target: measured voltage profiles |
| **better permanent magnet** | saturation magnetisation; Curie temperature; magnetocrystalline anisotropy | spin-polarised DFT (a configuration change we deliberately skipped so far) and T_Curie via Heisenberg Monte Carlo — which is the Ising / canonical-MC machinery of Milestones 2 and 5 with magnetic couplings instead of chemical ones; validation target: measured M_s and T_C |
| **heat-dissipating semiconductor** | lattice thermal conductivity (phonons — a new engine); band gap; electrical resistivity | **furthest** — not a metal on an FCC lattice at all: a different structure space and different calculators |
| **corrosion / oxidation-resistant alloy** | surface energies, oxide formation energies, passivation | new surface/defect structure space; hull machinery reusable for oxides |
| **high-entropy / multi-principal-element alloys** | configurational entropy versus ordering, phase stability at service temperature | extend the binary CE to multinary cluster spaces (icet supports it); the MC and hull layers generalise |

## 4. Validation is the product

Every step up the hierarchy must keep the property the current platform has:
predictions are checked against ground truth, and disagreements are explained
rather than hidden. Concretely:

- **Synthetic first.** Each new capability gets a hidden-oracle version with
  exact ground truth and a benchmark harness (plan §21) before it touches a real
  engine. The synthetic Ising/alloy/phase/property problems caught real defects
  (edge-chasing acquisition, ill-conditioned CE fits, budget overshoot) that
  the real engines would have hidden inside noise.
- **Then real, against measured data.** The first real-data validation is the
  Cu–Au system: predicted stable phases (Cu₃Au, CuAu, CuAu₃), lattice constants,
  formation enthalpies, order/disorder temperatures (663 K / 683 K), and bulk
  moduli are all measured quantities. The expected *discrepancy* — CE + MC
  overestimating T_c because vibrational entropy and the L1₀ tetragonal
  distortion are missing — is a known effect; reproducing it is a stronger
  validation than agreement would be.
- **Reports state limitations.** Non-FCC elements on the FCC lattice,
  non-spin-polarised DFT, unrelaxed cells, unverified candidates: the report
  says so. A research agent that cannot say "I don't know" is worthless.

## 5. How we build in this direction

Roughly in order; each step is usable on its own.

### 5.1 Campaign agent over tools (near term)

1. Expose the acquisition rules as agent tools (they already exist as pure
   functions: `propose_structure`, `propose_phase_point`,
   `propose_property_query`), each returning a proposal *with* its rationale.
2. Replace per-experiment `RUN_*` decisions with campaign-level actions:
   `SET_ACQUISITION(policy)`, `ALLOCATE(stage, fraction)`, `ADVANCE_STAGE`,
   `VERIFY(candidate, T)`, `FINISH(recommendation)` — keeping raw `RUN_*` as an
   override for when the agent has a specific hypothesis.
3. Make the Milestone 9 chain (DFT → CE → MC → ranking) a single multi-stage
   campaign whose stage transitions and budget splits are the agent's calls.
   The first transition to hand over is DFT → CE → T_c(x): running the
   phase-boundary sweep on the *fitted* cluster expansion, which is also the
   missing piece for the Cu–Au validation.
4. Re-benchmark on the metrics that reflect *meta* decisions: total budget to a
   confident recommendation, verification spent on candidates that mattered,
   false confidence avoided — agent-with-tools versus the fixed pipeline.

### 5.2 Broader structure spaces (medium term)

- Other parent lattices (BCC, HCP) and multinary cluster spaces via icet.
- Ionic relaxation and cell-shape relaxation in the DFT engine (removes the
  largest known error for size-mismatched pairs like Cu–Au).
- Spin-polarised DFT as a per-campaign option (prerequisite for anything
  magnetic, and for honest Ni/Fe/Co energetics).
- Vibrational free energy (quasi-harmonic or phonon) so finite-temperature
  predictions stop over-estimating transition temperatures.

### 5.3 New figures of merit (medium term)

- **Battery voltage** from hull formation energies versus a reference anode —
  the cheapest new capability with the clearest experimental validation.
- **Curie temperature** via Heisenberg MC on magnetic exchange couplings fitted
  the way we fit cluster expansions.
- Diffusion barriers (NEB) and elastic tensors (generalising the E(V) bulk
  modulus scan to full strain sets).

### 5.4 Research agent (long term)

- Goal → figures-of-merit translation with explicit constraints (cost,
  toxicity, manufacturability) and computable proxies per budget level.
- Prior-knowledge screening against materials databases (Materials Project,
  OQMD, AFLOW) before any compute is spent.
- Multi-system orchestration: many campaigns in parallel (Temporal already
  gives us durable, restartable jobs), cross-system comparison, and a
  recommendation whose every number has provenance.

## 6. Pragmatic next step

Battery electrodes are the recommended first climb: average voltage and volume
change fall out of the hull work we already trust, so the first new capability
is *candidate-system proposal + multi-system orchestration* rather than a new
physics engine — and it can be validated against measured voltage profiles the
same way Cu–Au validates transition temperatures.
