# AlloyLab — Autonomous Alloy Scientist

An autonomous computational materials-science platform (see `project_description.md`
for the full plan). This repository implements **all nine milestones of the plan**: the
complete product loop — agent decisions, typed simulation jobs, surrogate models
with uncertainty, failure recovery, live mission-control UI, and strategy
benchmarks — built on synthetic problems first (as the plan prescribes) and now
running against **real first-principles calculations**:

- **Ising V0** — autonomously locate the critical-temperature region of the 2D
  Ising model with a finite Monte Carlo budget.
- **Alloy V1 (Milestone 3)** — a binary alloy A(1-x)B(x) on a 2D lattice
  governed by a *hidden* pair Hamiltonian. The agent enumerates candidate
  orderings, spends a finite oracle budget on simulated-DFT energy queries
  (with injected SCF failures), fits a mini cluster expansion over correlation
  features, and discovers the formation-energy convex hull and stable ordered
  structures (e.g. the checkerboard A2B2 ground state).
- **FCC Ni-Al V2 (Milestone 4, icet)** — real crystallography via ASE + icet:
  symmetry-enumerated FCC orderings, an icet cluster space whose cluster
  vectors are the CE design rows, LOOCV-validated CE fitting with bootstrap
  uncertainty, and a hidden icet-style cluster expansion as the ground-truth
  oracle (plan section 22 V2). The agent discovers L1_2 Ni3Al / L1_0 NiAl-type
  ground states; `alloyscience.fcc.run_canonical_mc` samples the fitted CE with
  mchammer (canonical MC + Warren-Cowley short-range order).
- **Phase diagram (Milestone 5, mchammer)** — the agent maps the
  order/disorder boundary Tc(x) of a hidden CE with a finite canonical-MC
  budget: heat-capacity peaks locate the transition per composition slice,
  bootstrap ensembles quantify boundary uncertainty (with edge-pinned
  estimates flagged as bounds, not locations), and acquisition targets the
  most uncertain boundary via posterior sampling of the peak location (raw
  max-std chases range edges — the benchmark caught exactly that pathology).
  The dashboard draws the T-x diagram with uncertainty bars, the ordered
  region, per-run SRO coloring, and a per-slice C(T) inspector.
- **Real DFT (Milestone 6, ASE + Quantum ESPRESSO)** — the same hull campaign
  with a real energy engine behind the plan's `EnergyCalculator` boundary
  (`alloyscience.calculators`): `emt` (ASE's classical potential with volume
  optimisation and curvature-derived bulk moduli — Milestone 8's seed) or
  `espresso` (pw.x single-point SCF at the Vegard-scaled lattice). Espresso
  runs execute in per-calculation artifact directories; the `.pwo` log is
  stored on the job record and served at `/calculations/{id}/log`; SCF
  non-convergence is detected from the log, categorised, and retried by the
  agent with doubled `electron_maxstep` and halved `mixing_beta` — a failure
  mode that occurs for real in elongated metallic cells. Physics settings are
  demo-grade (non-spin-polarised, modest k-mesh): ordered Ni-Al compounds come
  out stable, but numbers are not publication-quality.
- **Durable execution (Milestone 7, Temporal)** — with `ALLOYLAB_EXECUTOR=temporal`
  every calculation runs as a `RunCalculationWorkflow` on a Temporal task
  queue, executed by separate worker processes (`pnpm --filter @alloylab/api
  worker`). Kill a worker mid-campaign and the campaign stalls durably, then
  resumes and completes when a worker returns; in-flight activities are
  detected via heartbeats and retried. Scientific failures (SCF
  non-convergence) remain DATA for the agent — only infrastructure failures
  (crash/timeout) hit Temporal's retry policy, and exhausted retries surface
  as `INFRASTRUCTURE_FAILURE` job records. Live SSE events still stream from
  the API process; the durable unit (`execute_and_persist`) is idempotent and
  identical on the local and Temporal paths.
- **Property search (Milestone 8, plan section 22 V3)** — "find the stiffest
  FCC Ni-Al ordering that is thermodynamically stable AND stays ordered below
  a threshold temperature." Each query returns energy and bulk modulus (hidden
  synthetic oracle with exact ground truth, or the real EMT engine); two
  bootstrap surrogates over the cluster vectors (energy -> hull, bulk modulus)
  feed a ranked candidate table (plan section 14: stable / property / uncertainty);
  the agent then spends the tail of its budget on canonical-MC verification at
  the threshold temperature ON ITS OWN FITTED CE (Milestone 5 machinery as a
  tool) and disqualifies candidates that disorder. A `FINAL_RECOMMENDATION`
  event closes the campaign; benchmark mode scores strategies by regret in GPa
  against the truly best stable intermetallic.
- **Full autonomous campaign (Milestone 9)** — the whole chain on the real
  engine: choose structures → run DFT (Quantum ESPRESSO with an E(V) scan for
  bulk moduli, `property_engine=espresso`) → fit CE → verify with MC → rank →
  **explain**. Every completed campaign persists a structured scientific
  report (`GET /campaigns/{id}/report`, `/campaigns/[id]/report` in the UI):
  recommendation with confidence, key results, model quality, budget and
  engine time, failure/retry summary, the full reasoning trail, and an
  explicit limitations section — built deterministically from the persisted
  record so every number has provenance. With a provider key set, the
  `agent` strategy (Pydantic AI) drives each decision and an LLM pass writes
  the prose from the structured facts (it may paraphrase, never invent numbers).

Benchmark mode scores strategies against the exact hidden Hamiltonian: hull
RMSE and missed/false stable phases for the hull problems, mean |Tc error|
(the plan's phase-boundary error) for the phase problem. All problems run
through one problem-agnostic campaign loop (`alloylab/problems/` adapters), so
V3 (real DFT) slots in without touching the loop, executor, or failure policy.

## Architecture (three layers, kept separate)

| Layer | Code | Responsibility |
|---|---|---|
| Intelligence | `apps/api/src/alloylab/agent/` (Pydantic AI + heuristics) | scientific decisions |
| Scientific truth | `packages/science/src/alloyscience/` (NumPy/SciPy) | numerical results |
| Execution infra | `apps/api/src/alloylab/{jobs,db,api}/` (FastAPI, SQLAlchemy, SSE) | durable, inspectable experiments |

The LLM never computes numbers; every scientific quantity comes from
deterministic tools, every calculation is a typed job row with provenance,
and every agent decision is persisted as a structured `AgentEvent`.

## Layout

```
apps/
  web/        Next.js + Tailwind mission-control UI  (/campaigns, /campaigns/[id], /benchmarks)
  api/        FastAPI backend: campaigns, jobs, agent loop, SSE, benchmarks
packages/
  science/    alloyscience: Ising MC, bootstrap surrogate, convex hull, strategies, benchmark harness
  api-client/ TypeScript client generated from the FastAPI OpenAPI schema
  typescript-config/
infra/
  docker/     optional PostgreSQL via docker compose
```

## Prerequisites

- Node ≥ 20 with `pnpm`
- `uv` (Python is managed automatically; Python 3.12)

## Setup & run

```bash
pnpm install
uv sync --all-packages --all-extras
pnpm --filter @alloylab/api-client generate   # regenerate TS client from OpenAPI (committed)

# terminal 1 — API on :8000
pnpm --filter @alloylab/api dev

# terminal 2 — web on :3000
pnpm --filter @alloylab/web dev
```

Open http://localhost:3000/campaigns, create a campaign, press **Start**, and
watch the agent select temperatures, recover from injected failures, and tighten
the Tc estimate. The **Benchmarks** page compares strategies against a
high-budget ground-truth scan.

### The LLM agent strategy

Heuristic strategies (`random`, `grid`, `uncertainty`) run fully offline. The
`agent` strategy runs on **Pydantic AI** with structured output (`output_type`)
and deterministic inspection tools. The model is a provider-prefixed Pydantic AI
model string set via `ALLOYLAB_AGENT_MODEL` (default `openai:gpt-5`; e.g.
`anthropic:claude-sonnet-4-5`, `google-gla:gemini-2.5-pro`), with the provider's
API key in the API's environment (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, …).
`ALLOYLAB_AGENT_MODEL=test` runs the full agent path on Pydantic AI's built-in
`TestModel` — no key needed — which is how the harness is unit-tested.

### Real DFT (Quantum ESPRESSO)

The `espresso` engine needs a `pw.x` binary and the PAW pseudopotentials in
`infra/pseudopotentials/` (Ni.pbe-spn-kjpaw and Al.pbe-n-kjpaw, PSlibrary 1.0.0).
Point the API at your binary:

```bash
export ALLOYLAB_PW_COMMAND=$HOME/.local/qe/bin/pw.x   # built from source (cmake, serial+OpenMP)
export ALLOYLAB_PSEUDO_DIR=$PWD/infra/pseudopotentials
```

The env-gated science test `test_espresso_real_scf_on_pure_ni` runs a real SCF
when `ALLOYLAB_PW_COMMAND` is set. Espresso campaigns take minutes per
structure — Milestone 7 (Temporal) is where these long jobs become durable.

### Durable execution (Temporal)

```bash
brew install temporal
temporal server start-dev                      # UI at http://localhost:8233
export ALLOYLAB_EXECUTOR=temporal
pnpm --filter @alloylab/api worker             # one or more workers
pnpm --filter @alloylab/api dev                # the API
```

(`infra/temporal/docker-compose.yml` is the container alternative.) The
env-gated test `ALLOYLAB_TEMPORAL_TEST=1 pytest apps/api/tests/test_executor.py`
runs a full campaign through a real local Temporal server.

### Database

SQLite by default (`alloylab.db` in the API working directory). For PostgreSQL:

```bash
docker compose -f infra/docker/docker-compose.yml up -d
export ALLOYLAB_DATABASE_URL=postgresql+asyncpg://alloylab:alloylab@localhost:5432/alloylab
uv sync --all-packages --extra postgres
```

## Tests

```bash
pnpm test          # turbo: science unit tests + backend unit/integration tests
```

The integration suite runs a **full synthetic campaign end-to-end without
OpenAI or Quantum ESPRESSO** — deterministic decisions, real Monte Carlo, model
refits, injected failure → diagnose → retry → succeed — per plan section 34.

## Beyond the plan

The plan's nine milestones are implemented. Natural next steps: spin-polarised
DFT and ionic relaxation for quantitative Ni-Al energetics; Alembic migrations
(the dev database is `create_all`-managed); a Postgres + Temporal deployment
profile; and richer LLM tooling (structure-inspection tools, self-critique of
recommendations) — the Pydantic AI harness makes those tools typed and testable.

Note: the dev database schema is created with `create_all` (no migrations yet);
after pulling schema changes, delete the local `alloylab.db` file.
