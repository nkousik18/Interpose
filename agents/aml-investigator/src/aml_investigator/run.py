"""Manual/live driver for the investigation agent (docs/ROADMAP.md Day 13's "dry-run
against gateway" test, and the eventual `interpose demo aml --run` per Section 9.10 --
not wired into the Typer CLI yet, a named gap left for Day 15's demo-script work).

Usage (gateway + both MCP servers already running, e.g. via docker-compose or a bare
`uv run` loop):

    python agents/aml-investigator/run_investigation.py [--account-id ID]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

from aml_investigator.gateway_client import InvestigationClient
from aml_investigator.graph import build_graph
from aml_investigator.seed import pick_seed_alert
from aml_investigator.state import Alert, InvestigationState

logger = logging.getLogger(__name__)


async def run_investigation(alert: Alert, gateway_url: str) -> InvestigationState:
    async with InvestigationClient(gateway_url) as client:
        graph = build_graph(client)
        result = await graph.ainvoke(InvestigationState(alert=alert))
        final_state = InvestigationState.model_validate(result)
        logger.info(
            "investigation.complete account_id=%s tool_calls=%d ok=%d failed=%d",
            alert.account_id,
            len(client.call_log),
            sum(1 for c in client.call_log if c.ok),
            sum(1 for c in client.call_log if not c.ok),
        )
        return final_state


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", help="Skip the seed generator, investigate this account.")
    parser.add_argument("--gateway-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    alert = (
        Alert(account_id=args.account_id, alert_type="SUSPICIOUS_WIRE")
        if args.account_id
        else pick_seed_alert()
    )
    print(f"Seed alert: {alert.model_dump_json(indent=2)}")

    final_state = await run_investigation(alert, args.gateway_url)
    print(json.dumps(final_state.model_dump(), indent=2, default=str))


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())


if __name__ == "__main__":
    main()
