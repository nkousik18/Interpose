"""Stage 3 (route resolution): maps a gateway route name to an upstream MCP server.

Locally this reads a YAML file that stands in for what becomes a Kubernetes ConfigMap
once Interpose deploys via Helm (Phase 2). See docs/INTERPOSE_SCOPING.md Section 6.5.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

DEFAULT_CONFIG_PATH = Path("config/upstreams.yaml")


class UpstreamServer(BaseModel):
    url: str


class RoutingTable(BaseModel):
    servers: dict[str, UpstreamServer]

    def resolve(self, server_name: str) -> UpstreamServer | None:
        return self.servers.get(server_name)


def load_routing_table(path: Path | str = DEFAULT_CONFIG_PATH) -> RoutingTable:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    return RoutingTable.model_validate(raw)
