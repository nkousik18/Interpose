"""Response models for the OFAC sanctions MCP server (docs/INTERPOSE_SCOPING.md
Section 9.6). Standalone from `interpose`'s own models -- this server is meant to be
a genuinely separate service the gateway proxies to, the same way a real production
sanctions-screening API would be.
"""

from pydantic import BaseModel

# https://sanctionssearch.ofac.treas.gov is OFAC's own public search UI; linking a
# match back to it by ent_num gives a human reviewer somewhere to verify a hit
# without Interpose needing to reproduce OFAC's own record display.
REFERENCE_URL_TEMPLATE = "https://sanctionssearch.ofac.treas.gov/Details.aspx?id={ent_num}"


class SDNEntry(BaseModel):
    """One row of `sdn.csv`, plus any aliases `alt.csv` attaches to it."""

    ent_num: str
    name: str
    # "individual" | "entity" | "vessel" | "aircraft" -- see loader.py's handling of
    # the raw "-0-" sentinel, which means "entity", not "unknown".
    sdn_type: str
    programs: list[str]
    remarks: str
    aliases: list[str] = []


class SanctionsMatch(BaseModel):
    """One fuzzy-match result against the SDN list."""

    matched_name: str
    entry_id: str
    score: float
    # Whether `score` cleared the configured match threshold -- callers that don't
    # want to reason about a raw fuzzy score can just check this.
    is_match: bool
    programs: list[str]
    reference_url: str
