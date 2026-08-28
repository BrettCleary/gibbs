"""The sidebar copilot: a Pydantic AI agent with *eyes* (read-only tools over
campaigns, hulls, phase diagrams, candidates, calculations, decisions) and
*hands* (proposing campaign parameters on the new-campaign form).

The copilot never starts a campaign and never computes numbers itself: every
quantity it reports comes from a tool call over persisted data, and every
form change it makes is a visible, reversible proposal the scientist submits.
"""

from .agent import (
    CampaignParamsPatch,
    CopilotContext,
    CopilotDeps,
    build_copilot_agent,
    stream_reply,
)
from .transcript import history_from_rows, split_new_messages, transcript_from_rows

__all__ = [
    "CampaignParamsPatch",
    "CopilotContext",
    "CopilotDeps",
    "build_copilot_agent",
    "stream_reply",
    "history_from_rows",
    "split_new_messages",
    "transcript_from_rows",
]
