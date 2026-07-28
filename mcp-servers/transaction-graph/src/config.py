"""Settings for the transaction-graph MCP server -- deliberately its own tiny
Settings, not interpose.config.Settings, same reasoning as ofac-sanctions/src/config.py:
this is meant to be a genuinely separate service, with its own environment.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Real default: the Spark-subsampled IBM AML data written by
# interpose.analytics.subsample_aml (docs/ROADMAP.md Day 12, data/README.md). These
# are directories of partitioned Parquet files, not single files -- see
# store.py::_table_expr for how a directory vs. a single `.csv`/`.parquet` path is
# turned into a DuckDB table expression.
DEFAULT_TRANSACTIONS_SOURCE = str(Path.home() / ".interpose" / "data" / "ibm-aml" / "transactions")
DEFAULT_ACCOUNTS_SOURCE = str(Path.home() / ".interpose" / "data" / "ibm-aml" / "accounts")

# US Bank Secrecy Act Currency Transaction Report threshold -- the canonical
# "individually-small-but-collectively-large" line structuring tries to stay under.
# See concepts/29-embedded-analytics-with-duckdb.md for why this single constant does
# double duty (the per-transaction "small" cutoff and the aggregate alert cutoff).
DEFAULT_SMALL_DEPOSIT_THRESHOLD = 10_000.0
DEFAULT_MIN_STRUCTURING_DEPOSITS = 3
DEFAULT_MAX_HOPS = 3


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRANSACTION_GRAPH_", env_file=".env", extra="ignore"
    )

    # Either a directory of partitioned Parquet (the real default) or a path to a
    # single `.csv`/`.parquet` file -- a small CSV fixture is what tests and offline
    # local dev use instead of the full subsampled dataset.
    transactions_source: str = DEFAULT_TRANSACTIONS_SOURCE
    accounts_source: str = DEFAULT_ACCOUNTS_SOURCE
    small_deposit_threshold: float = DEFAULT_SMALL_DEPOSIT_THRESHOLD
    min_structuring_deposits: int = DEFAULT_MIN_STRUCTURING_DEPOSITS
    max_hops: int = DEFAULT_MAX_HOPS
    host: str = "127.0.0.1"
    port: int = 9003
