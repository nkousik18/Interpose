"""Placeholder terminal nodes for Agents A2 (Anomaly Detector), A3 (Evidence
Composer), and A4 (Incident Escalator) -- docs/INTERPOSE_SCOPING.md Sections 7.8-7.10.
Real implementations land Phase 2 Day 8. The Supervisor's routing *to* these nodes is
real and tested today (docs/ROADMAP.md Day 6/7); what happens once execution arrives
here is not -- each stub just logs that it was reached and ends the graph.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from interpose.control_plane.state import InterposeState

logger = logging.getLogger(__name__)

NodeFn = Callable[[InterposeState], Awaitable[dict]]


def make_stub_node(agent_name: str) -> NodeFn:
    async def node(state: InterposeState) -> dict:
        logger.info(
            "control_plane.stub_agent_invoked agent=%s trace_id=%s audit_id=%d "
            "(not implemented until Phase 2 Day 8)",
            agent_name,
            state.event.trace_id,
            state.event.audit_id,
        )
        return {}

    return node
