# transaction-graph

The transaction-graph MCP server (`docs/INTERPOSE_SCOPING.md` Section 9.6, Phase 3 Day 12).
Exposes the subsampled IBM AML transaction data (`data/README.md`) as a queryable graph over
streamable-HTTP -- see `concepts/29-embedded-analytics-with-duckdb.md` for the DuckDB
concepts and design choices behind it.

Deliberately its own small, standalone service (own `Dockerfile`, no dependency on
`src/interpose/`), following the same pattern `ofac-sanctions` established in Day 11: this
stands in for a real production transaction-graph API the gateway proxies to, not something
the gateway owns.

## Tools

- `query_transactions(account_id, from_date, to_date)` -- transactions touching
  `account_id` (as sender or receiver) in a date range.
- `get_account(account_id)` -- account metadata plus summary statistics (transaction
  count, totals sent/received, distinct counterparties, first/last activity), computed
  live -- the dataset itself has no summary columns.
- `neighbors(account_id, hops=1, min_amount=0)` -- breadth-first k-hop neighborhood of
  counterparties, aggregated by account (not one row per raw transaction).
- `subgraph(account_ids, max_edges=500)` -- the induced subgraph over a given account
  set: every aggregated edge whose both endpoints are in the set.
- `structuring_check(account_id, window_days=30)` -- a canned structuring ("smurfing")
  heuristic: flags accounts receiving enough sub-threshold deposits, summing past the
  US BSA Currency Transaction Report threshold ($10,000), within a trailing window
  anchored to the account's own last activity (not wall-clock -- this is 2022 data).
- `mark_investigated(account_id, disposition, rationale)` -- **the write action.**
  Records a disposition (`cleared` | `escalate` | `monitor`) in an in-memory table that
  resets on every restart. Exists solely to demonstrate HITL gating and audit on a
  mutating call (Day 14's AML policy pack gates this specifically).

## Data

Reads two DuckDB views over the subsampled IBM AML dataset (`data/README.md`):
`transactions` and `accounts`. Real default: the partitioned Parquet directories
`~/.interpose/data/ibm-aml/{transactions,accounts}/` produced by
`interpose.analytics.subsample_aml`. Unlike `ofac-sanctions` (which fetches its
reference list live over the network), this dataset is a ~150MB local artifact that is
never committed to the repo or baked into the image -- override
`TRANSACTION_GRAPH_TRANSACTIONS_SOURCE` / `TRANSACTION_GRAPH_ACCOUNTS_SOURCE` (env vars)
to point at it explicitly, whether that's the real directories, a bind-mounted path
inside a container, or (what tests use) a small local `.csv` fixture --
`mcp-servers/transaction-graph/tests/fixtures/` holds a tiny synthetic sample (a
2-hop chain and a structuring pattern, not real IBM/OFAC data -- this dataset's
CDLA-Sharing-1.0 license is share-alike, so test fixtures here are synthetic rather
than small real extracts).

## Running it

Bare, against the real subsampled dataset:

```sh
uv run --group mcp-servers python mcp-servers/transaction-graph/src/server.py
```

Listens on `http://127.0.0.1:9003/mcp`. Standalone unit tests (pure DuckDB query logic
against small in-memory fixture tables, no files, no network):

```sh
uv run pytest tests/unit/mcp_servers/test_transaction_graph_store.py
```

Integration test through the real gateway (`tests/integration/test_gateway_transaction_graph.py`,
uses the local fixture CSVs above):

```sh
uv run pytest tests/integration/test_gateway_transaction_graph.py
```

Containerized -- the dataset is bind-mounted at run time, not baked into the image:

```sh
docker build -t transaction-graph:dev mcp-servers/transaction-graph
docker run --rm -p 9003:9003 \
  -v "$HOME/.interpose/data/ibm-aml:/data/ibm-aml:ro" \
  -e TRANSACTION_GRAPH_TRANSACTIONS_SOURCE=/data/ibm-aml/transactions \
  -e TRANSACTION_GRAPH_ACCOUNTS_SOURCE=/data/ibm-aml/accounts \
  transaction-graph:dev
```

**Named gap:** not yet deployed into the local `kind` cluster the way `hello-echo` and
`ofac-sanctions` are (`dev/mcp-servers/`) -- doing that for real requires `kind.yaml` to
mount the host's `~/.interpose/data/ibm-aml/` into the cluster's nodes (`extraMounts`),
which hasn't been added yet. Deferred to when Day 13's investigation agent needs a real
in-cluster run, rather than done speculatively here.
