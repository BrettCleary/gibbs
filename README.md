# AlloyLab — Autonomous Alloy Scientist

An autonomous computational materials-science platform (see `project_description.md`
for the full plan). This repository currently implements **Milestone 1 (Foundation)**
and **Milestone 2 (Ising Scientist)**: the complete product loop — agent decisions,
typed simulation jobs, surrogate models with uncertainty, failure recovery, live
mission-control UI, and a strategy benchmark — running against the synthetic 2D
Ising problem, exactly as the plan prescribes ("DO THIS BEFORE REAL DFT").

The V0 scientific problem: **autonomously locate the critical-temperature region
of the 2D Ising model with a finite Monte Carlo budget**, and quantitatively
compare the scientist against random/grid/uncertainty baselines.

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

- Milestone 3: hidden binary-alloy lattice Hamiltonian (composition, formation
  energies, ground-state search; `alloyscience.thermodynamics` hull code is
  already in place and tested)
- Milestone 4: icet cluster expansions
- Milestone 6: ASE + Quantum ESPRESSO behind the same `Calculation` job type
- Milestone 7: swap the async executor for Temporal without touching the agent
