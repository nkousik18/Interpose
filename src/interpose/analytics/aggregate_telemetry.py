"""Aggregates synthetic gateway telemetry into Grafana-ready summary tables
(docs/INTERPOSE_SCOPING.md Section 10.6, 12.4; Phase 3 Day 15): `agg_telemetry_hourly`,
`agg_policy_fires_daily`, `agg_hitl_daily`, `agg_aml_pack_daily`, `agg_cost_daily`
(`interpose.analytics.models`), which the rebuilt Grafana dashboards
(`charts/interpose/files/dashboards/`) query directly via a Postgres datasource.

Reads the synthetic Parquet `generate_synthetic_telemetry` wrote directly, not from
Postgres -- Spark's JDBC read path hits the same Ivy-resolution problem
`load_synthetic_telemetry`'s docstring describes for writes, and there's no reason to
round-trip through Postgres to read back data Spark already has local Parquet access
to.

Deliberately scoped to synthetic telemetry only, not parameterized to also aggregate
the real `audit_entries` table (Section 10.6's original framing suggests either
could feed this job). Section 10.6's own reasoning for generating synthetic
telemetry in the first place -- "in 4 weeks of MVP development you will not
accumulate 10M real tool calls" -- is exactly why a Spark-*scale* aggregation job's
real value is demonstrated against the synthetic corpus: a few hundred real rows
don't need Spark to aggregate, and Section 12.5's saved compliance queries already
answer real-audit questions directly against Postgres. A "real" aggregation path is a
named future extension, not built here.

Each aggregate row's `source` column is unconditionally "synthetic" for exactly that
reason -- named explicitly, not left to be confused with real gateway activity.

Run with: uv run --group analytics python -m interpose.analytics.aggregate_telemetry
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import psycopg
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import ArrayType, StringType, StructField, StructType

from interpose.analytics.generate_synthetic_telemetry import OUT_DIR as TELEMETRY_DIR
from interpose.analytics.load_synthetic_telemetry import _to_psycopg_dsn
from interpose.analytics.spark_env import ensure_java_home
from interpose.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SOURCE = "synthetic"

_POLICIES_FIRED_SCHEMA = ArrayType(
    StructType(
        [StructField("policy", StringType()), StructField("effect_type", StringType())]
    )
)
_DECISION_SCHEMA = StructType(
    [
        StructField("outcome", StringType()),
        StructField("fired_policy", StringType()),
        StructField("reason", StringType()),
    ]
)
_TOKENS_SCHEMA = StructType(
    [
        StructField("prompt", StringType()),
        StructField("completion", StringType()),
        StructField("provider", StringType()),
        StructField("cost_usd", StringType()),
    ]
)


def build_spark() -> SparkSession:
    ensure_java_home()
    return (
        SparkSession.builder.appName("interpose-aggregate-telemetry")
        .master("local[*]")
        .config("spark.driver.memory", "6g")
        .config("spark.sql.shuffle.partitions", "32")
        .getOrCreate()
    )


def load_raw(spark: SparkSession) -> DataFrame:
    df = spark.read.parquet(str(TELEMETRY_DIR))
    return (
        df.withColumn("hour", F.date_trunc("hour", F.col("timestamp")))
        .withColumn("day", F.to_date("timestamp"))
        .withColumn("decision_parsed", F.from_json("decision", _DECISION_SCHEMA))
        .withColumn("policies_fired_parsed", F.from_json("policies_fired", _POLICIES_FIRED_SCHEMA))
        .withColumn("tokens_parsed", F.from_json("tokens", _TOKENS_SCHEMA))
    )


def aggregate_telemetry_hourly(df: DataFrame) -> list[dict]:
    """Dashboard 1 (Gateway Health), approximated from the audit log's own
    `status`/`latency_ms` -- see `interpose.analytics.models.TelemetryHourly`'s
    docstring for why (no Prometheus deployed, nothing exports `/metrics`)."""
    agg = (
        df.groupBy("hour", "server", "tool", F.col("status").alias("outcome"))
        .agg(
            F.count("*").alias("call_count"),
            F.sum(F.when(F.col("status") == "UPSTREAM_ERROR", 1).otherwise(0)).alias(
                "error_count"
            ),
            F.percentile_approx("latency_ms", 0.50).alias("latency_p50_ms"),
            F.percentile_approx("latency_ms", 0.95).alias("latency_p95_ms"),
            F.percentile_approx("latency_ms", 0.99).alias("latency_p99_ms"),
        )
        .withColumn("source", F.lit(SOURCE))
    )
    return [row.asDict() for row in agg.collect()]


def aggregate_policy_fires_daily(df: DataFrame) -> list[dict]:
    """Dashboard 2's "policy fires per policy, by outcome" panel."""
    exploded = df.select(
        "day",
        "decision_parsed.outcome",
        F.explode_outer("policies_fired_parsed").alias("fired"),
    ).filter(F.col("fired").isNotNull())
    agg = (
        exploded.groupBy(
            "day",
            F.col("fired.policy").alias("policy_name"),
            F.col("fired.effect_type").alias("effect_type"),
            "outcome",
        )
        .agg(F.count("*").alias("fire_count"))
        .withColumn("source", F.lit(SOURCE))
    )
    return [row.asDict() for row in agg.collect()]


def aggregate_hitl_daily(df: DataFrame) -> list[dict]:
    """Dashboard 2's HITL queue-depth/response-time/approval-ratio panels.
    `median_response_seconds` is fabricated here (a deterministic hash of `trace_id`,
    not derived from two real timestamps) -- the per-call synthetic row model
    (one terminal row, not a HELD-then-COMPLETED pair) has no second timestamp to
    diff, same reasoning `generate_synthetic_telemetry`'s module docstring gives for
    not replicating that pairing at all."""
    hitl_rows = df.filter(F.col("hitl_decision").isNotNull())
    with_fake_response_time = hitl_rows.withColumn(
        "response_seconds",
        (F.abs(F.hash("trace_id")) % F.lit(570)) + F.lit(30),
    )
    agg = (
        with_fake_response_time.groupBy("day")
        .agg(
            F.count("*").alias("tickets_created"),
            F.sum(F.when(F.col("hitl_decision") == "APPROVED", 1).otherwise(0)).alias("approved"),
            F.sum(F.when(F.col("hitl_decision") == "DENIED", 1).otherwise(0)).alias("denied"),
            F.lit(0).alias("timed_out"),  # the generator never fabricates a timeout bucket
            F.percentile_approx("response_seconds", 0.5).alias("median_response_seconds"),
        )
        # Every HITL policy in this project's real pack uses one reviewer group
        # (aml-analysts, Phase 3 Day 14) -- the generator doesn't model multiple
        # groups, so this dashboard doesn't invent a distinction that isn't real.
        .withColumn("reviewer_group", F.lit("aml-analysts"))
        .withColumn("source", F.lit(SOURCE))
    )
    return [row.asDict() for row in agg.collect()]


def aggregate_aml_pack_daily(df: DataFrame) -> list[dict]:
    """Dashboard 3 (AML Pack demo-specific)."""
    ofac = df.filter(F.col("server") == "ofac-sanctions")
    txg = df.filter(F.col("server") == "transaction-graph")
    mark_investigated = txg.filter(F.col("tool") == "mark_investigated")

    ofac_calls = ofac.groupBy("day").agg(F.count("*").alias("ofac_calls"))
    sanctions_matches = (
        ofac.filter(F.col("tool") == "check_entity")
        .groupBy("day")
        .agg((F.count("*") * F.lit(0.35)).cast("long").alias("sanctions_matches"))
        # No real match-confidence field exists on synthetic rows at all; ~35% of
        # check_entity calls "matching" is an illustrative placeholder figure, not a
        # measured rate the way Day 14's real fuzzy-match threshold is.
    )
    tx_graph_calls = txg.groupBy("day").agg(F.count("*").alias("transaction_graph_calls"))
    tags_array = F.split(F.regexp_replace("tags", r'[\[\]"]', ""), ",")
    structuring_alerts = (
        txg.filter(F.array_contains(tags_array, "incident:structuring"))
        .groupBy("day")
        .agg(F.count("*").alias("structuring_alerts"))
    )
    mi_by_outcome = mark_investigated.groupBy("day").agg(
        F.sum(F.when(F.col("status") == "DENIED", 1).otherwise(0)).alias(
            "mark_investigated_denied"
        ),
        F.sum(
            F.when(F.col("hitl_decision") == "APPROVED", 1).otherwise(0)
        ).alias("mark_investigated_approved"),
        # Mutually exclusive from `_approved` -- see models.AmlPackDaily's docstring
        # for why this bucket can be nonzero in synthetic data but never in real
        # traffic (aml-write-hitl-gate holds every real mark_investigated call).
        F.sum(
            F.when(
                (F.col("status") == "COMPLETED") & F.col("hitl_decision").isNull(), 1
            ).otherwise(0)
        ).alias("mark_investigated_auto_passed"),
    )

    joined = (
        ofac_calls.join(sanctions_matches, "day", "outer")
        .join(tx_graph_calls, "day", "outer")
        .join(structuring_alerts, "day", "outer")
        .join(mi_by_outcome, "day", "outer")
        .fillna(0)
        .withColumn("source", F.lit(SOURCE))
    )
    return [row.asDict() for row in joined.collect()]


def aggregate_cost_daily(df: DataFrame) -> list[dict]:
    """Dashboard 4 (Cost Telemetry) -- synthetic-only, see module docstring and
    `interpose.analytics.models.CostDaily`'s: the real gateway has no LLM-cost
    visibility at all (Phase 3 Day 14's finding). Grouped by `{day, agent_id,
    provider}`, deliberately not also `tool` -- see `CostDaily`'s docstring for the
    918,819-row table that grouping by tool too actually produced."""
    cost_rows = df.filter(F.col("tokens").isNotNull())
    provider = F.col("tokens_parsed.provider").alias("provider")
    agg = (
        cost_rows.groupBy("day", "agent_id", provider)
        .agg(
            F.sum(F.col("tokens_parsed.prompt").cast("long")).alias("prompt_tokens"),
            F.sum(F.col("tokens_parsed.completion").cast("long")).alias("completion_tokens"),
            F.sum(F.col("tokens_parsed.cost_usd").cast("double")).alias("cost_usd"),
        )
        .withColumn("source", F.lit(SOURCE))
    )
    return [row.asDict() for row in agg.collect()]


_TABLE_SPECS: dict[str, list[str]] = {
    "agg_telemetry_hourly": [
        "source",
        "hour",
        "server",
        "tool",
        "outcome",
        "call_count",
        "error_count",
        "latency_p50_ms",
        "latency_p95_ms",
        "latency_p99_ms",
    ],
    "agg_policy_fires_daily": [
        "source",
        "day",
        "policy_name",
        "effect_type",
        "outcome",
        "fire_count",
    ],
    "agg_hitl_daily": [
        "source",
        "day",
        "reviewer_group",
        "tickets_created",
        "approved",
        "denied",
        "timed_out",
        "median_response_seconds",
    ],
    "agg_aml_pack_daily": [
        "source",
        "day",
        "ofac_calls",
        "sanctions_matches",
        "transaction_graph_calls",
        "structuring_alerts",
        "mark_investigated_denied",
        "mark_investigated_approved",
        "mark_investigated_auto_passed",
    ],
    "agg_cost_daily": [
        "source",
        "day",
        "agent_id",
        "provider",
        "prompt_tokens",
        "completion_tokens",
        "cost_usd",
    ],
}


def _write_table(
    conn: psycopg.Connection, table: str, columns: list[str], rows: list[dict]
) -> None:
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {table} WHERE source = %s", (SOURCE,))
        if rows:
            copy_sql = f"COPY {table} (" + ", ".join(columns) + ") FROM STDIN"
            with cur.copy(copy_sql) as copy:
                for row in rows:
                    copy.write_row(tuple(row[column] for column in columns))
    conn.commit()
    logger.info("aggregate_telemetry.written table=%s rows=%d", table, len(rows))


def main() -> None:
    spark = build_spark()
    dsn = _to_psycopg_dsn(get_settings().database_url)
    started = datetime.now(UTC)
    try:
        raw = load_raw(spark).cache()
        aggregates = {
            "agg_telemetry_hourly": aggregate_telemetry_hourly(raw),
            "agg_policy_fires_daily": aggregate_policy_fires_daily(raw),
            "agg_hitl_daily": aggregate_hitl_daily(raw),
            "agg_aml_pack_daily": aggregate_aml_pack_daily(raw),
            "agg_cost_daily": aggregate_cost_daily(raw),
        }
        with psycopg.connect(dsn) as conn:
            for table, rows in aggregates.items():
                _write_table(conn, table, _TABLE_SPECS[table], rows)
        elapsed = (datetime.now(UTC) - started).total_seconds()
        logger.info("aggregate_telemetry.done elapsed_seconds=%.1f", elapsed)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
