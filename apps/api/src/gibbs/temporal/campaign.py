"""Starting a campaign on the worker instead of in the API process.

The workflow id is derived from the campaign id, so Temporal — not an
in-process dict — is the arbiter of whether a campaign is already running. That
dict (`CampaignRunnerRegistry._tasks`) was only ever correct for a single
long-lived API replica, and reported nothing at all when the process that owned
the task went away.
"""

from __future__ import annotations

from ..config import Settings
from .client import connect_temporal_client


def campaign_workflow_id(campaign_id: str) -> str:
    return f"campaign-{campaign_id}"


async def start_campaign_workflow(
    settings: Settings, campaign_id: str, agent_run_id: str
) -> str:
    """Submit the campaign loop to the worker. Raises WorkflowAlreadyStartedError
    if this campaign is already running somewhere."""
    from .workflows import CampaignInput, RunCampaignWorkflow

    client = await connect_temporal_client(settings)
    handle = await client.start_workflow(
        RunCampaignWorkflow.run,
        CampaignInput(
            campaign_id=campaign_id,
            agent_run_id=agent_run_id,
            timeout_seconds=settings.campaign_timeout_seconds,
        ),
        id=campaign_workflow_id(campaign_id),
        task_queue=settings.temporal_task_queue,
    )
    return handle.id
