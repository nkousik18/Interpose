"""Bulk-loads the synthetic telemetry Parquet
(`interpose.analytics.generate_synthetic_telemetry`) into Postgres
`audit_entries_synthetic`, via a plain `COPY`, not a Spark JDBC write.

Spark's JDBC write path needs a JDBC driver Ivy-resolved at runtime
(`spark.jars.packages`) -- tried first, and the local environment's Ivy resolution
didn't actually fetch the driver despite having real internet access, for reasons not
worth chasing down for a one-time demo loader. There's also no existing precedent in
this project for Spark writing to Postgres directly (the audit store itself writes via
SQLAlchemy, Section 6.7). Reading the already-written Parquet with `pyarrow` in
batches and `COPY`-ing it is simpler, has one fewer moving part, and matches how every
other Postgres write in this project already happens.

Run with: uv run --group analytics python -m interpose.analytics.load_synthetic_telemetry
"""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg
import pyarrow.dataset as ds

from interpose.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

IN_DIR = Path.home() / ".interpose" / "data" / "synthetic-telemetry"
BATCH_SIZE = 50_000

# Matches generate_synthetic_telemetry.OUTPUT_COLUMNS exactly -- `id` is omitted
# (Postgres assigns it from audit_entries_synthetic_id_seq) and `day` is a
# Parquet-partitioning artifact, not a real table column.
COLUMNS = [
    "trace_id",
    "span_id",
    "timestamp",
    "status",
    "agent_id",
    "session_id",
    "server",
    "tool",
    "args_hash",
    "args_redacted",
    "policies_fired",
    "decision",
    "latency_ms",
    "tokens",
    "hitl_ticket_id",
    "hitl_reviewer",
    "hitl_decision",
    "hitl_rationale",
    "tags",
]


def _to_psycopg_dsn(sqlalchemy_url: str) -> str:
    """`Settings.database_url` is a SQLAlchemy URL (`postgresql+psycopg://...`) --
    psycopg's own `connect()` wants the plain `postgresql://` form, no dialect
    suffix."""
    return sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://")


def load(parquet_dir: Path = IN_DIR, database_url: str | None = None) -> int:
    dataset = ds.dataset(str(parquet_dir), format="parquet", partitioning="hive")
    dsn = _to_psycopg_dsn(database_url or get_settings().database_url)

    total = 0
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE audit_entries_synthetic")
        copy_sql = "COPY audit_entries_synthetic (" + ", ".join(COLUMNS) + ") FROM STDIN"
        with cur.copy(copy_sql) as copy:
            for batch in dataset.to_batches(batch_size=BATCH_SIZE, columns=COLUMNS):
                rows = batch.to_pylist()
                for row in rows:
                    copy.write_row(tuple(row[column] for column in COLUMNS))
                total += len(rows)
                logger.info("synthetic_telemetry.load_progress rows=%d", total)
        conn.commit()

    logger.info("synthetic_telemetry.loaded rows=%d table=audit_entries_synthetic", total)
    return total


if __name__ == "__main__":
    load()
