"""Sidebar copilot: chats, streaming replies, eyes-tools over real campaign
data, the form-patch hands-tool, and DB-backed agent definitions (tool sets,
skill sets) — driven by Pydantic AI's FunctionModel so no provider key is
needed and tool calls are deterministic."""

from __future__ import annotations

import asyncio
import json

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from sqlalchemy import select

import gibbs.api.copilot as copilot_api
from gibbs.copilot import CopilotContext, CopilotDeps, build_copilot_agent
from gibbs.copilot.agent import INSTRUCTIONS
from gibbs.copilot.registry import load_agent_definition
from gibbs.copilot.transcript import history_from_rows, split_new_messages, transcript_from_rows
from gibbs.db.base import get_session_factory
from gibbs.db.models import (
    AgentConfigRow,
    AgentRow,
    AgentSkillSet,
    AgentToolSet,
    CopilotMessage,
    CopilotToolCall,
    MessageSkill,
    SkillSet,
    SkillSetSkill,
    ToolSet,
    ToolSetTool,
)


def _scripted(steps):
    """A FunctionModel that replays `steps` (a list of parts per response) for
    both plain and streamed requests."""
    calls = {"n": 0}

    def _next():
        i = min(calls["n"], len(steps) - 1)
        calls["n"] += 1
        return list(steps[i])

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=_next())

    async def stream_fn(messages: list[ModelMessage], info: AgentInfo):
        for i, part in enumerate(_next()):
            if isinstance(part, TextPart):
                yield part.content[:8]  # two chunks so the delta path is exercised
                yield part.content[8:]
            else:
                yield {
                    i: DeltaToolCall(
                        name=part.tool_name, json_args=json.dumps(part.args), tool_call_id=part.tool_call_id
                    )
                }

    return FunctionModel(fn, stream_function=stream_fn)


def _parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        name, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        if name and data:
            events.append({"event": name, **json.loads(data)})
    return events


@pytest.fixture
def scripted_agent(monkeypatch):
    """Route the router's agent construction through a scripted (or given) model."""

    def install(steps=None, model=None):
        model = model or _scripted(steps)
        monkeypatch.setattr(
            copilot_api, "build_copilot_agent", lambda _m, d=None: build_copilot_agent(model, d)
        )
        monkeypatch.setenv("ALLOYLAB_AGENT_MODEL", "test")  # passes the availability check
        from gibbs.config import get_settings

        get_settings.cache_clear()

    return install


async def _finished_campaign(client) -> str:
    r = await client.post(
        "/campaigns",
        json={"name": "ising", "strategy": "grid", "simulation_budget": 4, "lattice_size": 8},
    )
    cid = r.json()["id"]
    await client.post(f"/campaigns/{cid}/start")
    for _ in range(600):
        c = (await client.get(f"/campaigns/{cid}")).json()
        if c["status"] in ("COMPLETED", "FAILED"):
            break
        await asyncio.sleep(0.05)
    assert c["status"] == "COMPLETED", c
    return cid


async def _send(client, chat_id: str, content: str, context: dict | None = None) -> list[dict]:
    r = await client.post(
        f"/copilot/chats/{chat_id}/messages",
        json={"content": content, "context": context or {"page": "other"}},
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    return _parse_sse(r.text)


async def _rows(chat_id: str) -> list[CopilotMessage]:
    from sqlalchemy.orm import selectinload

    async with get_session_factory()() as session:
        rows = (
            await session.execute(
                select(CopilotMessage)
                .where(CopilotMessage.chat_id == chat_id)
                .options(selectinload(CopilotMessage.tool_calls), selectinload(CopilotMessage.skills))
                .order_by(CopilotMessage.id)
            )
        ).scalars().all()
        return list(rows)


async def test_status_and_chat_crud(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ALLOYLAB_AGENT_MODEL", "openai:gpt-5")
    from gibbs.config import get_settings

    get_settings.cache_clear()
    r = await client.get("/copilot/status")
    assert r.status_code == 200 and r.json()["available"] is False

    r = await client.post("/copilot/chats", json={})
    assert r.status_code == 201, r.text
    chat = r.json()
    assert chat["transcript"] == [] and chat["title"] == "New chat"
    assert len(chat["id"]) == 36 and chat["id"].count("-") == 4  # a uuid

    r = await client.get("/copilot/chats")
    assert [c["id"] for c in r.json()] == [chat["id"]]

    # Without a usable model the reply endpoint refuses clearly.
    r = await client.post(f"/copilot/chats/{chat['id']}/messages", json={"content": "hi"})
    assert r.status_code == 503

    r = await client.delete(f"/copilot/chats/{chat['id']}")
    assert r.status_code == 204
    assert (await client.get(f"/copilot/chats/{chat['id']}")).status_code == 404


async def test_reply_streams_tool_calls_and_persists_rows(client, scripted_agent):
    cid = await _finished_campaign(client)
    calc_id = (await client.get(f"/campaigns/{cid}/calculations")).json()[0]["id"]

    scripted_agent(
        [
            [ToolCallPart(tool_name="get_campaign", args={"campaign_id": cid}, tool_call_id="t1")],
            [ToolCallPart(tool_name="list_calculations", args={"campaign_id": cid}, tool_call_id="t2")],
            [TextPart(content=f"The campaign finished; first run [calc:{calc_id}] succeeded.")],
        ]
    )
    chat_id = (await client.post("/copilot/chats", json={})).json()["id"]
    events = await _send(client, chat_id, "How did it go?", {"page": "campaign", "campaign_id": cid})
    kinds = [e["event"] for e in events]
    assert kinds.count("tool_call") == 2 and kinds.count("tool_result") == 2
    assert [e["name"] for e in events if e["event"] == "tool_call"] == ["get_campaign", "list_calculations"]
    assert all(e["ok"] for e in events if e["event"] == "tool_result")
    assert "".join(e["delta"] for e in events if e["event"] == "text").startswith("The campaign finished")
    done = events[-1]
    assert done["event"] == "done"
    transcript = done["transcript"]
    assert transcript[0] == {"role": "user", "text": "How did it go?"}
    tool_parts = [p for p in transcript[1]["parts"] if p["type"] == "tool"]
    assert tool_parts[0]["name"] == "get_campaign" and tool_parts[0]["result"]["id"] == cid
    assert tool_parts[1]["result"][0]["id"]  # calculations came back as parsed JSON
    assert transcript[1]["parts"][-1]["type"] == "text"

    # Persisted relationally: user row, assistant row, two tool_call rows; title set.
    rows = await _rows(chat_id)
    assert [r.role for r in rows] == ["user", "assistant"]
    assert rows[0].page_context["campaign_id"] == cid
    calls = rows[1].tool_calls
    assert [(c.name, c.status, c.position) for c in calls] == [
        ("get_campaign", "ok", 0),
        ("list_calculations", "ok", 1),
    ]
    assert json.loads(calls[0].arguments) == {"campaign_id": cid}
    assert json.loads(calls[0].output)["id"] == cid
    r = await client.get(f"/copilot/chats/{chat_id}")
    assert r.json()["transcript"] == transcript
    assert r.json()["title"] == "How did it go?"

    # The second turn's model sees the first turn rebuilt from rows.
    seen: dict = {}

    def capture(messages, info):
        return ModelResponse(parts=[TextPart(content="ok")])

    async def capture_stream(messages, info):
        seen["messages"] = messages
        yield "ok"

    scripted_agent(model=FunctionModel(capture, stream_function=capture_stream))
    await _send(client, chat_id, "and then?")
    kinds = [m.kind for m in seen["messages"]]
    # user prompt, tool-call response, tool returns, text response, new prompt
    assert kinds == ["request", "response", "request", "response", "request"]
    assert "How did it go?" in str(seen["messages"][0])


async def test_failed_reply_leaves_no_dangling_question(client, scripted_agent):
    def boom(messages, info):
        raise RuntimeError("provider down")

    async def boom_stream(messages, info):
        raise RuntimeError("provider down")
        yield  # pragma: no cover

    chat_id = (await client.post("/copilot/chats", json={})).json()["id"]
    scripted_agent(model=FunctionModel(boom, stream_function=boom_stream))
    events = await _send(client, chat_id, "hello?")
    assert events[-1]["event"] == "error" and "provider down" in events[-1]["detail"]
    assert (await client.get(f"/copilot/chats/{chat_id}")).json()["transcript"] == []


async def test_propose_params_only_on_form_page(client, scripted_agent):
    scripted_agent(
        [
            [
                ToolCallPart(
                    tool_name="propose_campaign_params",
                    args={
                        "patch": {
                            "problem_type": "phase_v2",
                            "element_a": "cu",
                            "element_b": "Au",
                            "phase_t_min": 300,
                            "phase_t_max": 900,
                        },
                        "rationale": "CuAu disorders near 683 K; bracket it.",
                    },
                    tool_call_id="p1",
                )
            ],
            [TextPart(content="Set up a Cu–Au phase-diagram campaign; press Create when ready.")],
        ]
    )
    chat_id = (await client.post("/copilot/chats", json={})).json()["id"]
    events = await _send(
        client,
        chat_id,
        "set up a Cu-Au order/disorder campaign",
        {"page": "new_campaign", "form": {"name": "x", "element_a": "Ni", "element_b": "Al"}},
    )
    patches = [e for e in events if e["event"] == "patch"]
    assert len(patches) == 1
    assert patches[0]["patch"] == {
        "problem_type": "phase_v2",
        "element_a": "Cu",  # normalised
        "element_b": "Au",
        "phase_t_min": 300.0,
        "phase_t_max": 900.0,
    }
    # The proposal is stored as the assistant message's component payload.
    parts = events[-1]["transcript"][1]["parts"]
    patch_part = next(p for p in parts if p["type"] == "patch")
    assert "683" in patch_part["rationale"]
    rows = await _rows(chat_id)
    assert rows[1].component_type == "form_patch" and rows[1].component_data["patch"]["element_a"] == "Cu"

    # Off the form page the tool refuses (a retry prompt, not a crash) and the
    # scripted model falls through to its text answer.
    scripted_agent(
        [
            [
                ToolCallPart(
                    tool_name="propose_campaign_params",
                    args={"patch": {"problem_type": "phase_v2"}, "rationale": "r"},
                    tool_call_id="p2",
                )
            ],
            [TextPart(content="Open the new-campaign form first.")],
        ]
    )
    chat2 = (await client.post("/copilot/chats", json={})).json()["id"]
    events = await _send(client, chat2, "same", {"page": "other"})
    assert not [e for e in events if e["event"] == "patch"]
    result = next(e for e in events if e["event"] == "tool_result")
    assert result["ok"] is False
    assert events[-1]["event"] == "done"


async def test_tools_refuse_unknown_ids(client):
    """Eyes-tools raise a retry on bad ids so the model gets a retry prompt, not a crash."""
    async with get_session_factory()() as session:
        deps = CopilotDeps(session=session, user_id="u", context=CopilotContext())
        model = _scripted(
            [
                [ToolCallPart(tool_name="get_hull", args={"campaign_id": "missing"}, tool_call_id="h")],
                [TextPart(content="No such campaign.")],
            ]
        )
        result = await build_copilot_agent(model).run("hull?", deps=deps)
        assert result.output == "No such campaign."
        text, calls = split_new_messages(result.new_messages())
        assert text == "No such campaign."
        assert calls[0]["status"] == "error" and "not found" in calls[0]["output"]


async def _seed_definition(*, tools: list[str], skills: list[tuple[str, str, str]]):
    async with get_session_factory()() as session:
        session.add(AgentConfigRow(id=1, max_output_tokens=2048, temperature=20))
        session.add(AgentRow(id=1, name="copilot", system_prompt="", agent_config_id=1))
        session.add(ToolSet(id=1, name="core"))
        for name in tools:
            session.add(ToolSetTool(tool_set_id=1, tool_name=name))
        session.add(AgentToolSet(agent_id=1, tool_set_id=1))
        session.add(SkillSet(id=1, name="ms"))
        for name, desc, content in skills:
            session.add(SkillSetSkill(skill_set_id=1, skill_name=name, description=desc, content=content))
        session.add(AgentSkillSet(agent_id=1, skill_set_id=1))
        await session.commit()


async def test_definition_tool_sets_and_skills(client, scripted_agent):
    await _seed_definition(
        tools=["list_campaigns", "list_elements"],
        skills=[("cu-au", "Cu-Au setup", "# Cu-Au\nBracket 663-683 K.")],
    )
    async with get_session_factory()() as session:
        definition = await load_agent_definition(session, "copilot", INSTRUCTIONS)
    assert definition.enabled_tools == frozenset({"list_campaigns", "list_elements"})
    assert [s.name for s in definition.skills] == ["cu-au"]
    assert definition.instructions == INSTRUCTIONS  # empty system_prompt -> code default
    assert definition.model_settings() == {"max_tokens": 2048, "temperature": 0.2}

    # The model sees only the enabled tools plus load_skill, and the skill list.
    seen: dict = {}
    turns = {"n": 0}

    async def stream_fn(messages, info):
        turns["n"] += 1
        if turns["n"] == 1:
            seen["tools"] = sorted(t.name for t in info.function_tools)
            seen["instructions"] = info.instructions or ""
            yield {
                0: DeltaToolCall(
                    name="load_skill", json_args=json.dumps({"skill_name": "cu-au"}), tool_call_id="s1"
                )
            }
        else:
            yield "Loaded the Cu-Au skill."

    def fn(messages, info):
        return ModelResponse(parts=[TextPart(content="unused")])

    scripted_agent(model=FunctionModel(fn, stream_function=stream_fn))
    chat_id = (await client.post("/copilot/chats", json={})).json()["id"]
    events = await _send(client, chat_id, "set up Cu-Au")
    assert seen["tools"] == ["list_campaigns", "list_elements", "load_skill"]
    assert "cu-au: Cu-Au setup" in seen["instructions"]
    load = next(e for e in events if e["event"] == "tool_call")
    assert load["name"] == "load_skill"
    assert events[-1]["event"] == "done"

    # The loaded skill is recorded on the assistant message, and its content
    # lives in the tool_call row so history reconstruction re-injects it.
    rows = await _rows(chat_id)
    assert [(s.skill_set_id, s.skill_name) for s in rows[1].skills] == [(1, "cu-au")]
    async with get_session_factory()() as session:
        assert len((await session.execute(select(MessageSkill))).scalars().all()) == 1
    history = history_from_rows(rows)
    assert any("Bracket 663-683 K" in str(m) for m in history)
    transcript = transcript_from_rows(rows)
    assert transcript[1]["parts"][0]["name"] == "load_skill"
