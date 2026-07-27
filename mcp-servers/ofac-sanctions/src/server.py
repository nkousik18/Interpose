"""OFAC sanctions MCP server (docs/INTERPOSE_SCOPING.md Section 9.6, Phase 3 Day
11). Exposes fuzzy-matched OFAC SDN list lookups over streamable-HTTP -- the same
transport Interpose's gateway proxies (concepts/09-mcp-handshake-and-transports.md).
Loads the SDN list + alternate-identities list once at startup (real Treasury API by
default; see config.py), not per-call -- this is a read-mostly reference list that
doesn't change within a demo run.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from loader import SanctionsIndex, best_match, build_index, load_source, top_matches
from mcp.server.fastmcp import Context, FastMCP
from models import SanctionsMatch, SDNEntry

from config import Settings

logger = logging.getLogger(__name__)

VALID_ENTITY_TYPES = {"individual", "entity", "vessel", "aircraft"}


@dataclass
class AppContext:
    index: SanctionsIndex
    match_threshold: float


def _lifespan_for(settings: Settings):
    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
        sdn_text = await load_source(settings.sdn_source)
        alt_text = await load_source(settings.alt_source)
        index = build_index(sdn_text, alt_text)
        alias_count = sum(len(entry.aliases) for entry in index.entries.values())
        logger.info(
            "ofac.loaded entries=%d aliases=%d sdn_source=%s",
            len(index.entries),
            alias_count,
            settings.sdn_source,
        )
        yield AppContext(index=index, match_threshold=settings.match_threshold)

    return lifespan


def _app_context(ctx: Context | None) -> AppContext:
    return ctx.request_context.lifespan_context


def build_server(settings: Settings) -> FastMCP:
    mcp = FastMCP(
        "ofac-sanctions",
        host=settings.host,
        port=settings.port,
        lifespan=_lifespan_for(settings),
    )

    @mcp.tool()
    def check_entity(
        name: str, entity_type: str = "individual", ctx: Context | None = None
    ) -> SanctionsMatch | None:
        """Fuzzy-match `name` against the SDN list, restricted to `entity_type`
        ("individual" | "entity" | "vessel" | "aircraft"). Returns None if nothing
        of that type is in the list at all; otherwise always returns the single
        best match found, with `is_match` reflecting whether its score cleared the
        configured threshold -- a low-confidence match is still informative."""
        if entity_type not in VALID_ENTITY_TYPES:
            raise ValueError(
                f"entity_type must be one of {sorted(VALID_ENTITY_TYPES)}, got {entity_type!r}"
            )
        app = _app_context(ctx)
        names = app.index.names_by_type.get(entity_type, {})
        return best_match(names, app.index, name, app.match_threshold)

    @mcp.tool()
    def check_alias(name: str, ctx: Context | None = None) -> list[SanctionsMatch]:
        """Alias-aware search: matches `name` against every SDN primary name *and*
        every alternate identity (`alt.csv`) -- unlike `check_entity`, which only
        ever searches primary names. Returns the top candidates across any entity
        type, since an alias search is explicitly broader than `check_entity`."""
        app = _app_context(ctx)
        return top_matches(app.index.all_names, app.index, name, app.match_threshold)

    @mcp.tool()
    def get_entity_detail(sdn_entry_id: str, ctx: Context | None = None) -> SDNEntry:
        """Full SDN record (including aliases) for a matched entry ID."""
        app = _app_context(ctx)
        entry = app.index.entries.get(sdn_entry_id)
        if entry is None:
            raise ValueError(f"no SDN entry with ent_num={sdn_entry_id!r}")
        return entry

    return mcp


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_server(Settings()).run(transport="streamable-http")
