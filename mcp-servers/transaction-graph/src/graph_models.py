"""Response models for the transaction-graph MCP server (docs/INTERPOSE_SCOPING.md
Section 9.6). Standalone from `interpose`'s own models, same reasoning as
ofac-sanctions/src/models.py -- this server stands in for a real production
transaction-graph API the gateway proxies to.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Transaction(BaseModel):
    """One row of the subsampled IBM AML transaction data."""

    timestamp: datetime
    from_account: str
    to_account: str
    amount_received: float
    receiving_currency: str
    amount_paid: float
    payment_currency: str
    payment_format: str
    is_laundering: bool


class AccountRecord(BaseModel):
    """Account metadata plus summary statistics computed over the transaction set --
    the dataset itself has no summary columns, these are aggregated on every call."""

    account_id: str
    bank_id: str
    account_number: str
    entity_id: str
    entity_name: str
    bank_name: str
    total_transactions: int
    total_sent: float
    total_received: float
    distinct_counterparties: int
    first_activity: datetime | None
    last_activity: datetime | None


class AccountLink(BaseModel):
    """One counterparty found while walking `account_id`'s neighborhood -- `hop` is
    the fewest number of edges from the origin account to this one."""

    account_id: str
    hop: int
    total_amount: float
    transaction_count: int


class GraphEdge(BaseModel):
    from_account: str
    to_account: str
    total_amount: float
    transaction_count: int


class GraphResponse(BaseModel):
    """An induced subgraph over a requested set of accounts: every edge whose both
    endpoints are in `nodes`, aggregated (not one row per raw transaction)."""

    nodes: list[str]
    edges: list[GraphEdge]
    truncated: bool


class StructuringSignal(BaseModel):
    """Result of the canned structuring ("smurfing") heuristic: many deposits each
    individually under the reporting threshold that sum past it within a window."""

    account_id: str
    window_days: int
    threshold_amount: float
    deposit_count: int
    total_deposits: float
    flagged: bool
    rationale: str


class WriteResult(BaseModel):
    """Result of `mark_investigated` -- the sole write tool on this server."""

    account_id: str
    disposition: str
    rationale: str
    recorded_at: datetime
