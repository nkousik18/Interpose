# Embedded analytics with DuckDB

Phase 3, Day 12 (`docs/ROADMAP.md`) built the second AML MCP server,
`transaction-graph` — it answers questions like "who has account #A_16453 been
paying, and is that a structuring pattern?" over the ~3.16M-row subsampled IBM AML
dataset (`data/README.md`). This is where DuckDB enters the project.

## What DuckDB actually is

DuckDB is an OLAP ("analytical") SQL database, but **embedded** — like SQLite, it's a
library you link into your process, not a server you connect to over a network. There
is no DuckDB daemon, no connection string, no separate container in
`docker-compose.yaml`. `duckdb.connect(":memory:")` in Python *is* the whole database,
living in your process's memory for as long as the process runs.

Compare that to Postgres (`concepts/18-postgres-sqlalchemy-alembic.md`), which
Interpose already uses for the audit log: Postgres is **row-oriented** (good at "fetch
this one record fast," which is what an audit lookup needs) and always a
separate process you connect to over a socket. DuckDB is **column-oriented** (good at
"scan millions of rows and aggregate a couple of columns," which is what "sum this
account's deposits in a date range" needs) and has no separate process at all. Each
tool is right for a different shape of workload — that's why this project now uses
both, for different jobs, not because one replaces the other.

## Reading Parquet without loading it

`transaction-graph`'s `store.py` never copies the subsampled dataset into DuckDB's own
storage. Instead it does:

```sql
CREATE VIEW transactions AS SELECT ... FROM read_parquet('.../transactions/**/*.parquet')
```

`read_parquet(...)` is a *table function* — it makes an external Parquet directory
(the exact one `interpose.analytics.subsample_aml` writes,
`concepts/14-spark-and-pyspark.md`) queryable as if it were a table, without reading
the whole thing into memory first. When a query has a `WHERE to_id = ?` filter,
DuckDB pushes that filter down into the Parquet scan itself, only actually reading the
column chunks it needs. That's why a server holding a 128MB dataset can answer a
single-account query in milliseconds without ever "loading the database" as a
separate step — there's no load step; the data stays on disk, DuckDB just gets fast
at reading exactly the slice a query needs.

## The one real table: an ephemeral write log

`transactions` and `accounts` are read-only views. The one actual DuckDB *table* this
server creates is `investigated` — the write target for `mark_investigated`, the
server's sole mutating tool (Section 9.6's design: it exists specifically so Day 14's
HITL policy pack has something real to gate). It lives in the same in-memory
connection and is gone the moment the process restarts, which is deliberate: this
"investigation state" is a demo artifact, not a system of record — Interpose's real
audit trail for that write action is the hash-chained Postgres log the gateway
produces around every call, not this table.

One consequence worth naming: DuckDB's Python connection object is not safe to use
from multiple threads at once. Reads are fine to run concurrently against one
connection, but interleaving a write with anything else risks corrupting the
connection's internal state. `GraphStore.write_lock` (a plain `threading.Lock`) wraps
the one write path for exactly this reason — a small, cheap guard for what will only
ever be a single writer in this demo, but the kind of thing that matters the moment a
second concurrent request shows up.

## Design choices in the six tools (Section 9.6)

- **`neighbors`, k-hop traversal.** Rather than one recursive SQL query (DuckDB
  supports `WITH RECURSIVE`, but reasoning about hop-by-hop aggregation inside a
  single recursive CTE gets hard to read fast), this is a small Python BFS loop: one
  SQL query per hop, aggregating each hop's new counterparties before deciding the
  next hop's frontier. Easier to test, easier to cap (`max_hops` in `Settings`, so a
  caller can't accidentally ask for a 50-hop walk across a 500K-account graph).
- **`subgraph`, an *induced* subgraph.** Given a set of account IDs, the tool returns
  every edge whose *both* endpoints are in that set — not every edge touching any of
  them. That's the standard graph-theory meaning of "induced subgraph on a vertex
  set," and it's what a real investigation needs: "how do these specific accounts I've
  already found relate to each other," not "show me everything adjacent to any of
  them" (that's what `neighbors` is for).
- **`structuring_check`, window anchored to the account's own data, not wall-clock.**
  This is 2022 data (`data/README.md`); "the last 30 days" measured against today's
  real date would find nothing, ever. The window is anchored to the account's own most
  recent deposit instead — a small but real judgment call about what "recent" means
  for a fixed historical dataset.

## A real bug: unpinned dependencies drift out from under you

Building this server's Docker image for the first time failed immediately:
`ModuleNotFoundError: No module named 'mcp.server.fastmcp'`. The Dockerfile installs
`mcp[cli]>=1.28.1` — a lower bound only, no upper bound, no lockfile (standalone
service Dockerfiles like this one and `ofac-sanctions/Dockerfile` don't use the root
project's `uv.lock`, deliberately, since they're meant to be independently
buildable services). Between Day 11 (when `ofac-sanctions`' identical pattern was
verified working) and today, the `mcp` SDK shipped a breaking `2.0.0` — the module
that used to be `mcp.server.fastmcp` was renamed. A fresh `pip install` picked up
`2.0.0` and broke.

Fix: pin the exact version the root project's `uv.lock` already resolved
(`mcp[cli]==1.28.1`) in both Dockerfiles, rather than leaving them to float. This is
the general lesson, not just a one-off patch: anything without a lockfile is
implicitly "whatever's newest today," and "today" keeps moving. A reproducible build
needs either a lockfile or an explicit pin — there's no third option.
