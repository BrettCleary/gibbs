"""The copilot agent: instructions, context, tools, and the streaming reply.

Tools are split into *eyes* (read-only views over persisted campaign data —
the same builders the dashboards use) and *hands* (proposing parameters on the
new-campaign form). The agent cannot start, pause, or mutate a campaign;
those stay behind buttons the scientist presses.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, FunctionToolset, ModelRetry, RunContext
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolReturnPart,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import views
from .registry import AgentDefinition, SkillRef, default_definition, skill_content
from ..db.models import AgentEvent, Calculation, Campaign
from ..schemas import CampaignRead, DftEngine, ProblemType, PropertyEngine, StrategyName

MAX_TOOL_CHARS = 14_000
SYNTHETIC_PROBLEMS = {"alloy_v1", "fcc_v2", "phase_v2"}
LOG_TAIL_LINES = 60


# --------------------------------------------------------------------------- context


class CopilotContext(BaseModel):
    """What the scientist is looking at, sent with every message."""

    page: Literal["new_campaign", "campaign", "other"] = "other"
    campaign_id: str | None = None
    # Current values of the new-campaign form (keys match CampaignParamsPatch).
    form: dict[str, Any] | None = None


class CampaignParamsPatch(BaseModel):
    """A partial update to the new-campaign form. Only set the fields to change."""

    name: str | None = None
    problem_type: ProblemType | None = None
    element_a: str | None = Field(default=None, description="Element symbol, e.g. 'Cu'.")
    element_b: str | None = Field(default=None, description="Element symbol; x is its fraction.")
    strategy: StrategyName | None = None
    simulation_budget: int | None = Field(default=None, ge=4, le=200)
    target_uncertainty: float | None = Field(
        default=None, description="Optional early-stopping uncertainty target."
    )
    dft_engine: DftEngine | None = Field(default=None, description="dft_v3 only.")
    property_engine: PropertyEngine | None = Field(default=None, description="property_v3 only.")
    temperature_threshold: float | None = Field(
        default=None, gt=0, description="property_v3: candidates must stay ordered below this T (K)."
    )
    lattice_size: int | None = Field(default=None, ge=8, le=64, description="ising_v0 only.")
    temperature_min: float | None = Field(default=None, description="ising_v0 (reduced units).")
    temperature_max: float | None = Field(default=None, description="ising_v0 (reduced units).")
    phase_t_min: float | None = Field(default=None, gt=0, description="phase_v2: T window low (K).")
    phase_t_max: float | None = Field(default=None, gt=0, description="phase_v2: T window high (K).")


@dataclass
class CopilotDeps:
    session: AsyncSession
    user_id: str
    context: CopilotContext
    # Proposals recorded by the hands-tools during this run (streamed to the UI).
    patches: list[dict] = field(default_factory=list)
    # The agent definition this run uses (tool sets, skill sets, model settings).
    definition: AgentDefinition | None = None
    # Skills loaded during this run, recorded on the assistant message.
    loaded_skills: list[SkillRef] = field(default_factory=list)


# ---------------------------------------------------------------------- instructions

INSTRUCTIONS = """You are the Gibbs copilot: a materials-science colleague embedded in Gibbs, an
autonomous computational materials-science platform. Scientists run *campaigns*: an
objective, a finite calculation budget, and a strategy that picks experiments. You help
them set campaigns up, follow what a running campaign is doing, and interpret finished
results.

Campaign problem types (real simulations):
- dft_v3: a formation-energy hull with EMT (fast classical potential; Al, Cu, Ag, Au,
  Ni, Pd, Pt only) or Quantum ESPRESSO DFT (slow, needs pseudopotentials on disk).
- property_v3 (engine emt or espresso): the FCC A-B ordering with the highest bulk
  modulus that is on the hull and stays ordered below a threshold temperature.
- ising_v0: locate the critical temperature of a 2D Ising model by real Monte Carlo
  (reduced units, T~2.27).
Benchmark problems (synthetic, hidden ground truth — run from the Benchmarks page, never
proposed as campaigns): alloy_v1 (hidden pair Hamiltonian), fcc_v2 (hidden cluster
expansion), phase_v2 (Monte Carlo on a hidden CE), property_v3 with the hidden engine.
You may still read and explain existing campaigns of those types; say they are
synthetic and that their energies are dimensionless.
Strategies: `agent` (LLM scientist choosing experiments), `uncertainty` (bootstrap
ensemble uncertainty sampling — usually the strongest), `grid` (coverage), `random`.
Composition x is always the fraction of element B.

Rules:
1. Every number you state must come from a tool call in this conversation. Never
   estimate energies, temperatures, or moduli from memory. If a tool has no data yet,
   say so.
2. Cite evidence inline with reference tokens the interface turns into links:
   [calc:<calculation_id>] for calculations, [campaign:<campaign_id>] for campaigns.
   Cite the calculation behind any specific measurement you quote.
3. On the new-campaign page, make changes with `propose_campaign_params` — one call
   with every field you want to change — and give a one-sentence rationale. The
   scientist reviews the highlighted fields and presses Create; you cannot create,
   start, pause, or delete campaigns.
4. Use your domain knowledge freely for *interpretation and setup* (known phases,
   experimental transition temperatures, why a Monte Carlo cluster-expansion estimate
   overshoots a measured Tc), but label it as literature/background, distinct from
   campaign results.
5. Be concise and concrete. Units: eV/atom, K, GPa, Å. Prefer short paragraphs or
   tight lists over headings.
"""


def _skill_instructions(ctx: RunContext[CopilotDeps]) -> str:
    """List the agent's skills so the model can decide when to load one."""
    definition = ctx.deps.definition
    if not definition or not definition.skills:
        return ""
    lines = [
        "Skills available via load_skill (load one before relying on its guidance; "
        "skills inform setup and interpretation — results still come only from tools):"
    ]
    for skill in definition.skills:
        lines.append(f"- {skill.name}: {skill.description or ''}".rstrip())
    return "\n".join(lines)


def _context_instructions(ctx: RunContext[CopilotDeps]) -> str:
    c = ctx.deps.context
    if c.page == "new_campaign":
        form = json.dumps(c.form or {}, default=str)
        return (
            "The scientist is on the NEW CAMPAIGN form. Current form values (JSON): "
            f"{form}. Change settings only via propose_campaign_params."
        )
    if c.page == "campaign" and c.campaign_id:
        return (
            f"The scientist is viewing campaign {c.campaign_id}. Start by reading it with "
            "get_campaign / get_report before answering questions about its results."
        )
    return "The scientist is on a general page (campaign list or benchmarks)."


# ---------------------------------------------------------------------------- helpers


def _dump(data: Any) -> str:
    text = json.dumps(data, default=str)
    if len(text) > MAX_TOOL_CHARS:
        return json.dumps({"truncated": True, "preview": text[:MAX_TOOL_CHARS]})
    return text


def _r(value: Any, nd: int = 4) -> Any:
    return round(value, nd) if isinstance(value, float) else value


async def _campaign(ctx: RunContext[CopilotDeps], campaign_id: str) -> Campaign:
    """A campaign the chat's user owns. Someone else's is simply not found."""
    campaign = await ctx.deps.session.get(Campaign, campaign_id)
    if campaign is None or campaign.user_id != ctx.deps.user_id:
        raise ModelRetry(f"campaign {campaign_id!r} not found")
    return campaign


def _calc_summary(c: Calculation) -> dict:
    p = c.input_parameters or {}
    out = c.output or {}
    summary = {
        "id": c.id,
        "type": c.calculation_type,
        "engine": c.engine,
        "status": c.status,
        "structure_label": p.get("structure_label"),
        "composition": _r(p.get("composition")),
        "temperature": _r(p.get("temperature")),
        "retry_of": c.retry_of,
        "failure_category": c.failure_category,
        "resolution": c.resolution,
    }
    for key in (
        "energy_per_site",
        "e_form",
        "optimal_lattice_constant",
        "bulk_modulus",
        "susceptibility",
        "susceptibility_err",
        "heat_capacity",
        "heat_capacity_err",
        "sro",
    ):
        if key in out:
            summary[key] = _r(out[key])
    return summary


# ------------------------------------------------------------------------------ agent


def build_copilot_agent(model, definition: AgentDefinition | None = None) -> Agent[CopilotDeps, str]:
    """Build the copilot from an agent definition (DB row or the in-code default).

    Tool sets restrict which of the tools registered here the model may call;
    skill sets add a `load_skill` tool over the definition's skills.
    """
    definition = definition or default_definition(INSTRUCTIONS)
    # Models issue tool calls in parallel; the tools share one AsyncSession, so
    # the toolset runs them sequentially.
    tools: FunctionToolset[CopilotDeps] = FunctionToolset(sequential=True)
    enabled = definition.enabled_tools
    toolset = (
        tools
        if enabled is None
        else tools.filtered(lambda ctx, tool: tool.name in enabled or tool.name == "load_skill")
    )
    agent: Agent[CopilotDeps, str] = Agent(
        model,
        deps_type=CopilotDeps,
        instructions=[definition.instructions, _skill_instructions, _context_instructions],
        name=f"gibbs-{definition.name}",
        retries=2,
        toolsets=[toolset],
        model_settings=definition.model_settings(),
    )

    if definition.skills:

        @tools.tool
        async def load_skill(ctx: RunContext[CopilotDeps], skill_name: str) -> str:
            """Load the full text of one of your skills by name (see the skills list in
            your instructions). Load a skill before following its guidance."""
            found = await skill_content(ctx.deps.session, ctx.deps.definition or definition, skill_name)
            if found is None:
                names = ", ".join(s.name for s in definition.skills)
                raise ModelRetry(f"unknown skill {skill_name!r}; available: {names}")
            ref, content = found
            if ref not in ctx.deps.loaded_skills:
                ctx.deps.loaded_skills.append(ref)
            return content

    # ------------------------------------------------------------------ eyes

    @tools.tool
    async def list_campaigns(ctx: RunContext[CopilotDeps]) -> str:
        """The user's campaigns (most recent first): id, name, problem type, status,
        elements, budget."""
        rows = (
            await ctx.deps.session.execute(
                select(Campaign)
                .where(Campaign.user_id == ctx.deps.user_id)
                .order_by(Campaign.created_at.desc())
            )
        ).scalars().all()
        return _dump(
            [
                {
                    "id": c.id,
                    "name": c.name,
                    "problem_type": c.problem_type,
                    "strategy": c.strategy,
                    "status": c.status,
                    "elements": c.elements,
                    "budget_used": c.simulations_used,
                    "budget_total": c.simulation_budget,
                }
                for c in rows
            ]
        )

    @tools.tool
    async def get_campaign(ctx: RunContext[CopilotDeps], campaign_id: str) -> str:
        """A campaign's settings, status, budget, and stopping rationale."""
        c = await _campaign(ctx, campaign_id)
        data = CampaignRead.model_validate(c).model_dump(mode="json")
        cfg = c.problem_config or {}
        data["engine"] = cfg.get("dft_engine") or cfg.get("property_engine") or cfg.get("engine")
        data["temperature_threshold"] = cfg.get("temperature_threshold")
        return _dump(data)

    @tools.tool
    async def get_report(ctx: RunContext[CopilotDeps], campaign_id: str) -> str:
        """The scientific report: key results, recommendation, limitations, decision trail,
        failure summary. Works for campaigns still in progress (provisional)."""
        c = await _campaign(ctx, campaign_id)
        if c.report:
            report = dict(c.report)
        else:
            from ..report import build_report

            report = await build_report(ctx.deps.session, c)
        report.pop("llm_narrative", None)
        report["decision_trail"] = report.get("decision_trail", [])[-12:]
        return _dump(report)

    @tools.tool
    async def get_hull(ctx: RunContext[CopilotDeps], campaign_id: str) -> str:
        """Formation-energy hull for alloy campaigns (alloy_v1, fcc_v2, dft_v3, property_v3):
        every structure with measured or predicted e_form (eV/atom) and uncertainty, the
        predicted stable set, and the cluster-expansion LOOCV error."""
        c = await _campaign(ctx, campaign_id)
        view = await views.hull_view(ctx.deps.session, c)
        return _dump(
            {
                "model_version": view.model_version,
                "energy_unit": view.energy_unit,
                "loocv_rmse": _r(view.loocv_rmse),
                "endpoints_measured": view.endpoints_measured,
                "stable_labels": view.stable_labels,
                "hull": [{"x": _r(x), "e_form": _r(e)} for x, e in zip(view.hull_x, view.hull_e)],
                "structures": [
                    {
                        "label": p.label,
                        "structure_id": p.structure_id,
                        "x": _r(p.x),
                        "e_form": _r(p.e_form),
                        "e_form_std": _r(p.e_form_std),
                        "measured": p.measured,
                        "predicted_stable": p.predicted_stable,
                    }
                    for p in sorted(view.points, key=lambda p: (p.x, p.label))
                ],
            }
        )

    @tools.tool
    async def get_phase_diagram(ctx: RunContext[CopilotDeps], campaign_id: str) -> str:
        """T-x phase diagram for phase_v2 campaigns: per-composition Tc estimate (K) with
        uncertainty, whether it is pinned to the window edge, and the measurements
        (heat capacity, short-range order) behind it."""
        c = await _campaign(ctx, campaign_id)
        view = await views.phase_diagram_view(ctx.deps.session, c)
        return _dump(
            {
                "model_version": view.model_version,
                "temperature_window_K": [view.temperature_min, view.temperature_max],
                "slices": [
                    {
                        "x": _r(s.x),
                        "tc_mean_K": _r(s.tc_mean, 1),
                        "tc_std_K": _r(s.tc_std, 1),
                        "edge_pinned": s.tc_edge_pinned,
                        "measurements": [
                            {
                                "calculation_id": m.calculation_id,
                                "T": _r(m.temperature, 1),
                                "heat_capacity": _r(m.heat_capacity),
                                "heat_capacity_err": _r(m.heat_capacity_err),
                                "sro": _r(m.sro),
                            }
                            for m in s.measured
                        ],
                    }
                    for s in view.slices
                ],
            }
        )

    @tools.tool
    async def get_candidates(ctx: RunContext[CopilotDeps], campaign_id: str) -> str:
        """Ranked candidates for property_v3 campaigns: e_form, energy above hull, bulk
        modulus (GPa) with uncertainty, stability at the threshold temperature, score."""
        c = await _campaign(ctx, campaign_id)
        view = await views.candidates_view(ctx.deps.session, c)
        return _dump(
            {
                "temperature_threshold_K": view.temperature_threshold,
                "model_version": view.model_version,
                "top_candidate": view.top_candidate_label,
                "candidates": [
                    {k: _r(v) for k, v in cand.model_dump().items()} for cand in view.candidates
                ],
            }
        )

    @tools.tool
    async def list_calculations(
        ctx: RunContext[CopilotDeps],
        campaign_id: str,
        status: Literal["SUCCEEDED", "FAILED", "RUNNING", "QUEUED"] | None = None,
        limit: int = 60,
    ) -> str:
        """Calculations of a campaign (newest first) with key inputs and outputs. Filter by
        status to see failures. Use get_calculation for full detail and engine logs."""
        await _campaign(ctx, campaign_id)
        q = select(Calculation).where(Calculation.campaign_id == campaign_id)
        if status:
            q = q.where(Calculation.status == status)
        rows = (
            await ctx.deps.session.execute(q.order_by(Calculation.created_at.desc()).limit(limit))
        ).scalars().all()
        return _dump([_calc_summary(c) for c in rows])

    @tools.tool
    async def get_calculation(ctx: RunContext[CopilotDeps], calculation_id: str) -> str:
        """Full detail of one calculation: inputs, outputs, provenance, failure metadata,
        retry lineage, and the tail of its engine log if one exists."""
        c = (
            await ctx.deps.session.execute(
                select(Calculation)
                .join(Campaign, Campaign.id == Calculation.campaign_id)
                .where(
                    Calculation.id == calculation_id,
                    Campaign.user_id == ctx.deps.user_id,
                )
            )
        ).scalar_one_or_none()
        if c is None:
            raise ModelRetry(f"calculation {calculation_id!r} not found")
        data = {
            **_calc_summary(c),
            "campaign_id": c.campaign_id,
            "input_parameters": {k: v for k, v in (c.input_parameters or {}).items() if k != "features"},
            "output": c.output,
            "provenance": c.provenance,
            "failure_metadata": c.failure_metadata,
            "changed_parameters": c.changed_parameters,
            "reason_for_change": c.reason_for_change,
            "started_at": c.started_at,
            "completed_at": c.completed_at,
        }
        if c.stdout_artifact and Path(c.stdout_artifact).is_file():
            lines = Path(c.stdout_artifact).read_text(errors="replace").splitlines()
            data["log_tail"] = "\n".join(lines[-LOG_TAIL_LINES:])
        return _dump(data)

    @tools.tool
    async def list_decisions(ctx: RunContext[CopilotDeps], campaign_id: str, limit: int = 40) -> str:
        """The agent's decision trail for a campaign: hypotheses, evidence, actions, model
        updates, failures, and the final recommendation (oldest first)."""
        await _campaign(ctx, campaign_id)
        rows = (
            await ctx.deps.session.execute(
                select(AgentEvent)
                .where(AgentEvent.campaign_id == campaign_id)
                .where(
                    AgentEvent.event_type.in_(
                        ["AGENT_DECISION", "MODEL_UPDATED", "JOB_FAILED", "FINAL_RECOMMENDATION",
                         "CAMPAIGN_COMPLETED", "CAMPAIGN_ERROR", "USER_NOTE"]
                    )
                )
                .order_by(AgentEvent.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return _dump(
            [
                {
                    "at": e.created_at,
                    "type": e.event_type,
                    "hypothesis": e.hypothesis,
                    "evidence": e.reasoning_summary,
                    "action": e.action,
                    "payload": e.payload,
                }
                for e in reversed(rows)
            ]
        )

    @tools.tool
    def list_elements(ctx: RunContext[CopilotDeps]) -> str:
        """The element catalog: symbol, ambient structure, FCC lattice constant, and which
        engines support it (EMT is limited to Al, Cu, Ag, Au, Ni, Pd, Pt)."""
        from alloyscience.calculators import element_catalog

        return _dump(
            [
                {
                    "symbol": e.symbol,
                    "name": e.name,
                    "structure": e.structure,
                    "fcc_native": e.fcc_native,
                    "a_fcc": round(e.a_fcc, 3),
                    "emt": e.emt,
                }
                for e in element_catalog()
            ]
        )

    # ----------------------------------------------------------------- hands

    @tools.tool
    async def propose_campaign_params(
        ctx: RunContext[CopilotDeps], patch: CampaignParamsPatch, rationale: str
    ) -> str:
        """Fill or change fields of the new-campaign form. Only valid on the new-campaign
        page. Set only the fields to change; the scientist sees them highlighted with your
        rationale and decides whether to create the campaign."""
        if ctx.deps.context.page != "new_campaign":
            raise ModelRetry(
                "the scientist is not on the new-campaign form; ask them to open it "
                "(Campaigns -> New campaign) before proposing parameters"
            )
        changes = patch.model_dump(exclude_none=True, mode="json")
        if not changes:
            raise ModelRetry("patch is empty: set at least one field")
        if changes.get("problem_type") in SYNTHETIC_PROBLEMS:
            raise ModelRetry(
                f"{changes['problem_type']} is a synthetic benchmark problem, not a campaign; "
                "campaigns use dft_v3, property_v3 (emt/espresso), or ising_v0"
            )
        if changes.get("property_engine") == "hidden":
            raise ModelRetry("the hidden property engine is benchmark-only; use emt or espresso")
        if "element_a" in changes or "element_b" in changes:
            from alloyscience.calculators import CATALOG_SYMBOLS

            for key in ("element_a", "element_b"):
                if key in changes:
                    changes[key] = changes[key].strip().capitalize()
                    if changes[key] not in CATALOG_SYMBOLS:
                        raise ModelRetry(f"{changes[key]!r} is not in the element catalog")
        merged = {**(ctx.deps.context.form or {}), **changes}
        if merged.get("element_a") and merged.get("element_a") == merged.get("element_b"):
            raise ModelRetry("element_a and element_b must differ")
        ctx.deps.patches.append({"patch": changes, "rationale": rationale})
        return _dump({"applied": changes, "form": merged, "note": "The scientist must press Create."})

    return agent


# --------------------------------------------------------------------------- streaming


async def stream_reply(
    agent: Agent[CopilotDeps, str],
    prompt: str,
    history: list[ModelMessage],
    deps: CopilotDeps,
) -> AsyncIterator[dict]:
    """Run the agent and yield UI events; the last event is ``done`` with the new
    messages of this run (append them to the stored history)."""
    text_index: int | None = None
    async with agent.run_stream_events(prompt, message_history=history, deps=deps) as events:
        async for event in events:
            if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
                text_index = event.index
                if event.part.content:
                    yield {"type": "text", "delta": event.part.content}
            elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                if event.index == text_index or text_index is None:
                    yield {"type": "text", "delta": event.delta.content_delta}
            elif isinstance(event, FunctionToolCallEvent):
                part = event.part
                try:
                    args = part.args_as_dict()
                except Exception:
                    args = {"raw": part.args}
                yield {"type": "tool_call", "id": part.tool_call_id, "name": part.tool_name, "args": args}
            elif isinstance(event, FunctionToolResultEvent):
                part = event.part
                ok = isinstance(part, ToolReturnPart)
                yield {"type": "tool_result", "id": part.tool_call_id, "name": part.tool_name, "ok": ok}
                if ok and part.tool_name == "propose_campaign_params" and deps.patches:
                    yield {"type": "patch", **deps.patches[-1]}
        result = events.result
    usage = result.usage() if callable(result.usage) else result.usage
    yield {
        "type": "done",
        "new_messages": result.new_messages(),
        "total_tokens": getattr(usage, "total_tokens", None),
        "trace_id": _current_trace_id(),
    }


def _current_trace_id() -> str | None:
    """Trace id of the surrounding span when tracing is enabled (Arize/OTel)."""
    try:
        from opentelemetry import trace

        ctx = trace.get_current_span().get_span_context()
        return format(ctx.trace_id, "032x") if ctx.is_valid else None
    except Exception:
        return None
