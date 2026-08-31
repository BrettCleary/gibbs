"""DB-backed agent definitions: system prompt, model, tool sets, skill sets.

`load_agent_definition(session, "copilot")` resolves the copilot's row and its
composition. When the tables are empty (fresh SQLite dev DB, tests) the
in-code default — the built-in instructions with every tool and no skills —
is returned, so nothing depends on seed data to run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import (
    AgentConfigRow,
    AgentRow,
    AgentSkillSet,
    AgentToolSet,
    SkillSetSkill,
    ToolSetTool,
)

COPILOT_AGENT_NAME = "copilot"


@dataclass(frozen=True)
class SkillRef:
    skill_set_id: int
    name: str
    description: str | None


@dataclass
class AgentDefinition:
    name: str
    instructions: str
    # Provider-prefixed Pydantic AI model string; None = settings.agent_model.
    model: str | None = None
    # None = every tool registered in code; otherwise the allowed tool names.
    enabled_tools: frozenset[str] | None = None
    skills: list[SkillRef] = field(default_factory=list)
    agent_id: int | None = None
    max_output_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    # Provider-specific Pydantic AI model settings from agent_config.provider_options,
    # e.g. {"openai_reasoning_effort": "high"}. Merged last, so a config row can reach
    # any setting its provider's ModelSettings supports.
    provider_options: dict = field(default_factory=dict)

    def model_settings(self) -> dict | None:
        settings: dict = {}
        if self.max_output_tokens:
            settings["max_tokens"] = self.max_output_tokens
        if self.temperature is not None:
            settings["temperature"] = self.temperature
        if self.top_p is not None:
            settings["top_p"] = self.top_p
        settings.update(self.provider_options)
        return settings or None


def default_definition(instructions: str) -> AgentDefinition:
    return AgentDefinition(name=COPILOT_AGENT_NAME, instructions=instructions)


async def load_agent_definition(
    session: AsyncSession, name: str, fallback_instructions: str
) -> AgentDefinition:
    row = (
        await session.execute(select(AgentRow).where(AgentRow.name == name))
    ).scalar_one_or_none()
    if row is None:
        return default_definition(fallback_instructions)
    config = await session.get(AgentConfigRow, row.agent_config_id)

    tools: frozenset[str] | None = None
    if not row.enable_all_tools:
        names = (
            await session.execute(
                select(ToolSetTool.tool_name)
                .join(AgentToolSet, AgentToolSet.tool_set_id == ToolSetTool.tool_set_id)
                .where(AgentToolSet.agent_id == row.id)
            )
        ).scalars().all()
        tools = frozenset(names)

    skill_rows = (
        await session.execute(
            select(SkillSetSkill.skill_set_id, SkillSetSkill.skill_name, SkillSetSkill.description)
            .join(AgentSkillSet, AgentSkillSet.skill_set_id == SkillSetSkill.skill_set_id)
            .where(AgentSkillSet.agent_id == row.id)
            .order_by(SkillSetSkill.skill_set_id, SkillSetSkill.skill_name)
        )
    ).all()

    return AgentDefinition(
        name=row.name,
        instructions=row.system_prompt or fallback_instructions,
        model=row.foundation_model or None,
        enabled_tools=tools,
        skills=[SkillRef(skill_set_id=s, name=n, description=d) for s, n, d in skill_rows],
        agent_id=row.id,
        max_output_tokens=config.max_output_tokens if config else None,
        temperature=(config.temperature / 100) if config and config.temperature is not None else None,
        top_p=(config.top_p / 100) if config and config.top_p is not None else None,
        provider_options=dict(config.provider_options or {}) if config else {},
    )


async def skill_content(
    session: AsyncSession, definition: AgentDefinition, skill_name: str
) -> tuple[SkillRef, str] | None:
    """Full content of a skill, scoped to the agent's skill sets."""
    ref = next((s for s in definition.skills if s.name == skill_name), None)
    if ref is None:
        return None
    row = await session.get(SkillSetSkill, (ref.skill_set_id, ref.name))
    if row is None:
        return None
    return ref, row.content
