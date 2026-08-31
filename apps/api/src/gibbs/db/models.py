from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, ForeignKeyConstraint, Integer, String, Text, Uuid
from sqlalchemy import JSON as _JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

# The schema of record is the Drizzle definition in apps/web/db/schema (jsonb
# on Postgres, tables in the science / agent / benchmarks schemas). These models
# mirror it for the Python query layer; SQLite (tests / zero-config dev) gets
# plain JSON and has the schemas translated away (see base.py).
JSON = JSONB().with_variant(_JSON(), "sqlite")


def _uuid() -> str:
    return uuid.uuid4().hex


def _uuid_str() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Campaign(Base):
    """A discovery campaign. V0: locate the Ising critical region."""

    __tablename__ = "campaigns"
    __table_args__ = {"schema": "science"}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    # Owner. Nullable only because campaigns predate ownership: rows written
    # before the column existed have no owner and are visible to nobody.
    user_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("app_auth.user.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    objective: Mapped[str] = mapped_column(Text)
    problem_type: Mapped[str] = mapped_column(String(50), default="ising_v0")
    strategy: Mapped[str] = mapped_column(String(50), default="agent")

    # Search space (V0: temperature only; composition reserved for V1+).
    temperature_min: Mapped[float] = mapped_column(Float, default=1.5)
    temperature_max: Mapped[float] = mapped_column(Float, default=3.5)
    composition_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    composition_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    elements: Mapped[list] = mapped_column(JSON, default=list)

    lattice_size: Mapped[int] = mapped_column(Integer, default=24)
    simulation_budget: Mapped[int] = mapped_column(Integer, default=20)
    simulations_used: Mapped[int] = mapped_column(Integer, default=0)
    target_uncertainty: Mapped[float | None] = mapped_column(Float, nullable=True)
    failure_rate: Mapped[float] = mapped_column(Float, default=0.0)

    status: Mapped[str] = mapped_column(String(30), default="CREATED")
    stopping_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Hidden problem definition (e.g. the secret alloy Hamiltonian). Never
    # exposed through the API or to the agent; used only by the executor and
    # by benchmark ground-truth evaluation.
    problem_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Final scientific report (Milestone 9), persisted at campaign completion.
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    @property
    def engine(self) -> str | None:
        """Energy engine: "emt" | "espresso" for real campaigns, "hidden" for
        synthetic ground truth, "ising" for the real Ising MC, None otherwise."""
        cfg = self.problem_config or {}
        if self.problem_type == "ising_v0":
            return "ising"
        engine = cfg.get("engine") or cfg.get("dft_engine") or cfg.get("property_engine")
        if engine:
            return engine
        if self.problem_type in ("alloy_v1", "fcc_v2", "phase_v2", "property_v3"):
            return "hidden"
        return None

    @property
    def synthetic(self) -> bool:
        """True when the ground truth is a hidden model — a benchmark, not a simulation."""
        return self.engine == "hidden"


class Structure(Base):
    """A candidate atomic configuration (V1: periodic tile on the 2D lattice)."""

    __tablename__ = "structures"
    __table_args__ = {"schema": "science"}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("science.campaigns.id"), index=True)
    label: Mapped[str] = mapped_column(String(50), index=True)
    chemical_formula: Mapped[str] = mapped_column(String(100), default="")
    composition: Mapped[float] = mapped_column(Float)  # x_B
    n_sites: Mapped[int] = mapped_column(Integer)
    occupations: Mapped[list] = mapped_column(JSON, default=list)  # 2D tile problems
    shape: Mapped[list] = mapped_column(JSON, default=list)
    features: Mapped[list] = mapped_column(JSON, default=list)  # CE design row
    # 3D problems (plan's Structure entity): lattice vectors, cartesian
    # positions, atomic numbers.
    lattice: Mapped[list | None] = mapped_column(JSON, nullable=True)
    positions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    atomic_numbers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Calculation(Base):
    """One simulation job (V0: a Monte Carlo run at one temperature)."""

    __tablename__ = "calculations"
    __table_args__ = {"schema": "science"}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("science.campaigns.id"), index=True)
    structure_id: Mapped[str | None] = mapped_column(
        ForeignKey("science.structures.id"), nullable=True, index=True
    )
    calculation_type: Mapped[str] = mapped_column(String(40), default="MONTE_CARLO")
    engine: Mapped[str] = mapped_column(String(100), default="alloyscience.ising.IsingSimulator")
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", index=True)

    input_parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    provenance: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    failure_category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    failure_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retry_of: Mapped[str | None] = mapped_column(ForeignKey("science.calculations.id"), nullable=True)
    changed_parameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason_for_change: Mapped[str | None] = mapped_column(Text, nullable=True)
    # null | "retried" | "abandoned" — how a FAILED calculation was dealt with.
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Engine log artifacts (plan's Calculation entity), e.g. the pw.x .pwo file.
    stdout_artifact: Mapped[str | None] = mapped_column(String(500), nullable=True)
    stderr_artifact: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SurrogateModel(Base):
    """A fitted surrogate (V0: bootstrap response surrogate for chi(T))."""

    __tablename__ = "surrogate_models"
    __table_args__ = {"schema": "science"}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("science.campaigns.id"), index=True)
    type: Mapped[str] = mapped_column(String(50), default="response_surrogate")
    version: Mapped[int] = mapped_column(Integer, default=1)
    training_calculation_ids: Mapped[list] = mapped_column(JSON, default=list)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    artifact: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AgentRun(Base):
    """One autonomous run of the scientist loop over a campaign."""

    __tablename__ = "agent_runs"
    __table_args__ = {"schema": "agent"}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("science.campaigns.id"), index=True)
    model: Mapped[str] = mapped_column(String(100), default="heuristic")
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AgentEvent(Base):
    """Auditable record of every agent decision/action and job lifecycle event."""

    __tablename__ = "agent_events"
    __table_args__ = {"schema": "agent"}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent.agent_runs.id"), nullable=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("science.campaigns.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tool_output_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BenchmarkRun(Base):
    """A stored benchmark comparison of experiment-selection strategies."""

    __tablename__ = "benchmark_runs"
    __table_args__ = {"schema": "benchmarks"}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    results: Mapped[list | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Better Auth tables (apps/web/db/schema/auth.ts) ---------------------------
# Owned and written by the Next.js app; the API only reads them to authenticate
# requests (gibbs/api/auth.py). Columns mirror the Drizzle definition.


class AuthUser(Base):
    __tablename__ = "user"
    __table_args__ = {"schema": "app_auth"}

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text, unique=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    image: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuthSession(Base):
    __tablename__ = "session"
    __table_args__ = {"schema": "app_auth"}

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    token: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ip_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("app_auth.user.id", ondelete="CASCADE"))


class CopilotChat(Base):
    """A copilot chat. Mirrors apps/web/db/schema/copilot.ts (agent.chat)."""

    __tablename__ = "chat"
    __table_args__ = {"schema": "agent"}

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("app_auth.user.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(Text, default="New chat")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    messages: Mapped[list["CopilotMessage"]] = relationship(
        back_populates="chat", cascade="all, delete-orphan", order_by="CopilotMessage.id"
    )


class CopilotMessage(Base):
    """One timeline entry of a chat: a user prompt or an assistant reply."""

    __tablename__ = "messages"
    __table_args__ = {"schema": "agent"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("agent.chat.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(Text)  # "user" | "assistant"
    message: Mapped[str] = mapped_column(Text, default="")
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    component_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    component_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    chat: Mapped[CopilotChat] = relationship(back_populates="messages")
    tool_calls: Mapped[list["CopilotToolCall"]] = relationship(
        back_populates="message", cascade="all, delete-orphan", order_by="CopilotToolCall.position"
    )
    skills: Mapped[list["MessageSkill"]] = relationship(cascade="all, delete-orphan")


class CopilotToolCall(Base):
    """A tool call the model made while producing an assistant message."""

    __tablename__ = "tool_call"
    __table_args__ = {"schema": "agent"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent.messages.id", ondelete="CASCADE"), index=True
    )
    call_id: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    arguments: Mapped[str] = mapped_column(Text, default="{}")
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="pending")  # ok | error | pending
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    message: Mapped[CopilotMessage] = relationship(back_populates="tool_calls")


# ----------------------------------------------------------- agent configuration
# Mirrors apps/web/db/schema/agent-config.ts: an agent row is composed from
# tool sets and skill sets; message_skill records which skills a reply loaded.


class AgentConfigRow(Base):
    __tablename__ = "agent_config"
    __table_args__ = {"schema": "agent"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    temperature: Mapped[int | None] = mapped_column(Integer, nullable=True)  # x100
    top_p: Mapped[int | None] = mapped_column(Integer, nullable=True)  # x100
    provider_options: Mapped[dict] = mapped_column(JSON, default=dict)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class AgentRow(Base):
    __tablename__ = "agent"
    __table_args__ = {"schema": "agent"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    system_prompt: Mapped[str] = mapped_column(Text)
    foundation_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    enable_all_tools: Mapped[bool] = mapped_column(Boolean, default=False)
    agent_config_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent.agent_config.id"))
    tag: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    config: Mapped[AgentConfigRow] = relationship()


class ToolSet(Base):
    __tablename__ = "tool_set"
    __table_args__ = {"schema": "agent"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ToolSetTool(Base):
    __tablename__ = "tool_set_tool"
    __table_args__ = {"schema": "agent"}

    tool_set_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent.tool_set.id", ondelete="CASCADE"), primary_key=True
    )
    tool_name: Mapped[str] = mapped_column(Text, primary_key=True, index=True)


class AgentToolSet(Base):
    __tablename__ = "agent_tool_set"
    __table_args__ = {"schema": "agent"}

    agent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent.agent.id", ondelete="CASCADE"), primary_key=True
    )
    tool_set_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent.tool_set.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SkillSet(Base):
    __tablename__ = "skill_set"
    __table_args__ = {"schema": "agent"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class SkillSetSkill(Base):
    __tablename__ = "skill_set_skill"
    __table_args__ = {"schema": "agent"}

    skill_set_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent.skill_set.id", ondelete="CASCADE"), primary_key=True
    )
    skill_name: Mapped[str] = mapped_column(Text, primary_key=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text)


class AgentSkillSet(Base):
    __tablename__ = "agent_skill_set"
    __table_args__ = {"schema": "agent"}

    agent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent.agent.id", ondelete="CASCADE"), primary_key=True
    )
    skill_set_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent.skill_set.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MessageSkill(Base):
    """Which skills an assistant message loaded (for history reconstruction)."""

    __tablename__ = "message_skill"
    __table_args__ = (
        ForeignKeyConstraint(
            ["skill_set_id", "skill_name"],
            ["agent.skill_set_skill.skill_set_id", "agent.skill_set_skill.skill_name"],
            ondelete="CASCADE",
        ),
        {"schema": "agent"},
    )

    message_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent.messages.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    skill_set_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_name: Mapped[str] = mapped_column(Text, primary_key=True)
