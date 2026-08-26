# AlloyLab — Autonomous Alloy Scientist

An autonomous computational materials-science platform (see `project_description.md`
for the full plan). This repository currently implements **Milestones 1–5**: the
complete product loop — agent decisions, typed simulation jobs, surrogate models
with uncertainty, failure recovery, live mission-control UI, and strategy
benchmarks — on four synthetic problems, exactly as the plan prescribes
("DO THIS BEFORE REAL DFT"):

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

Benchmark mode scores strategies against the exact hidden Hamiltonian: hull
RMSE and missed/false stable phases for the hull problems, mean |Tc error|
(the plan's phase-boundary error) for the phase problem. All problems run
through one problem-agnostic campaign loop (`alloylab/problems/` adapters), so
V3 (real DFT) slots in without touching the loop, executor, or failure policy.

## Architecture (three layers, kept separate)

| Layer | Code | Responsibility |
|---|---|---|
| Intelligence | `apps/api/src/alloylab/agent/` (OpenAI Agents SDK + heuristics) | scientific decisions |
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
`agent` strategy uses the OpenAI Agents SDK and requires `OPENAI_API_KEY` in the
API's environment (model configurable via `ALLOYLAB_AGENT_MODEL`, default `gpt-5`).

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

## What's next (per the plan)

- Milestone 6: ASE + Quantum ESPRESSO behind the same `STRUCTURE_ENERGY` job type
- Milestone 7: swap the async executor for Temporal without touching the agent
- Milestone 8: property search (bulk modulus) subject to finite-temperature
  stability from the Milestone 5 boundary machinery

Note: the dev database schema is created with `create_all` (no migrations yet);
after pulling schema changes, delete the local `alloylab.db` file.
