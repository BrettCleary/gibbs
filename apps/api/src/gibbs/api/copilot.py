"""Sidebar copilot endpoints: chats (persisted conversations) and a streaming
reply. The reply is Server-Sent Events over POST (the browser reads it with
fetch + ReadableStream; EventSource cannot POST)."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from ..agent.llm import model_available
from ..config import get_settings
from ..copilot import CopilotContext, CopilotDeps, build_copilot_agent, stream_reply
from ..copilot.agent import INSTRUCTIONS
from ..copilot.registry import COPILOT_AGENT_NAME, load_agent_definition
from ..copilot.transcript import (
    FORM_PATCH,
    history_from_rows,
    split_new_messages,
    transcript_from_rows,
)
from ..db.base import get_session_factory
from ..db.models import AuthUser, CopilotChat, CopilotMessage, CopilotToolCall, MessageSkill
from ..schemas import (
    CopilotChatCreate,
    CopilotChatRead,
    CopilotChatSummary,
    CopilotMessageCreate,
    CopilotStatus,
)
from .auth import require_user
from .deps import get_session

logger = logging.getLogger("gibbs.copilot")
router = APIRouter(prefix="/copilot", tags=["copilot"])


async def _messages(session: AsyncSession, chat_id: str) -> list[CopilotMessage]:
    rows = await session.execute(
        select(CopilotMessage)
        .where(CopilotMessage.chat_id == chat_id)
        .options(selectinload(CopilotMessage.tool_calls))
        .order_by(CopilotMessage.created_at, CopilotMessage.id)
    )
    return list(rows.scalars().all())


async def _read(session: AsyncSession, chat: CopilotChat) -> CopilotChatRead:
    return CopilotChatRead(
        id=str(chat.id),
        title=chat.title,
        transcript=transcript_from_rows(await _messages(session, chat.id)),
        created_at=chat.created_at,
        updated_at=chat.updated_at,
    )


async def _owned_chat(session: AsyncSession, chat_id: str, user: AuthUser) -> CopilotChat:
    chat = await session.get(CopilotChat, chat_id)
    if chat is None or chat.user_id != user.id:
        raise HTTPException(status_code=404, detail="chat not found")
    return chat


@router.get("/status", response_model=CopilotStatus)
async def copilot_status():
    """Whether the copilot can answer (its model's provider key is configured)."""
    model = get_settings().agent_model
    ok, reason = model_available(model)
    return CopilotStatus(available=ok, model=model, reason=reason)


@router.get("/chats", response_model=list[CopilotChatSummary])
async def list_chats(
    session: AsyncSession = Depends(get_session),
    user: AuthUser = Depends(require_user),
):
    """The user's chats, most recently active first."""
    rows = await session.execute(
        select(CopilotChat)
        .where(CopilotChat.user_id == user.id)
        .order_by(CopilotChat.updated_at.desc())
        .limit(50)
    )
    return [
        CopilotChatSummary(id=str(c.id), title=c.title, created_at=c.created_at, updated_at=c.updated_at)
        for c in rows.scalars().all()
    ]


@router.post("/chats", response_model=CopilotChatRead, status_code=201)
async def create_chat(
    body: CopilotChatCreate,
    session: AsyncSession = Depends(get_session),
    user: AuthUser = Depends(require_user),
):
    chat = CopilotChat(user_id=user.id, title=body.title or "New chat")
    session.add(chat)
    await session.commit()
    await session.refresh(chat)
    return await _read(session, chat)


@router.get("/chats/{chat_id}", response_model=CopilotChatRead)
async def get_chat(
    chat_id: str,
    session: AsyncSession = Depends(get_session),
    user: AuthUser = Depends(require_user),
):
    return await _read(session, await _owned_chat(session, chat_id, user))


@router.delete("/chats/{chat_id}", status_code=204)
async def delete_chat(
    chat_id: str,
    session: AsyncSession = Depends(get_session),
    user: AuthUser = Depends(require_user),
):
    chat = await _owned_chat(session, chat_id, user)
    await session.delete(chat)
    await session.commit()


@router.post("/chats/{chat_id}/messages")
async def send_message(
    chat_id: str,
    body: CopilotMessageCreate,
    session: AsyncSession = Depends(get_session),
    user: AuthUser = Depends(require_user),
):
    """Send a message and stream the copilot's reply as SSE events:
    `text` {delta}, `tool_call` {id,name,args}, `tool_result` {id,name,ok},
    `patch` {patch,rationale} (a form proposal), `done` {transcript}, `error` {detail}.

    The user row is written first; the assistant row and its tool calls are
    written when the run completes, so a failed run leaves only the question.
    """
    chat = await _owned_chat(session, chat_id, user)
    settings = get_settings()
    definition = await load_agent_definition(session, COPILOT_AGENT_NAME, INSTRUCTIONS)
    model = definition.model or settings.agent_model
    ok, reason = model_available(model)
    if not ok:
        raise HTTPException(status_code=503, detail=f"copilot unavailable: {reason}")
    context = CopilotContext(
        page=body.context.page if body.context.page in ("new_campaign", "campaign", "other") else "other",
        campaign_id=body.context.campaign_id,
        form=body.context.form,
    )
    history = history_from_rows(await _messages(session, chat.id))
    user_row = CopilotMessage(
        chat_id=chat.id,
        role="user",
        message=body.content,
        page_context=body.context.model_dump(mode="json"),
    )
    session.add(user_row)
    if chat.title == "New chat":
        chat.title = body.content.strip().splitlines()[0][:100]
    await session.commit()
    user_row_id = user_row.id
    prompt = body.content
    agent = build_copilot_agent(model, definition)

    async def generator():
        # The request-scoped session may be closed before a streaming response
        # finishes; run the reply on its own session.
        async with get_session_factory()() as run_session:
            deps = CopilotDeps(
                session=run_session, user_id=user.id, context=context, definition=definition
            )
            try:
                async for event in stream_reply(agent, prompt, history, deps):
                    if event["type"] != "done":
                        yield {"event": event["type"], "data": json.dumps(event, default=str)}
                        continue
                    text, calls = split_new_messages(event["new_messages"])
                    patch = deps.patches[-1] if deps.patches else None
                    assistant = CopilotMessage(
                        chat_id=chat_id,
                        role="assistant",
                        message=text,
                        total_tokens=event.get("total_tokens") or 0,
                        trace_id=event.get("trace_id"),
                        component_type=FORM_PATCH if patch else None,
                        component_data=patch,
                        tool_calls=[CopilotToolCall(**c) for c in calls],
                        skills=[
                            MessageSkill(skill_set_id=ref.skill_set_id, skill_name=ref.name)
                            for ref in deps.loaded_skills
                        ],
                    )
                    run_session.add(assistant)
                    stored_chat = await run_session.get(CopilotChat, chat_id)
                    stored_chat.updated_at = assistant.created_at or stored_chat.updated_at
                    await run_session.commit()
                    payload = {
                        "type": "done",
                        "transcript": transcript_from_rows(await _messages(run_session, chat_id)),
                    }
                    yield {"event": "done", "data": json.dumps(payload, default=str)}
            except Exception as exc:  # surface provider/tool errors to the sidebar
                logger.exception("copilot reply failed")
                # The question stays in the timeline without an answer; remove it so
                # the scientist can resend without a dangling turn in the history.
                row = await run_session.get(CopilotMessage, user_row_id)
                if row is not None:
                    await run_session.delete(row)
                    await run_session.commit()
                yield {"event": "error", "data": json.dumps({"type": "error", "detail": str(exc)})}

    return EventSourceResponse(generator())
