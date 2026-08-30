# Gibbs — an autonomous alloy scientist

A scientist states an engineering objective — *"find the stiffest FCC Ni-Al ordering
that is thermodynamically stable and stays ordered below 600 K"* — and watches an
agent work the problem: choose which structures to compute, spend a finite budget of
first-principles calculations, fit a cluster expansion with honest uncertainty,
verify candidates with Monte Carlo, rank them, and write up the evidence.

Not a chatbot. Every number on screen traces back to a typed job row with
provenance; the LLM decides *what to compute next* and *how to explain it*, and never
computes a quantity itself.

![A completed Cu-Au formation-energy hull campaign: the measured-vs-cluster-expansion
convex hull with per-structure uncertainty, the predicted stable structures, a 3D view
of the ordering on the hull, and the campaign activity feed.](screenshots/campaign.png)

<!-- TODO(video): 60-90s screen capture — create a campaign, press Start, watch
     decisions stream in, land on the final report. Embed as a link to a GIF or
     an uploaded .mp4 (GitHub renders drag-and-dropped video inline). -->

## The loop

| | |
|---|---|
| **Plan** | the agent picks the next structures to compute, under a fixed simulation budget |
| **Compute** | each choice becomes a typed job — Quantum ESPRESSO SCF, EMT, or a hidden synthetic oracle |
| **Model** | a cluster expansion is fitted over icet cluster vectors, LOOCV-validated, with bootstrap uncertainty |
| **Verify** | canonical Monte Carlo on the agent's *own fitted* CE checks that a candidate stays ordered |
| **Rank** | candidates are scored on stability, target property, and remaining uncertainty |
| **Explain** | a structured report cites every number back to the calculation that produced it |

Failures are part of the loop, not an exception path. SCF non-convergence is
detected from the `.pwo` log, categorised, and retried by the agent with doubled
`electron_maxstep` and halved `mixing_beta` — a failure mode that occurs for real in
elongated metallic cells. Scientific failures stay **data for the agent**;
only infrastructure failures (crash, timeout) hit the executor's retry policy.

Every decision is inspectable. The activity feed records what the agent chose, the
rationale, and the **evidence** it had at the time — *"Measuring T=2.123 refines the
susceptibility curve. Measure where the bootstrap surrogate ensemble disagrees most.
Evidence: 14 completed measurements; Tc = 2.4140 ± 0.1172 (surrogate v12)"* — followed
by the job it launched and the model version it refitted.

![The Ising critical-region campaign: the susceptibility curve with the surrogate's
uncertainty band and the located Tc, the decision trail with per-decision evidence, and
the calculations table with its failure/retry lineage column.](screenshots/ising_critical_region_mc.png)

<!-- TODO(screenshot): an activity feed showing a diagnose → retry → succeed sequence
     (run a campaign with ALLOYLAB_INJECTED_FAILURE_RATE=0.3 to produce one). The
     failure-recovery story is more convincing shown than described. -->

## The copilot — eyes and hands, not a chat box

A Pydantic AI agent is docked beside every page. Its **eyes** are read-only tools
over the same view builders the dashboards render from (`get_hull`,
`get_phase_diagram`, `get_candidates`, `get_report`, `list_calculations`,
`get_calculation` with the engine-log tail, `list_decisions`, `list_elements`), so
every number it quotes comes from a persisted calculation and is cited as a
`[calc:…]` chip that opens the evidence.

It has exactly one **hand**: `propose_campaign_params`. On the new-campaign form it
fills in fields with a rationale, the changed fields light up, and the scientist
presses Create. It cannot start, pause, or mutate a campaign — the scientist stays
the one who spends compute.

![The copilot sidebar beside the new-campaign form: it loaded a hull-interpretation
skill, proposed a full parameter set with a rationale, and the changed form fields are
highlighted — ending with "The form is ready, but the scientist still needs to press
Create."](screenshots/copilot.png)

The agent is configured from the database rather than hardcoded: `agent.agent` +
`agent_config` hold prompt, model and sampling; tool sets restrict which registered
tools it may call; skill sets are documents it pulls in with `load_skill`, and
`message_skill` records which ones each reply used. Chats persist relationally
(`agent.chat` → `agent.messages` → `agent.tool_call`; model history is rebuilt from
rows each turn, and page context travels with every message). Replies stream over
SSE with tool calls rendered as cards. The default copilot, its tool set, and three
materials-science skills ship as seed data (`apps/web/supabase/seeds/*.sql`), not
migration content.

`apps/api/src/gibbs/copilot/`, `apps/web/components/copilot/`.

## Measuring whether the search actually works

Every problem has a **hidden ground-truth Hamiltonian**, so a campaign's answer can
be scored against the exact one. The benchmark harness runs the deterministic
acquisition baselines — `random`, `grid`, `uncertainty` — against that truth and
reports:

- **hull problems** — convex-hull RMSE, plus missed and false stable phases
- **phase-diagram problems** — mean |Tc error| across the composition range
- **property search** — regret in GPa against the truly best stable intermetallic

This is the part that keeps the project honest, and it has already earned its keep:
the benchmark caught a real pathology in the phase-boundary acquisition function —
raw max-std sampling chases the *edges of the temperature range* rather than the
uncertain boundary. The fix (posterior sampling of the peak location) exists because
the harness measured the problem, not because it looked wrong.

The benchmark endpoint deliberately **excludes** the LLM `agent` strategy: an
LLM-driven run is scored by running an `agent`-strategy campaign and reading its
report, so a stochastic decider is never averaged into a table of deterministic ones.

![Benchmark mode: binary-alloy and Ni-Al phase-diagram tables, each strategy given the
same budget against the same hidden Hamiltonian and ranked by hull RMSE and mean |Tc
error|.](screenshots/benchmarks.png)

And it reports results that do not flatter the method. In the runs above — budget 20,
three seeds — plain `random` beats `uncertainty` sampling on both problems (hull RMSE
0.0161 vs 0.0185; mean |Tc error| 78 K vs 93 K). At this budget and seed count that is
what the evidence says, and the number shown is the number measured. Establishing
where active selection *does* pay for itself — larger budgets, more seeds, higher-cost
engines — is exactly what the harness exists to answer.

## What it can compute

The platform was built on synthetic problems with exact answers first, then moved to
real first-principles calculations behind the same interfaces. All of these run
through one problem-agnostic campaign loop (`gibbs/problems/` adapters), so adding a
problem touches neither the loop, the executor, nor the failure policy.

- **Ising V0** — locate the critical-temperature region of the 2D Ising model with a
  finite Monte Carlo budget. The smallest honest version of "spend a budget to find a
  transition."
- **Alloy V1** — a binary alloy A(1-x)B(x) on a 2D lattice under a *hidden* pair
  Hamiltonian. The agent enumerates orderings, spends a finite oracle budget on
  simulated-DFT energies, fits a mini cluster expansion over correlation features, and
  recovers the formation-energy convex hull and its stable orderings (e.g. the
  checkerboard A2B2 ground state).
- **FCC Ni-Al V2** — real crystallography via ASE + icet: symmetry-enumerated FCC
  orderings, an icet cluster space whose cluster vectors are the CE design rows,
  LOOCV-validated fitting with bootstrap uncertainty, and a hidden icet-style cluster
  expansion as ground truth. The agent finds L1_2 Ni3Al / L1_0 NiAl-type ground states;
  `alloyscience.fcc.run_canonical_mc` samples the fitted CE with mchammer (canonical MC
  plus Warren-Cowley short-range order).
- **Phase diagrams** — map the order/disorder boundary Tc(x) of a hidden CE on a finite
  canonical-MC budget. Heat-capacity peaks locate the transition per composition slice,
  bootstrap ensembles quantify boundary uncertainty (edge-pinned estimates are flagged
  as *bounds*, not locations), and acquisition targets the most uncertain boundary. The
  dashboard draws the T-x diagram with uncertainty bars, the ordered region, per-run SRO
  coloring, and a per-slice C(T) inspector.
- **Real DFT** — the same hull campaign with a real energy engine behind the
  `EnergyCalculator` boundary (`alloyscience.calculators`): `emt` (ASE's classical
  potential, with volume optimisation and curvature-derived bulk moduli) or `espresso`
  (pw.x single-point SCF at the Vegard-scaled lattice). Espresso runs execute in
  per-calculation artifact directories; the `.pwo` log is stored on the job record and
  served at `/calculations/{id}/log`.
- **Property search** — "stiffest ordering that is stable *and* stays ordered below a
  threshold." Each query returns energy and bulk modulus; two bootstrap surrogates over
  the cluster vectors (energy → hull, bulk modulus) feed a ranked candidate table; the
  agent then spends the tail of its budget on canonical-MC verification at the threshold
  temperature and disqualifies candidates that disorder.
- **Full autonomous campaign** — the whole chain on the real engine: choose structures
  → run DFT (with an E(V) scan for bulk moduli) → fit CE → verify with MC → rank →
  **explain**. Every completed campaign persists a structured report (`GET
  /campaigns/{id}/report`, `/campaigns/[id]/report` in the UI): recommendation with
  confidence, key results, model quality, budget and engine time, failure/retry summary,
  the full reasoning trail, and an explicit limitations section — built deterministically
  from the persisted record so every number has provenance. With a provider key set, an
  LLM pass writes the prose *from those structured facts* (it may paraphrase, never
  invent numbers).

![The stiff-and-stable property search: bulk modulus vs composition with candidates
colored by stable/ordered/disorders-at-T/unstable, and the ranked candidate table
carrying formation energy, distance above hull, bulk modulus with uncertainty, the
verdict at 1200 K, and whether each figure was measured or
predicted.](screenshots/stiffest_stable_intermediate.png)

The `SOURCE` column is the point: a ranked list that says which of its own numbers came
from a calculation and which came from the surrogate, so the scientist can see how much
of the ranking is evidence and how much is extrapolation.

<!-- TODO(screenshot): the T-x phase diagram with uncertainty bars and the ordered region. -->

![The final report for a Cu-Au hull campaign: an LLM-written summary labelled "prose
written by the LLM from the structured facts below", then the structured facts
themselves — key results, model and confidence, budget and engines (15/15 calculations,
254 s of quantum-espresso pw.x, 0 failed), failures, and
limitations.](screenshots/final_report_fcc_cu_au_hull.png)

Note the caption under the summary: **prose written by the LLM from the structured facts
below**. The facts are assembled deterministically from the persisted record first; the
model's only job is to say them in English. The limitations section is generated the same
way — this report tells you, unprompted, that its own numbers are not quantitatively
reliable.

### Any element pair

The FCC problems (`fcc_v2`, `phase_v2`, `dft_v3`, `property_v3`) take an **element
pair** `[A, B]` — a searchable picker backed by `GET /campaigns/elements` — with
composition `x` as the fraction of B. Element A sets the parent FCC lattice constant
(from ASE reference data; BCC/HCP elements are placed on an equal-atomic-volume FCC
lattice) and cluster-space cutoffs scale with it, so every pair gets the same pair
shells. Elements that are not FCC at ambient conditions (Fe, Ti, …) are allowed but
flagged as a *hypothetical FCC lattice* in the picker and in the report's limitations.

Engine support is validated at campaign creation: EMT covers Al, Cu, Ag, Au, Ni, Pd,
Pt; Quantum ESPRESSO needs one UPF per element in `infra/pseudopotentials/` — fetch
PSlibrary PAW sets with:

```bash
uv run --package gibbs python -m gibbs.pseudos Cu Au
```

## Architecture

Three layers, kept separate on purpose:

| Layer | Code | Responsibility |
|---|---|---|
| Intelligence | `apps/api/src/gibbs/agent/` (Pydantic AI + heuristics) | scientific decisions |
| Scientific truth | `packages/science/src/alloyscience/` (NumPy/SciPy) | numerical results |
| Execution infra | `apps/api/src/gibbs/{jobs,db,api}/` (FastAPI, SQLAlchemy over Supabase Postgres, SSE) + `apps/web/db/` (Drizzle schema & migrations) | durable, inspectable experiments |

The LLM never computes numbers. Every scientific quantity comes from a deterministic
tool, every calculation is a typed job row with provenance, and every agent decision
is persisted as a structured `AgentEvent` — tagged `heuristic` or `llm`, so a
templated argmax is never displayed as reasoning.

```
apps/
  web/        Next.js + Tailwind mission-control UI  (/campaigns, /campaigns/[id], /benchmarks)
  api/        FastAPI backend: campaigns, jobs, agent loop, SSE, benchmarks, copilot
packages/
  science/    alloyscience: Ising MC, cluster expansion, bootstrap surrogate, convex hull,
              strategies, benchmark harness
  api-client/ TypeScript client generated from the FastAPI OpenAPI schema
  typescript-config/
infra/
  docker/     plain Postgres 16 compose (alternative to the Supabase stack)
  temporal/   Temporal compose
apps/web/db/schema/   Drizzle schema (source of truth)
apps/web/supabase/    Supabase project config + migrations/ (drizzle-kit output)
```

## Quickstart

Prerequisites: Node ≥ 20 with `pnpm`, and `uv` (Python 3.12 is managed for you).

```bash
pnpm install
uv sync --all-packages --all-extras
pnpm --filter @gibbs/api-client generate   # regenerate TS client from OpenAPI (committed)

# terminal 1 — API on :8000
pnpm --filter @gibbs/api dev

# terminal 2 — web on :3000
pnpm --filter @gibbs/web dev
```

Open http://localhost:3000 — you land on **/login**; sign up with any email and
password (no email verification), then create a campaign, press **Start**, and watch
the agent work. Nothing above needs an API key, a DFT binary, or Docker: the default
path runs on SQLite against synthetic oracles with exact ground truth.

## Reference

### The LLM agent strategy

Heuristic strategies (`random`, `grid`, `uncertainty`) run fully offline. The `agent`
strategy runs on **Pydantic AI** with structured output (`output_type`) and
deterministic inspection tools. The model is a provider-prefixed Pydantic AI model
string set via `ALLOYLAB_AGENT_MODEL` (default `openai:gpt-5`; e.g.
`anthropic:claude-sonnet-4-5`, `google-gla:gemini-2.5-pro`), with the provider's key
in the API's environment (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, …).
`ALLOYLAB_AGENT_MODEL=test` runs the full agent path on Pydantic AI's built-in
`TestModel` — no key needed — which is how the harness is unit-tested.

### Tracing

Agent runs emit OpenTelemetry spans (agent run → model request → tool call → output
validation) via Pydantic AI's instrumentation, rewritten by an OpenInference span
processor and shipped to Arize AX. Opt-in: set `ARIZE_SPACE_ID` and `ARIZE_API_KEY`
and it turns on; otherwise `setup_tracing()` is a no-op, so tests and keyless dev runs
are unaffected. `apps/api/src/gibbs/tracing.py`.

### Exercising failure recovery

The synthetic oracles (Ising MC, hidden CE, EMT) are deterministic numerics and never
fail on their own, so the diagnose → retry → abandon path is only exercised by
injecting failures. That is a **testing seam, not a campaign setting** — off by
default, and settable from neither the UI nor the API request body, because a
scientist's budget should never be spent on fabricated failures (a failure and its
retry both count against `simulations_used`):

```bash
export ALLOYLAB_INJECTED_FAILURE_RATE=0.3   # 0.0 (default) .. 0.9
```

Campaigns read the rate at creation and record it on the campaign row, so any run
that saw injected failures says so in its own provenance. Real Quantum ESPRESSO SCF
non-convergence is detected from the `.pwo` log and needs no injection.

### Real DFT (Quantum ESPRESSO)

The `espresso` engine needs a `pw.x` binary and PAW pseudopotentials in
`infra/pseudopotentials/` (Ni.pbe-spn-kjpaw and Al.pbe-n-kjpaw, PSlibrary 1.0.0):

```bash
export ALLOYLAB_PW_COMMAND=$HOME/.local/qe/bin/pw.x   # built from source (cmake, serial+OpenMP)
export ALLOYLAB_PSEUDO_DIR=$PWD/infra/pseudopotentials
```

The env-gated science test `test_espresso_real_scf_on_pure_ni` runs a real SCF when
`ALLOYLAB_PW_COMMAND` is set. Espresso campaigns take minutes per structure — which
is what durable execution is for.

### Durable execution (Temporal)

With `ALLOYLAB_EXECUTOR=temporal`, every calculation runs as a
`RunCalculationWorkflow` on a Temporal task queue, executed by separate worker
processes. Kill a worker mid-campaign and the campaign stalls *durably*, then resumes
and completes when a worker returns; in-flight activities are detected via heartbeats
and retried. Exhausted retries surface as `INFRASTRUCTURE_FAILURE` job records. Live
SSE events still stream from the API process, and the durable unit
(`execute_and_persist`) is idempotent and identical on the local and Temporal paths.

```bash
brew install temporal
temporal server start-dev                   # UI at http://localhost:8233
export ALLOYLAB_EXECUTOR=temporal
pnpm --filter @gibbs/api worker             # one or more workers
pnpm --filter @gibbs/api dev                # the API
```

(`infra/temporal/docker-compose.yml` is the container alternative.) The env-gated
test `ALLOYLAB_TEMPORAL_TEST=1 pytest apps/api/tests/test_executor.py` runs a full
campaign through a real local Temporal server.

### Authentication (Better Auth)

The web app is gated by [Better Auth](https://www.better-auth.com) with email +
password sign-in (`apps/web/lib/auth.ts`, tables in the `app_auth` Postgres schema —
Supabase owns `auth`). Set `BETTER_AUTH_SECRET` (and `BETTER_AUTH_URL` for a hosted
deploy) in `apps/web/.env.local`; see `.env.example`. `middleware.ts` redirects
anonymous visitors to `/login`, and `app/(app)/layout.tsx` verifies the session
server-side.

The FastAPI backend requires the same session on **every** endpoint except `/health`
(`gibbs/api/auth.py`, applied router-wide in `main.py`). The browser sends the session
token as `Authorization: Bearer …` — Better Auth's `bearer` plugin hands it out on
sign-in — and the API looks it up in `app_auth.session` (shared database, no extra
config). `EventSource` cannot set headers, so the SSE route accepts `?token=` when the
request negotiates `text/event-stream`. In tests the dependency is stubbed
(`tests/conftest.py`); `tests/test_auth.py` exercises the real check.

### Database: Supabase + Drizzle

The schema of record lives in **`apps/web/db/schema/`** (one Drizzle file per table
plus `relations.ts` and `schemas.ts`); migrations are generated by drizzle-kit into
**`apps/web/supabase/migrations/`** — the Supabase CLI's own migration folder — so
`supabase db reset` / `migration up` / `db push` apply them directly. Drizzle
generates, Supabase applies: one migration folder, one migration tracker.

Tables live in four Postgres schemas that mirror the code's layers — never in
`public`, which Supabase exposes to anon-key clients via PostgREST:

| schema | tables |
|---|---|
| `science` | campaigns, structures, calculations, surrogate_models — the scientific record |
| `agent` | agent_runs, agent_events, chat, messages, tool_call — the decision trail |
| `benchmarks` | benchmark_runs |
| `app_auth` | user, session, account, verification — Better Auth |

Row-level security is enabled on every table (defense-in-depth; no policies, so
nothing is readable through the REST API). The API and the Drizzle client connect as
the table owner (`postgres`), which RLS does not apply to. The Python API (SQLAlchemy
over asyncpg) mirrors the same tables for its queries and never creates tables in
Postgres — on startup it verifies the Drizzle-created tables exist and tells you to
migrate if not.

```bash
# local Supabase stack (config in apps/web/supabase/, ports 5433x so it can
# coexist with other local projects); needs Docker + the Supabase CLI
cd apps/web && supabase start            # DB on 127.0.0.1:54332, Studio on :54333

# schema workflow
pnpm --filter @gibbs/web db:generate  # drizzle-kit generate -> supabase/migrations/NNNN_*.sql
pnpm --filter @gibbs/web db:migrate   # supabase migration up: apply pending to the local stack
pnpm --filter @gibbs/web db:reset     # supabase db reset: wipe + re-apply every migration (+ seeds)
pnpm --filter @gibbs/web db:push      # supabase db push: apply pending to the linked hosted project
pnpm --filter @gibbs/web db:studio    # drizzle studio

# point both apps at the database (see apps/web/.env.example)
export DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54332/postgres
export ALLOYLAB_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:54332/postgres
```

For a hosted Supabase project use its *session-mode* pooler URI (port 5432) in both
variables. `ALLOYLAB_DATABASE_URL=sqlite+aiosqlite:///./gibbs.db` still works for
zero-config dev and is what the test suite uses; the env-gated
`apps/api/tests/test_postgres.py` (set `ALLOYLAB_TEST_DATABASE_URL`) runs full
campaigns against a Drizzle-migrated Postgres. `infra/docker/` keeps a plain Postgres
16 compose file as a lighter alternative to the full Supabase stack — the migrations
are the same.

## Tests

```bash
pnpm test          # turbo: science unit tests + backend unit/integration tests + web tests
```

The integration suite runs a **full synthetic campaign end-to-end with no LLM
provider and no Quantum ESPRESSO** — deterministic decisions, real Monte Carlo, model
refits, injected failure → diagnose → retry → succeed. CI runs the same three suites
on every push and pull request.

## Limitations

Stated plainly, because the report states them too:

- **Physics settings are demo-grade.** Non-spin-polarised, modest k-mesh, no ionic
  relaxation. Ordered Ni-Al compounds do come out stable, but the numbers are not
  publication-quality.
- **Non-FCC elements are hypothetical.** Fe, Ti and friends are placed on an
  equal-atomic-volume FCC lattice and flagged as such wherever they appear.
- **The benchmark scores acquisition strategies, not the LLM.** An LLM-driven run is
  evaluated by reading its campaign report, not by averaging it into the baseline table.

## What's next

- Spin-polarised DFT and ionic relaxation, for quantitative Ni-Al energetics
- An eval harness for the copilot: citation validity, groundedness, refusal when the
  record does not support an answer
- Alembic migrations for the SQLite dev path (Postgres already uses Drizzle migrations)
- A deployed Postgres + Temporal profile

**[LONG_TERM_GOAL.md](LONG_TERM_GOAL.md)** lays out the hierarchy of objectives
(application goal → figures of merit → candidate systems → stability → experiments),
which decisions belong to tools versus the agent, and the build order beyond the
current scope. **[project_description.md](project_description.md)** is the original
nine-milestone design document; all nine are implemented.

Note: on Postgres the schema comes from the Drizzle migrations in
`apps/web/supabase/migrations` (`pnpm --filter @gibbs/web db:migrate`); the SQLite
test/dev path is `create_all`-managed, so after pulling schema changes delete the
local `gibbs.db` file.

## License

[MIT](LICENSE) © 2026 Brett Cleary
