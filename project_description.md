# Autonomous Alloy Scientist

## Project Overview

Build an autonomous computational materials-science platform that searches binary-alloy design spaces for compositions and atomic structures that satisfy useful engineering objectives.

The system should combine:

- quantum-mechanical calculations
- statistical mechanics
- active learning / experiment selection
- an AI scientific agent
- durable simulation infrastructure
- a scientist-facing web interface
- explicit uncertainty and reproducibility
- quantitative evaluation of whether the agent actually improves scientific search efficiency

This should NOT primarily be a chatbot.

The core product experience should resemble a scientific mission-control system in which the user specifies an engineering objective and watches an AI scientist:

1. form hypotheses,
2. choose simulations,
3. run calculations,
4. inspect results,
5. diagnose failures,
6. update models,
7. quantify uncertainty,
8. choose the next most informative calculations,
9. identify promising materials,
10. explain the evidence supporting its conclusions.

The high-level scientific chain is:

composition + atomic configuration
    ↓
quantum-mechanical energy calculations
    ↓
effective Hamiltonian / cluster expansion
    ↓
statistical-mechanics sampling
    ↓
finite-temperature phase stability
    ↓
property calculations
    ↓
engineering candidate ranking

The eventual product question is NOT:

> "What does the Ni-Al phase diagram look like?"

It is closer to:

> "Find alloy compositions and structures that maximize a target property while remaining thermodynamically stable across my operating-temperature range, using as few expensive first-principles calculations as possible."

---

# 1. Canonical Demo Problem

Use a binary alloy:

    A_(1-x) B_x

where:

    0 <= x <= 1

For the first real-material demo, use a Ni-rich Ni-Al alloy system.

However, constrain V1 to a single parent lattice, initially FCC.

Do NOT attempt to reproduce the complete experimental Ni-Al phase diagram in V1. The real system contains multiple structures, defects, kinetics, magnetic effects, vibrational contributions, etc.

The initial scientific problem is narrower:

> Given an FCC lattice containing Ni and Al, determine which atomic ordering patterns are energetically favorable, identify ordered phases, estimate their finite-temperature stability, and identify promising structures for engineering-property calculations.

A particularly interesting region is around compositions corresponding to ordered Ni-Al structures such as Ni3Al.

This is economically relevant because ordered phases can act as strengthening phases in high-temperature alloys.

The project should eventually answer questions of the form:

> Which candidate structures have favorable mechanical properties AND remain thermodynamically stable over the application's required temperature range?

---

# 2. Scientific Concepts

## 2.1 Atomic configuration

For a fixed lattice containing N sites, define:

    sigma_i ∈ {Ni, Al}

A configuration is:

    sigma = (sigma_1, sigma_2, ..., sigma_N)

At a fixed composition x, there may be an enormous number of possible configurations.

The first problem is therefore:

> Which arrangements of Ni and Al atoms are energetically favorable?

---

## 2.2 DFT calculations

Use Density Functional Theory as the expensive energy oracle.

For a structure sigma:

    E_DFT(sigma)

returns an approximate ground-state electronic energy.

Use:

- ASE for structure representation and calculator abstraction
- Quantum ESPRESSO for first-principles DFT calculations

ASE should be the abstraction boundary.

The rest of our scientific code should depend on an interface such as:

    EnergyCalculator

rather than directly depending on Quantum ESPRESSO.

This allows us to swap between:

- synthetic oracle
- classical potential
- Quantum ESPRESSO
- another DFT package
- ML interatomic potential

without changing the agent.

Conceptually:

    structure
        ↓
    ASE Atoms
        ↓
    Calculator
        ↓
    energy / forces / stress

---

# 3. Formation Energy and Zero-Temperature Stability

Raw total energy is not enough.

Calculate formation energy relative to the pure elements.

For composition x:

    ΔE_form =
        E(A_(1-x)B_x)
        - (1-x) E(A)
        - x E(B)

Plot:

    ΔE_form(x)

for calculated structures.

Construct the lower convex hull.

Structures lying on the lower convex hull are thermodynamically stable against decomposition at approximately 0 K within the approximations of the calculation.

Structures above the hull are metastable or unstable.

The UI should make this extremely visual.

Example:

                 unstable structure
                       •
                      /
          •----------•
         /            \
    A •----------------• B
          composition

The agent should reason explicitly about:

- formation energy
- energy above hull
- competing structures
- composition
- uncertainty

---

# 4. Why Finite Temperature Matters

Finding the lowest-energy structures only answers the approximate T = 0 question.

At finite temperature, equilibrium depends on free energy.

For a simplified model:

    F = E - T S

An ordered structure may minimize energy but have low configurational entropy.

A disordered solid solution may have higher energy but much higher entropy.

Therefore increasing temperature can produce:

    ordered phase
        ↓
    order/disorder transition
        ↓
    disordered solid solution

The economically important question is not just:

> Is this structure stable?

but:

> Is this structure stable under the temperatures at which the material will be manufactured and used?

For example:

Candidate A:
    excellent mechanical properties
    stable only below 500 K

Candidate B:
    slightly worse mechanical properties
    stable to 1100 K

For a high-temperature turbine application, Candidate B may be vastly more useful.

---

# 5. Cluster Expansion

DFT is too expensive to evaluate every atomic configuration.

Fit a cluster expansion that approximates configurational energy.

Conceptually:

    H(sigma)
      = J_0
      + Σ_i J_i sigma_i
      + Σ_ij J_ij sigma_i sigma_j
      + Σ_ijk J_ijk sigma_i sigma_j sigma_k
      + ...

The fitted coefficients J are effective cluster interactions.

Training data:

    configuration_1 -> DFT energy_1
    configuration_2 -> DFT energy_2
    ...
    configuration_n -> DFT energy_n

Use:

    icet

for:

- cluster-space construction
- structure containers
- fitting cluster expansions
- configuration enumeration
- convex-hull workflows
- Monte Carlo integration

The fitted cluster expansion becomes a cheap surrogate:

    structure -> predicted energy

that can be evaluated millions of times much more cheaply than DFT.

---

# 6. Statistical Mechanics / Monte Carlo

Use Monte Carlo to sample configurations according to the effective Hamiltonian.

Approximately:

    P(sigma)
      ∝ exp(-H(sigma) / (k_B T))

Run simulations across:

- composition x
- temperature T

Measure quantities such as:

- mean energy
- heat capacity
- order parameters
- susceptibilities
- composition
- correlation functions

Transitions can be detected from:

- order parameter changes
- heat-capacity peaks
- susceptibility peaks
- free-energy behavior

The output is a finite-temperature composition-temperature diagram:

    phase = f(x, T)

rather than a P-V-T diagram.

Pressure should initially be treated as fixed.

---

# 7. Property Prediction

Phase stability is an intermediate result.

The economically valuable result is finding phases that have useful physical properties and remain stable under operating conditions.

Create a pluggable property-calculation system.

Example interface:

    PropertyCalculator

Possible property calculations:

## V1

- equilibrium lattice constant
- formation energy
- bulk modulus

## V2

- elastic tensor
- shear modulus
- Young's modulus
- Poisson ratio
- density
- electronic density of states

## Later

- thermal expansion
- phonon stability
- thermal conductivity
- diffusion barriers
- oxidation-related descriptors
- magnetic properties
- creep-related proxies

Property calculations should themselves become simulation jobs with:

- inputs
- outputs
- provenance
- uncertainty
- runtime
- cost

---

# 8. Engineering Design Objective

The user should create a "Discovery Campaign."

Example:

    Application:
        high-temperature structural alloy

    Elements:
        Ni, Al

    Composition range:
        x_Al = 0.10 to 0.35

    Operating temperature:
        300 K to 1000 K

    Objectives:
        maximize bulk modulus

    Constraints:
        stable over operating-temperature range
        energy above hull < threshold
        density < threshold

    DFT budget:
        40 calculations

The platform then attempts to solve something conceptually like:

    maximize:
        material_property(candidate)

    subject to:
        thermodynamic_stability(candidate, T)
        for T_min <= T <= T_max

        total_DFT_calculations <= budget

The agent's job is to intelligently allocate the simulation budget.

---

# 9. Agent Role

The agent is an autonomous computational materials scientist.

It should NOT fabricate scientific results.

All numerical scientific claims must originate from deterministic scientific tools.

The LLM is responsible for:

- hypothesis generation
- experiment selection
- interpreting results
- prioritizing candidates
- diagnosing simulation failures
- deciding what to investigate next
- deciding whether uncertainty is sufficiently low
- communicating scientific reasoning

The LLM is NOT responsible for calculating:

- DFT energies
- Monte Carlo averages
- convex hulls
- elastic constants
- regression coefficients
- statistical uncertainties

Those must come from tools.

---

# 10. Agent Framework

Use Python.

Recommended initial stack:

- OpenAI Agents SDK
- Pydantic
- FastAPI
- asyncio

Use OpenAI Agents SDK as the equivalent of the Vercel AI SDK agent harness.

Reasons:

- relatively small abstraction surface
- Python-first
- typed function tools
- Pydantic schema generation
- built-in agent loop
- structured outputs
- tracing
- sessions
- easy tool composition

Avoid LangGraph initially.

We don't need to encode the scientific method as a giant hard-coded DAG.

The interesting behavior should come from the scientific agent choosing actions.

However, DO NOT use the agent framework as the job scheduler.

Separate:

    AGENT REASONING

from:

    SCIENTIFIC JOB EXECUTION

The LLM chooses what needs to happen.

The execution system guarantees that the calculation actually happens.

---

# 11. Long-Running Job Infrastructure

Eventually use Temporal for durable scientific workflows.

Quantum ESPRESSO and Monte Carlo jobs may:

- run for minutes/hours
- fail
- time out
- be retried
- be interrupted
- depend on previous jobs
- need resumability

Architecture:

    Agent
      |
      | run_dft(...)
      v
    Scientific Job API
      |
      v
    Temporal Workflow
      |
      v
    Worker
      |
      v
    Quantum ESPRESSO

The agent should never directly execute arbitrary shell commands.

Tools submit strongly typed jobs.

For the earliest prototype, Temporal can be omitted and jobs can run locally through a simple async job executor.

Introduce Temporal once the synthetic scientific loop works.

---

# 12. Agent Tools

Expose typed tools.

Examples:

    enumerate_structures(...)
    inspect_structure(...)
    calculate_formation_energy(...)
    get_convex_hull(...)
    fit_cluster_expansion(...)
    validate_cluster_expansion(...)
    estimate_model_uncertainty(...)
    suggest_high_uncertainty_structures(...)
    run_dft(...)
    inspect_dft_run(...)
    retry_dft(...)
    run_monte_carlo(...)
    inspect_monte_carlo_run(...)
    calculate_phase_boundary(...)
    calculate_material_property(...)
    compare_candidates(...)
    inspect_budget(...)
    finish_campaign(...)

Do not make:

    run_shell_command(command: string)

available to the scientific agent.

Every scientific action should have explicit schemas.

---

# 13. Active Learning

This is one of the most important parts of the project.

The agent has a limited DFT budget.

Example:

    DFT budget = 30

There may be thousands of possible atomic configurations.

The system must determine:

> Which structure should we spend the next expensive DFT calculation on?

Baseline strategies:

### Random

Randomly select uncomputed structures.

### Grid / composition coverage

Select structures to evenly cover composition space.

### Uncertainty sampling

Select structures with high surrogate-model uncertainty.

### Expected information gain

Prefer calculations expected to most reduce uncertainty about the scientific objective.

### Agent

Give the AI scientist:

- current training set
- cluster-expansion validation metrics
- hull
- candidate structures
- uncertainty estimates
- phase diagram uncertainty
- remaining budget

Ask it to choose the next calculation(s).

The agent should have to justify choices in a structured form.

Example:

    hypothesis:
        "The low-energy structure near x_Al=0.25 may represent
         an ordered phase that changes the finite-temperature
         stability region."

    uncertainty:
        "Cluster-expansion ensemble disagreement is high for
         several uncomputed structures near this composition."

    action:
        calculate structures 182, 207, 311

    expected_information:
        "These structures discriminate between competing
         predictions around the suspected ordered phase."

---

# 14. Uncertainty

Uncertainty must be a first-class concept.

At minimum use:

- train / validation error
- cross-validation error
- ensemble disagreement

One simple implementation:

Fit multiple cluster expansions against bootstrap-resampled training sets.

For candidate structure sigma:

    predictions =
        [E_1(sigma), ..., E_n(sigma)]

Compute:

    μ(sigma)
    σ(sigma)

Use prediction variance as an acquisition signal.

The UI should visually distinguish:

- measured / DFT-calculated values
- surrogate predictions
- uncertain predictions

Never present model predictions as equivalent to completed DFT calculations.

---

# 15. Simulation Failure Recovery

Failure handling is part of the demo.

DFT calculations may fail due to:

- SCF non-convergence
- invalid structure
- inappropriate parameters
- geometry optimization failure
- wall-clock timeout
- worker failure
- malformed pseudopotential configuration

Represent failure explicitly.

Example:

    status: FAILED

    category:
        SCF_NOT_CONVERGED

    metadata:
        iterations: 100
        final_residual: ...
        convergence_threshold: ...

The agent receives the failure report and decides whether to:

- retry
- change settings
- abandon the structure
- request human review

Every retry must preserve:

    original_run_id
    retry_run_id
    changed_parameters
    reason_for_change

Example agent event:

    Run DFT-184 failed SCF convergence.

    Diagnosis:
        convergence residual plateaued.

    Proposed action:
        adjust mixing / convergence settings and retry.

    Retry:
        DFT-191

This should be visible in the frontend.

---

# 16. Reproducibility and Provenance

Every scientific output must be reproducible.

Store:

- code version / git commit
- simulation engine
- simulation engine version
- pseudopotentials
- input structure
- calculation parameters
- random seeds
- model version
- parent calculations
- timestamps
- machine / worker metadata where useful
- stdout
- stderr
- result artifacts

No scientific result should exist without provenance.

---

# 17. Product UX

Do NOT build a ChatGPT clone.

Primary interface:

    scientific mission control

Chat can exist as one interaction mechanism but should not dominate the product.

Main pages:

## /campaigns

List discovery campaigns.

Show:

- objective
- alloy
- status
- DFT budget consumed
- current best candidate
- uncertainty
- last agent action

---

## /campaigns/[id]

Primary campaign dashboard.

Suggested layout:

### Top

Engineering objective.

Example:

    Find a Ni-Al structure with high stiffness
    that remains stable from 300-1000 K.

Show:

    21 / 40 DFT calculations consumed

    4 candidate phases

    2 high-priority uncertainties

    campaign status: investigating

---

### Main visualization

Composition-temperature phase diagram.

Axes:

    x-axis = Al fraction
    y-axis = temperature

Show:

- inferred phases
- phase boundaries
- uncertainty bands
- regions with insufficient data

Allow clicking a region.

---

### Candidate panel

Rank promising candidates.

Example:

    Ni3Al candidate

    composition: 25% Al
    hull distance: 0 meV/atom
    predicted bulk modulus: ...
    stability window: ...
    confidence: high

---

### Agent activity

Chronological scientific reasoning.

Example:

    14:32
    Agent detected high uncertainty around x=0.25.

    14:33
    Selected structures #184, #291 and #417.

    14:33
    Reason:
    These configurations maximally disagree across the
    cluster-expansion ensemble.

    14:36
    DFT #184 running.

    14:42
    DFT #291 failed SCF convergence.

    14:43
    Agent scheduled retry with modified convergence settings.

---

# 18. Experiment Graph

Create a DAG visualization.

Example:

    User Objective
          |
          v
    Initial Structures
          |
          v
       DFT Runs
          |
          v
    Cluster Expansion v1
          |
          v
      Monte Carlo
          |
          v
    Suspected Transition
          |
          v
     Agent Hypothesis
          |
          v
    Additional DFT Runs
          |
          v
    Cluster Expansion v2
          |
          v
     Phase Diagram
          |
          v
    Property Calculation

Every node should be clickable.

This is one of the key product features.

Scientists should be able to answer:

> Why does the system believe this?

by traversing the evidence graph.

---

# 19. Structure Viewer

Create a 3D structure viewer.

Show:

- element identity
- lattice
- unit cell
- composition
- structure ID
- calculated energy
- predicted energy
- energy above hull
- model uncertainty

Eventually allow side-by-side comparison:

    ordered structure
        vs
    disordered structure

This visually explains why "same composition" does not mean "same material."

---

# 20. Run Inspector

Every DFT or Monte Carlo run gets a page.

Example:

    /runs/dft-184

Show:

- status
- parent campaign
- input structure
- engine
- parameters
- command metadata
- runtime
- logs
- convergence plot
- energy
- forces
- output artifacts
- retries
- provenance

If failed:

    failure category
    diagnostics
    agent interpretation
    retry history

---

# 21. Benchmark / Evaluation Mode

This is critical.

We need to determine whether the AI agent actually improves scientific search.

Create synthetic environments where ground truth is known.

Start with an Ising model or predefined lattice Hamiltonian.

The agent does NOT see the Hamiltonian directly.

It can query configurations through an expensive simulated experiment:

    evaluate_structure(sigma)

Assign each query a cost.

Example budget:

    30 evaluations

Ground truth can be calculated separately with a much larger compute budget.

Compare strategies:

| Strategy              | Queries | Ground-state error | Phase-boundary error |
|-----------------------|---------|--------------------|----------------------|
| Random                | 30      | ...                | ...                  |
| Uniform coverage      | 30      | ...                | ...                  |
| Uncertainty sampling  | 30      | ...                | ...                  |
| AI agent              | 30      | ...                | ...                  |

Additional metrics:

- number of simulations required
- wall-clock cost
- false stable-phase discoveries
- missed stable phases
- phase-boundary error
- uncertainty calibration
- recovery rate from injected failures
- invalid experiment rate
- number of unnecessary duplicate calculations
- property-optimization regret

This should have a dedicated frontend.

---

# 22. Synthetic V1

DO THIS BEFORE REAL DFT.

Build the full product loop using a cheap known Hamiltonian.

Suggested progression:

## V0

2D Ising model.

Goal:

    autonomously locate the critical-temperature region.

The agent chooses temperatures at which to run Monte Carlo.

Compare against random/grid sampling.

This validates:

- agent loop
- experiment selection
- Monte Carlo infrastructure
- uncertainty
- dashboard
- evaluation harness

---

## V1

Synthetic binary-alloy lattice Hamiltonian.

Provide hidden pair interactions.

Agent must discover:

- low-energy configurations
- stable compositions
- ordering behavior
- approximate phase boundaries

This adds composition.

---

## V2

Use `icet` with a known cluster expansion.

Treat the CE as ground-truth oracle.

Agent has limited access to structure energies.

Goal:

    reconstruct phase behavior with minimal queries.

---

## V3

Replace oracle queries with real DFT calculations.

Use:

    ASE
      +
    Quantum ESPRESSO

Now:

    DFT -> training data -> cluster expansion -> Monte Carlo

---

## V4

Add engineering-property optimization.

Example:

    maximize bulk modulus
    subject to finite-temperature stability.

---

# 23. Technology Stack

## Monorepo

Use Turborepo.

Package manager:

    pnpm

Python environment:

    uv

Suggested repository:

    /
    ├── apps/
    │   ├── web/
    │   │   ├── app/
    │   │   ├── components/
    │   │   ├── features/
    │   │   └── package.json
    │   │
    │   └── api/
    │       ├── src/
    │       │   └── alloylab/
    │       │       ├── api/
    │       │       ├── agent/
    │       │       ├── campaigns/
    │       │       ├── jobs/
    │       │       └── db/
    │       ├── pyproject.toml
    │       └── package.json
    │
    ├── packages/
    │   ├── ui/
    │   ├── api-client/
    │   ├── science/
    │   │   ├── pyproject.toml
    │   │   └── src/
    │   │       └── alloyscience/
    │   │           ├── structures/
    │   │           ├── calculators/
    │   │           ├── thermodynamics/
    │   │           ├── cluster_expansion/
    │   │           ├── monte_carlo/
    │   │           ├── properties/
    │   │           └── uncertainty/
    │   │
    │   ├── eslint-config/
    │   └── typescript-config/
    │
    ├── infra/
    │   ├── docker/
    │   └── temporal/
    │
    ├── turbo.json
    ├── pnpm-workspace.yaml
    └── pyproject.toml

The Python app can contain a small `package.json` whose scripts invoke:

    uv run ...

so Turbo can orchestrate it alongside the TypeScript applications.

---

# 24. Frontend

Use:

- Next.js
- React
- TypeScript
- Tailwind CSS

Do NOT use Mantine.

Part of the point of the project is trying Tailwind.

Potential supporting libraries:

- shadcn/ui for low-level accessible primitives if useful
- Plotly for scientific charts
- React Flow for experiment DAG
- 3Dmol.js / another atomic visualization library for structures
- TanStack Query for API state

Use a restrained scientific/technical design.

Avoid generic SaaS dashboard aesthetics.

Prioritize:

- dense information
- inspectability
- plotting
- provenance
- scientific state

---

# 25. Backend

Use:

- Python
- FastAPI
- Pydantic
- OpenAI Agents SDK
- SQLAlchemy or SQLModel
- PostgreSQL
- uv

Scientific packages:

- NumPy
- SciPy
- ASE
- icet
- pymatgen where useful
- Quantum ESPRESSO external executable

Optional later:

- scikit-learn
- Temporal Python SDK

FastAPI should publish OpenAPI.

Generate the TypeScript client automatically from OpenAPI rather than manually maintaining duplicate API types.

---

# 26. Database Model

Core entities:

## Campaign

    id
    name
    elements
    composition_min
    composition_max
    temperature_min
    temperature_max
    simulation_budget
    simulations_used
    status
    objective
    created_at

---

## Structure

    id
    chemical_formula
    composition
    lattice
    positions
    atomic_numbers
    parent_structure_id
    metadata

Store an ASE-compatible serialized representation.

---

## Calculation

    id
    campaign_id
    structure_id
    calculation_type
    engine
    status
    input_parameters
    output
    energy
    uncertainty
    started_at
    completed_at
    parent_calculation_id
    retry_of
    failure_category
    stdout_artifact
    stderr_artifact

Types include:

    DFT
    MONTE_CARLO
    PROPERTY
    STRUCTURE_RELAXATION

---

## SurrogateModel

    id
    campaign_id
    type
    version
    training_calculation_ids
    parameters
    validation_metrics
    artifact
    created_at

Example:

    cluster_expansion

---

## Phase

    id
    campaign_id
    composition_range
    temperature_range
    representative_structure_id
    confidence
    evidence

---

## Candidate

    id
    campaign_id
    structure_id
    rank
    objective_score
    stability_score
    property_values
    uncertainty
    explanation

---

## AgentRun

    id
    campaign_id
    model
    started_at
    completed_at
    token_usage
    status

---

## AgentEvent

    id
    agent_run_id
    campaign_id
    event_type
    hypothesis
    reasoning_summary
    action
    tool_name
    tool_input
    tool_output_reference
    created_at

Do NOT store or display hidden chain-of-thought.

Store concise scientific rationale explicitly requested from the model.

---

# 27. API

Suggested endpoints:

    POST /campaigns
    GET  /campaigns
    GET  /campaigns/{id}
    POST /campaigns/{id}/start
    POST /campaigns/{id}/pause

    GET /campaigns/{id}/structures
    GET /campaigns/{id}/calculations
    GET /campaigns/{id}/models
    GET /campaigns/{id}/phase-diagram
    GET /campaigns/{id}/candidates
    GET /campaigns/{id}/agent-events

    GET /structures/{id}
    GET /calculations/{id}
    GET /models/{id}

Use Server-Sent Events initially:

    GET /campaigns/{id}/events

Stream:

- agent actions
- job starts
- job progress
- job completion
- failures
- model updates
- candidate changes

WebSockets are unnecessary unless bidirectional realtime interaction becomes important.

---

# 28. Agent Loop

Conceptual loop:

    while not stopping_condition:

        state = build_scientific_state()

        decision = await scientist_agent.run(state)

        validate(decision)

        execute(decision)

        persist_everything()

        if jobs_running:
            wait_for_results()

        update_models()

        evaluate_progress()

The state given to the agent should include summaries, NOT enormous raw arrays.

Example:

    objective
    remaining_budget
    current_candidates
    current_hull
    CE validation error
    uncertain composition regions
    recent failures
    completed experiments
    running experiments
    available candidate structures

The agent can request deeper information using tools.

---

# 29. Structured Agent Decision

Force important decisions into a schema.

Example:

    class ScientificDecision(BaseModel):
        hypothesis: str
        evidence: list[str]
        uncertainty: str
        action_type: ActionType
        action_parameters: dict
        expected_information_gain: str
        stopping_rationale: str | None

This gives the frontend something useful to display without exposing raw model reasoning.

---

# 30. Scientific State Machine

Campaign states:

    CREATED
      ↓
    INITIALIZING
      ↓
    COLLECTING_DATA
      ↓
    FITTING_MODEL
      ↓
    SAMPLING
      ↓
    ANALYZING
      ↓
    PROPERTY_EVALUATION
      ↓
    COMPLETED

But the transitions should not be rigid.

The agent may loop:

    FITTING_MODEL
        ↓
    identifies uncertainty
        ↓
    COLLECTING_DATA
        ↓
    FITTING_MODEL

or:

    SAMPLING
        ↓
    phase boundary unclear
        ↓
    COLLECTING_DATA

This iterative loop is the actual scientific method.

---

# 31. Stopping Conditions

Campaigns should not run forever.

Possible stopping criteria:

- DFT budget exhausted
- uncertainty below threshold
- no candidate improvement over N iterations
- requested confidence reached
- engineering objective satisfied
- user manually stops
- agent concludes additional experiments have low expected value

Agent must explicitly state why it is stopping.

---

# 32. Human-in-the-Loop

Allow the scientist to intervene.

Examples:

    "Investigate the x=0.25 region more deeply."

    "Spend at most five more DFT calculations."

    "Reject this candidate because Al concentration is too high."

    "Use a stricter stability threshold."

    "Why do you believe candidate #14 is stable?"

The user should also be able to approve expensive calculation batches.

Example:

    Agent proposes:
        Run 8 DFT calculations
        estimated compute cost: X

    [Approve]
    [Modify]
    [Reject]

---

# 33. Scientific Explainability

For every major conclusion, support:

    Why?

Example:

    Candidate Ni3Al-17
        ↓
    predicted useful property
        ↓
    property calculation P-81

and:

    finite-temperature stability
        ↓
    Monte Carlo campaign MC-14
        ↓
    cluster expansion CE-v7
        ↓
    37 DFT training calculations

The user should be able to traverse this chain.

The project should make unsupported model claims difficult.

---

# 34. Testing

## Unit tests

Scientific:

- composition calculations
- formation energies
- convex hull
- cluster-expansion fitting
- uncertainty
- Monte Carlo observables
- property calculations

Backend:

- schemas
- API
- job lifecycle
- agent tool validation
- state transitions

Frontend:

- critical components
- visualization transformations

---

## Integration tests

Example:

    create synthetic campaign
        ↓
    enumerate structures
        ↓
    evaluate synthetic oracle
        ↓
    fit surrogate
        ↓
    run MC
        ↓
    agent requests new experiments
        ↓
    results update
        ↓
    campaign completes

This test should run without OpenAI or Quantum ESPRESSO using deterministic mocked agent decisions.

---

# 35. Evaluation

Agent performance must be measurable.

For each benchmark run save:

    strategy
    random_seed
    oracle
    budget
    structures_sampled
    final model
    true stable structures
    predicted stable structures
    phase-boundary error
    objective regret
    total simulation cost

Run many seeds.

Produce aggregate plots.

This benchmark is arguably as important as the agent itself.

---

# 36. Key Product Principle

Avoid:

> "Look, GPT can call Quantum ESPRESSO."

That is not interesting enough.

Demonstrate:

> "An autonomous agent can make better decisions about which
> expensive scientific calculations to perform, recover from
> failed calculations, update its beliefs from the results,
> quantify uncertainty, and converge toward useful material
> candidates with less compute."

That is the central thesis.

---

# 37. Development Milestones

## Milestone 1 — Foundation

Build:

- Turborepo
- Next.js app
- Tailwind
- FastAPI
- PostgreSQL
- generated TypeScript API client
- campaign CRUD
- agent-event stream

No real physics yet.

---

## Milestone 2 — Ising Scientist

Implement 2D Ising simulator.

Agent objective:

> Determine the critical region using a finite Monte Carlo budget.

Build:

- simulator
- experiment tool
- agent loop
- plots
- uncertainty
- benchmark against grid/random

This proves the product architecture.

---

## Milestone 3 — Binary Lattice Model

Implement hidden binary-alloy Hamiltonian.

Support:

- composition
- configurations
- formation energies
- ground-state search
- convex hull

Agent must discover stable configurations.

---

## Milestone 4 — icet

Integrate icet.

Implement:

- structure enumeration
- cluster space
- structure container
- CE fitting
- cross-validation
- CE prediction
- Monte Carlo sampling

Agent chooses which oracle energies to acquire.

---

## Milestone 5 — Phase Diagram

Build:

- T-x plot
- order parameters
- phase-transition detection
- uncertainty visualization

Agent autonomously investigates uncertain boundaries.

---

## Milestone 6 — Real DFT

Install Quantum ESPRESSO.

Build ASE-backed:

    QuantumEspressoCalculator

Add:

- DFT job records
- artifacts
- logs
- SCF convergence detection
- retries

Replace selected synthetic energy queries with DFT.

---

## Milestone 7 — Durable Execution

Add Temporal.

Make DFT and long Monte Carlo runs durable.

Support:

- worker restart
- retry policy
- timeout
- cancellation
- provenance
- job progress

---

## Milestone 8 — Property Search

Implement at least one actual engineering-property calculation.

Suggested first property:

    bulk modulus

The agent now searches for:

> structures with high predicted bulk modulus that also satisfy
> thermodynamic-stability constraints.

---

## Milestone 9 — Full Autonomous Campaign

User provides:

    elements
    composition range
    operating temperature
    property objective
    compute budget

Agent independently performs:

    structure selection
        ↓
    DFT
        ↓
    cluster expansion
        ↓
    Monte Carlo
        ↓
    candidate identification
        ↓
    property calculation
        ↓
    additional simulations
        ↓
    final recommendation

---

# 38. Definition of a Successful Demo

The final demo should be something like:

1. Create a Ni-Al discovery campaign.

2. Tell the system:

       Find promising Ni-rich Ni-Al ordered structures
       for a high-temperature structural application.

       Prefer high stiffness.

       Require stability over the specified
       operating-temperature range.

       You have a budget of 30 DFT calculations.

3. The agent begins with a small diverse training set.

4. DFT results arrive.

5. It fits a cluster expansion.

6. The UI shows the convex hull evolving.

7. Monte Carlo reveals a suspected ordered region.

8. Model uncertainty is high around x_Al ≈ 0.25.

9. The agent explicitly decides that three additional
   structures around this region have high information value.

10. One DFT run fails.

11. The agent diagnoses it and retries appropriately.

12. The new data materially changes the cluster expansion.

13. The inferred phase boundary tightens.

14. A candidate ordered structure survives the required
    temperature range.

15. The system calculates its bulk modulus.

16. The candidate gets promoted to the top of the ranking.

17. The UI can trace the recommendation all the way back
    through Monte Carlo, cluster expansion, and raw DFT runs.

18. Benchmark mode shows that the agent reached a comparable
    answer with fewer expensive oracle queries than random
    or uniform sampling.

That is the story the project should tell.

---

# 39. What NOT to Build Initially

Do not initially attempt:

- arbitrary elements
- arbitrary crystal structures
- complete phase diagrams
- liquid phases
- melting
- pressure-dependent phase diagrams
- full phonon free energies
- diffusion kinetics
- precipitation kinetics
- molecular dynamics
- ternary alloys
- autonomous literature review
- autonomous experimental laboratory equipment
- dozens of material properties
- multi-agent architecture for its own sake

We want one scientifically legitimate closed loop done extremely well.

---

# 40. Architectural Philosophy

Three layers should remain clearly separated:

## Intelligence

    OpenAI Agents SDK

Responsible for:

    scientific decisions

## Scientific truth

    NumPy / SciPy / ASE / icet /
    Quantum ESPRESSO / Monte Carlo

Responsible for:

    numerical scientific results

## Execution infrastructure

    FastAPI / Postgres / Temporal / workers

Responsible for:

    making experiments durable,
    inspectable and reproducible

Never let the LLM blur those boundaries.

---

# 41. Project North Star

The finished project should make the following statement credible:

> We built a small autonomous materials-science laboratory.
>
> The AI scientist is given an engineering objective and a
> finite computational budget. It selects which atomic
> structures are worth expensive first-principles evaluation,
> learns an effective physical model from those calculations,
> uses statistical mechanics to determine finite-temperature
> phase behavior, calculates properties of promising phases,
> recovers from failed simulations, and iteratively chooses
> new experiments until it can recommend a material candidate
> with quantified evidence and uncertainty.
>
> Every scientific conclusion is traceable back to the
> simulations that produced it, and the system can be
> quantitatively benchmarked against non-agent experiment-
> selection strategies.

That is the product.