"""Drives the control plane: consumes DecisionEvents from the EventBus and runs each
one through the compiled graph, in the background, off the gateway's hot path
(docs/INTERPOSE_SCOPING.md Section 7.12).
"""

from __future__ import annotations

import logging

from langgraph.graph.state import CompiledStateGraph

from interpose.control_plane.bus import EventBus
from interpose.control_plane.state import InterposeState

logger = logging.getLogger(__name__)


async def run_forever(bus: EventBus, graph: CompiledStateGraph) -> None:
    async for event in bus.consume():
        try:
            await graph.ainvoke(InterposeState(event=event))
        except Exception:
            # A control-plane failure must never affect the gateway's own decision --
            # it already happened and was audited before this event was even
            # published. Log and keep consuming.
            logger.exception(
                "control_plane.processing_error trace_id=%s audit_id=%d",
                event.trace_id,
                event.audit_id,
            )
