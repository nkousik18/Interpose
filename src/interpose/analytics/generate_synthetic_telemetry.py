"""Synthetic gateway telemetry generator (docs/INTERPOSE_SCOPING.md Section 10.6,
Phase 3 Day 15). Fabricates ~10M tool-call records shaped like `audit_entries`,
simulating 4 weeks of a busy gateway across 500 agents, 100 tools, 20 upstream
servers -- exists solely so `interpose.analytics.aggregate_telemetry` and Grafana's
Postgres-backed dashboards have something meaningful to show. Section 10.6's own
reasoning: in a few weeks of MVP development this project will never accumulate 10M
real tool calls, and the Spark/dashboard story needs demonstrable scale to be
credible.

One row per call, holding its *terminal* outcome (PASS/DENY/HITL-approved/
HITL-denied/error) -- not the real audit store's literal INTENT-then-COMPLETED row
pairing (Section 6.7). That pairing is an artifact of how the live gateway writes
audit rows incrementally as a call proceeds; it has no bearing on what an aggregation
job needs to count, and doubling 10M rows into 20M for no analytical benefit isn't
worth it.

Output: Parquet partitioned by day under
`~/.interpose/data/synthetic-telemetry/`, loaded into Postgres by
`interpose.analytics.load_synthetic_telemetry` (a separate, plain-Python COPY step,
not a Spark JDBC write -- see that module's docstring for why).

Run with: uv run --group analytics python -m interpose.analytics.generate_synthetic_telemetry
"""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from interpose.analytics.spark_env import ensure_java_home

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUT_DIR = Path.home() / ".interpose" / "data" / "synthetic-telemetry"

SEED = 42
TARGET_ROWS = 10_000_000
NUM_AGENTS = 500
NUM_WEEKS = 4
# A fixed, reproducible window rather than "the last 4 weeks from whenever this runs"
# -- same reasoning as the AML subsampling job's fixed seed (concept 14): a generator
# whose output changes based on wall-clock time isn't reproducible.
START_DATE = date(2026, 7, 6)  # a Monday
END_DATE = START_DATE + timedelta(weeks=NUM_WEEKS)
NUM_DAYS = (END_DATE - START_DATE).days

# Two of the twenty servers are this project's own real ones, so Dashboard 3 (AML
# pack) has something to filter on; the rest are generic stand-ins for "a busy
# gateway proxies to many upstream servers."
REAL_SERVERS = {
    "ofac-sanctions": ["check_entity", "check_alias", "get_entity_detail"],
    "transaction-graph": [
        "query_transactions",
        "get_account",
        "neighbors",
        "subgraph",
        "structuring_check",
        "mark_investigated",
    ],
}
NUM_GENERIC_SERVERS = 18
_GENERIC_TOOLS_TARGET = 100 - sum(len(v) for v in REAL_SERVERS.values())  # 91
GENERIC_SERVERS = {
    f"server-{i:02d}": [
        f"tool_{i:02d}_{j}"
        for j in range(
            _GENERIC_TOOLS_TARGET // NUM_GENERIC_SERVERS
            + (1 if i < _GENERIC_TOOLS_TARGET % NUM_GENERIC_SERVERS else 0)
        )
    ]
    for i in range(NUM_GENERIC_SERVERS)
}
ALL_SERVERS: dict[str, list[str]] = {**REAL_SERVERS, **GENERIC_SERVERS}
SERVER_TOOL_PAIRS = [(server, tool) for server, tools in ALL_SERVERS.items() for tool in tools]

# 3 incident windows (Section 10.6): fixed (day_offset, hour, duration_hours) tuples
# where the DENY rate spikes well above baseline -- something a real anomaly detector
# (Agent A2, interpose.control_plane) would have flagged.
INCIDENT_WINDOWS = [
    (day_offset, hour, 2) for day_offset, hour in [(5, 14), (13, 3), (22, 20)]
]
# The one coordinated-attack simulation: a single agent hammering one tool with a
# burst of calls in a short window, almost all denied (a rate-limit-exceeded story).
ATTACK_DAY_OFFSET = 18
ATTACK_HOUR = 2
ATTACK_AGENT_INDEX = 217
ATTACK_SERVER, ATTACK_TOOL = "ofac-sanctions", "check_entity"
ATTACK_CALL_COUNT = 5_000

BASELINE_DENY_RATE = 0.10
INCIDENT_DENY_RATE = 0.55
HITL_APPROVED_RATE = 0.06
HITL_DENIED_RATE = 0.02
UPSTREAM_ERROR_RATE = 0.02
# PASS gets whatever's left of the 1.0 budget after the above.

HITL_REVIEWERS = ["alice", "bob", "carol", "dave"]
PROVIDERS = ["groq", "anthropic"]
# Only this fraction of rows carry a synthetic `tokens`/cost figure at all -- most
# tool calls have no LLM cost attached to them even conceptually (Phase 3 Day 14's
# finding: the real gateway never observes this), this is purely illustrative volume
# for Dashboard 4.
COST_BEARING_ROW_FRACTION = 0.15


def build_spark() -> SparkSession:
    ensure_java_home()
    return (
        SparkSession.builder.appName("interpose-synthetic-telemetry")
        .master("local[*]")
        .config("spark.driver.memory", "6g")
        .config("spark.sql.shuffle.partitions", "64")
        .getOrCreate()
    )


def _hour_weight(hour_col: str) -> F.Column:
    """Diurnal cycle: a smooth bell centered at 13:00, floor ~0.15 overnight, peak
    ~1.0 midday -- built from a cosine rather than a lookup table so it's one
    expression, not 24 hand-picked constants."""
    hour = F.col(hour_col)
    phase = (hour - F.lit(13.0)) / F.lit(24.0) * F.lit(2 * math.pi)
    return F.lit(0.15) + F.lit(0.85) * ((F.cos(phase) + F.lit(1.0)) / F.lit(2.0))


def _day_weight(day_offset_col: str) -> F.Column:
    """Weekend dip: Saturday/Sunday (day_offset % 7 in {5, 6}, since START_DATE is a
    Monday) run at 40% of weekday volume."""
    dow = F.col(day_offset_col) % 7
    return F.when(dow >= 5, F.lit(0.4)).otherwise(F.lit(1.0))


def build_hour_buckets(spark: SparkSession) -> DataFrame:
    """One row per (day_offset, hour) -- `NUM_DAYS * 24` rows, small enough to
    broadcast. `weight` folds in the diurnal cycle, the weekend dip, and a spike
    during any of the 3 incident windows."""
    buckets = spark.createDataFrame(
        [(d, h) for d in range(NUM_DAYS) for h in range(24)], ["day_offset", "hour"]
    )
    buckets = buckets.withColumn("weight", _hour_weight("hour") * _day_weight("day_offset"))
    incident_condition = F.lit(False)
    for day_offset, hour, duration in INCIDENT_WINDOWS:
        incident_condition = incident_condition | (
            (F.col("day_offset") == day_offset)
            & (F.col("hour") >= hour)
            & (F.col("hour") < hour + duration)
        )
    return buckets.withColumn(
        "in_incident_window", incident_condition
    ).withColumn(
        # Incident windows also draw more volume, not just a worse outcome mix --
        # a real incident is a spike in *activity*, not just a spike in denials.
        "weight",
        F.when(incident_condition, F.col("weight") * F.lit(2.5)).otherwise(F.col("weight")),
    )


def allocate_row_counts(hour_buckets: DataFrame) -> DataFrame:
    """Turns each bucket's `weight` into an integer row count summing to
    `TARGET_ROWS`, computed once on the small (NUM_DAYS*24-row) bucket table -- not
    via a join against the full 10M-row target, which a naive weighted-sampling
    implementation would need."""
    total_weight = hour_buckets.agg(F.sum("weight")).first()[0]
    return hour_buckets.withColumn(
        "row_count",
        F.round(F.col("weight") / F.lit(total_weight) * F.lit(TARGET_ROWS)).cast("long"),
    )


def build_base_rows(spark: SparkSession, bucket_counts: DataFrame) -> DataFrame:
    """Explodes each (day_offset, hour, row_count) bucket into `row_count` actual
    rows -- `F.sequence` + `F.explode` rather than a manual union per bucket
    (there are `NUM_DAYS * 24` = 672 of them), or a range-join against the full
    target row count (which Spark would have to execute as a broadcast nested-loop
    join, not a cheap equi-join, at 10M-rows-times-672-buckets scale)."""
    exploded = bucket_counts.filter(F.col("row_count") > 0).select(
        "day_offset",
        "hour",
        "in_incident_window",
        F.explode(F.sequence(F.lit(0), F.col("row_count") - 1)).alias("_bucket_idx"),
    )
    return (
        exploded.withColumn("_rand_a", F.rand(SEED))
        .withColumn("_rand_b", F.rand(SEED + 1))
        .withColumn("_rand_c", F.rand(SEED + 2))
        .withColumn("_rand_d", F.rand(SEED + 3))
        .withColumn("_rand_e", F.rand(SEED + 4))
    )


def _unix_start() -> int:
    from datetime import UTC, datetime

    return int(
        datetime(START_DATE.year, START_DATE.month, START_DATE.day, tzinfo=UTC).timestamp()
    )


def with_timestamp(df: DataFrame) -> DataFrame:
    minute = (F.col("_rand_b") * 60).cast("int")
    second = (F.col("_rand_c") * 60).cast("int")
    unix_seconds = (
        F.lit(_unix_start())
        + F.col("day_offset") * 86400
        + F.col("hour") * 3600
        + minute * 60
        + second
    )
    return df.withColumn("timestamp", F.timestamp_seconds(unix_seconds))


def with_agent(df: DataFrame) -> DataFrame:
    # A skewed draw (product of two uniforms) rather than a flat one -- a handful of
    # agents genuinely are far busier than the rest in any real fleet, and a flat
    # distribution would make every dashboard "top agents" panel meaningless.
    agent_index = (F.col("_rand_d") * F.col("_rand_a") * NUM_AGENTS).cast("int")
    return df.withColumn("agent_id", F.format_string("agent-%04d", agent_index))


def with_server_and_tool(spark: SparkSession, df: DataFrame) -> DataFrame:
    pairs_array = F.array(
        *[F.struct(F.lit(s).alias("server"), F.lit(t).alias("tool")) for s, t in SERVER_TOOL_PAIRS]
    )
    idx = (F.col("_rand_e") * len(SERVER_TOOL_PAIRS)).cast("int")
    df = df.withColumn("_pair", F.element_at(pairs_array, idx + 1))
    return df.withColumn("server", F.col("_pair.server")).withColumn("tool", F.col("_pair.tool"))


# Outcome buckets and their cumulative thresholds against a single uniform draw.
# `deny_rate` is per-row (boosted inside an incident window); the other three
# buckets' widths are fixed, and PASS takes whatever's left.
def with_outcome(df: DataFrame) -> DataFrame:
    deny_rate = F.when(F.col("in_incident_window"), F.lit(INCIDENT_DENY_RATE)).otherwise(
        F.lit(BASELINE_DENY_RATE)
    )
    t1 = deny_rate
    t2 = t1 + F.lit(HITL_APPROVED_RATE)
    t3 = t2 + F.lit(HITL_DENIED_RATE)
    t4 = t3 + F.lit(UPSTREAM_ERROR_RATE)
    draw = F.col("_rand_a")
    bucket = (
        F.when(draw < t1, F.lit("DENY_POLICY"))
        .when(draw < t2, F.lit("HITL_APPROVED"))
        .when(draw < t3, F.lit("HITL_DENIED"))
        .when(draw < t4, F.lit("UPSTREAM_ERROR"))
        .otherwise(F.lit("PASS"))
    )
    return df.withColumn("outcome_bucket", bucket)


def _policy_name_for(server_col: str, kind: str) -> F.Column:
    """Real AML pack policy names for the two real servers (continuity with Day 14's
    actual pack); a generic stand-in name for every other server, since those
    policies were never really written."""
    real = {
        "DENY_POLICY": "aml-rate-limit-sanctions",
        "HITL_APPROVED": "aml-write-hitl-gate",
        "HITL_DENIED": "aml-write-hitl-gate",
    }[kind]
    generic = {
        "DENY_POLICY": "synthetic-denylist",
        "HITL_APPROVED": "synthetic-hitl-gate",
        "HITL_DENIED": "synthetic-hitl-gate",
    }[kind]
    return F.when(F.col(server_col).isin(list(REAL_SERVERS)), F.lit(real)).otherwise(F.lit(generic))


def with_status_decision_and_hitl(df: DataFrame) -> DataFrame:
    bucket = F.col("outcome_bucket")
    status = (
        F.when(bucket.isin("DENY_POLICY", "HITL_DENIED"), F.lit("DENIED"))
        .when(bucket == "UPSTREAM_ERROR", F.lit("UPSTREAM_ERROR"))
        .otherwise(F.lit("COMPLETED"))
    )
    fired_policy = (
        F.when(bucket == "DENY_POLICY", _policy_name_for("server", "DENY_POLICY"))
        .when(bucket == "HITL_APPROVED", _policy_name_for("server", "HITL_APPROVED"))
        .when(bucket == "HITL_DENIED", _policy_name_for("server", "HITL_DENIED"))
    )
    decision_outcome = (
        F.when(bucket == "DENY_POLICY", F.lit("DENY"))
        .when(bucket.isin("HITL_APPROVED", "HITL_DENIED"), F.lit("HOLD"))
        .when(bucket == "UPSTREAM_ERROR", F.lit("UPSTREAM_ERROR"))
        .otherwise(F.lit("PASS"))
    )
    reason = (
        F.when(bucket == "DENY_POLICY", F.lit("rate_limit_exceeded"))
        .when(bucket.isin("HITL_APPROVED", "HITL_DENIED"), F.lit("hitl_required"))
        .when(bucket == "UPSTREAM_ERROR", F.lit("simulated upstream timeout"))
    )
    decision = F.to_json(
        F.struct(
            decision_outcome.alias("outcome"),
            fired_policy.alias("fired_policy"),
            reason.alias("reason"),
        )
    )
    policies_fired = F.when(
        fired_policy.isNotNull(),
        F.to_json(
            F.array(
                F.struct(
                    fired_policy.alias("policy"),
                    F.lit("rate_limit").alias("effect_type"),
                )
            )
        ),
    ).otherwise(F.lit("[]"))

    is_hitl = bucket.isin("HITL_APPROVED", "HITL_DENIED")
    hitl_decision = (
        F.when(bucket == "HITL_APPROVED", F.lit("APPROVED"))
        .when(bucket == "HITL_DENIED", F.lit("DENIED"))
    )
    return (
        df.withColumn("status", status)
        .withColumn("decision", decision)
        .withColumn("policies_fired", policies_fired)
        .withColumn(
            "hitl_ticket_id", F.when(is_hitl, F.expr("uuid()")).otherwise(F.lit(None))
        )
        .withColumn(
            "hitl_reviewer",
            F.when(
                is_hitl,
                F.element_at(
                    F.array(*[F.lit(n) for n in HITL_REVIEWERS]),
                    (F.rand(SEED + 11) * len(HITL_REVIEWERS)).cast("int") + 1,
                ),
            ),
        )
        .withColumn("hitl_decision", hitl_decision)
        .withColumn(
            "hitl_rationale", F.when(is_hitl, F.lit("synthetic reviewer decision"))
        )
    )


def with_latency(df: DataFrame) -> DataFrame:
    # Log-normal-ish: exp(N(log(150), 0.6)) centers around 150ms with a heavy right
    # tail, clipped to a plausible range.
    raw = F.exp(F.randn(SEED + 5) * F.lit(0.6) + F.log(F.lit(150.0)))
    return df.withColumn("latency_ms", F.greatest(F.lit(10), F.least(F.lit(8000), raw)).cast("int"))


def with_tags(df: DataFrame) -> DataFrame:
    is_real_server = F.col("server").isin(list(REAL_SERVERS))
    is_structuring = (F.col("server") == "transaction-graph") & (
        F.col("tool") == "structuring_check"
    )
    # Roughly matches the real pack's structuring hit rate on its own fixture data
    # (Phase 3 Day 14) -- not a statistically derived figure, just a plausible one.
    structuring_flagged = is_structuring & (F.rand(SEED + 6) < 0.3)
    tags = (
        F.when(
            structuring_flagged,
            F.array(
                F.lit("pack:aml"),
                F.lit("regulation:BSA"),
                F.lit("incident:structuring"),
                F.lit("severity:high"),
            ),
        )
        .when(is_real_server, F.array(F.lit("pack:aml"), F.lit("regulation:BSA")))
        .otherwise(F.array())
    )
    return df.withColumn("tags", F.to_json(tags)).withColumn(
        "_structuring_flagged", structuring_flagged
    )


def with_cost(df: DataFrame) -> DataFrame:
    is_cost_bearing = F.rand(SEED + 7) < COST_BEARING_ROW_FRACTION
    prompt_tokens = (F.rand(SEED + 8) * 1500 + 100).cast("int")
    completion_tokens = (F.rand(SEED + 9) * 500 + 20).cast("int")
    provider = F.when(F.rand(SEED + 10) < 0.7, F.lit("groq")).otherwise(F.lit("anthropic"))
    # Rough, illustrative $/token figures -- not any real provider's actual pricing.
    cost_per_1k = F.when(provider == "groq", F.lit(0.0002)).otherwise(F.lit(0.006))
    cost_usd = (prompt_tokens + completion_tokens) / F.lit(1000.0) * cost_per_1k
    tokens_json = F.to_json(
        F.struct(
            prompt_tokens.alias("prompt"),
            completion_tokens.alias("completion"),
            provider.alias("provider"),
            F.round(cost_usd, 6).alias("cost_usd"),
        )
    )
    return df.withColumn("tokens", F.when(is_cost_bearing, tokens_json))


# The final column list every output row (baseline + attack) must have, in the shape
# `load_synthetic_telemetry` expects (JSON-shaped columns pre-serialized to strings
# via `F.to_json`, so the loader can COPY them straight into `jsonb` columns).
OUTPUT_COLUMNS = [
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


def with_identifiers(df: DataFrame) -> DataFrame:
    return (
        df.withColumn("trace_id", F.expr("uuid()"))
        .withColumn("span_id", F.expr("uuid()"))
        # Each row is treated as its own session -- real sessions correlate several
        # calls together, but nothing in the aggregation job examines session
        # continuity, so there's no analytical reason to simulate it.
        .withColumn("session_id", F.expr("uuid()"))
        .withColumn("args_hash", F.lit("synthetic"))
        .withColumn("args_redacted", F.lit('{"synthetic": true}'))
    )


def build_baseline_rows(spark: SparkSession) -> DataFrame:
    hour_buckets = build_hour_buckets(spark)
    bucket_counts = allocate_row_counts(hour_buckets).drop("weight")
    df = build_base_rows(spark, bucket_counts)
    df = with_timestamp(df)
    df = with_agent(df)
    df = with_server_and_tool(spark, df)
    df = with_outcome(df)
    df = with_status_decision_and_hitl(df)
    df = with_latency(df)
    df = with_tags(df)
    df = with_cost(df)
    df = with_identifiers(df)
    return df.select(*OUTPUT_COLUMNS)


def build_attack_rows(spark: SparkSession) -> DataFrame:
    """The one coordinated-attack simulation (Section 10.6): one agent, one tool,
    a short window, almost every call denied on the rate limit -- a burst pattern
    Agent A2's z-score detector (interpose.control_plane) would flag immediately in
    a real deployment."""
    unix_start = _unix_start() + ATTACK_DAY_OFFSET * 86400 + ATTACK_HOUR * 3600
    df = spark.range(ATTACK_CALL_COUNT).withColumnRenamed("id", "_idx")
    df = df.withColumn(
        "timestamp", F.timestamp_seconds(F.lit(unix_start) + (F.col("_idx") % 3600))
    )
    df = df.withColumn("agent_id", F.format_string("agent-%04d", F.lit(ATTACK_AGENT_INDEX)))
    df = df.withColumn("server", F.lit(ATTACK_SERVER)).withColumn("tool", F.lit(ATTACK_TOOL))
    # A handful of these still slip through as PASS -- a real rate limiter has a
    # window, not a hard wall from the first call.
    is_denied = F.rand(SEED + 20) < 0.95
    df = df.withColumn(
        "status", F.when(is_denied, F.lit("DENIED")).otherwise(F.lit("COMPLETED"))
    )
    df = df.withColumn(
        "decision",
        F.when(
            is_denied,
            F.to_json(
                F.struct(
                    F.lit("DENY").alias("outcome"),
                    F.lit("aml-rate-limit-sanctions").alias("fired_policy"),
                    F.lit("rate_limit_exceeded").alias("reason"),
                )
            ),
        ).otherwise(
            F.to_json(
                F.struct(
                    F.lit("PASS").alias("outcome"),
                    F.lit(None).cast("string").alias("fired_policy"),
                    F.lit(None).cast("string").alias("reason"),
                )
            )
        ),
    )
    df = df.withColumn(
        "policies_fired",
        F.when(
            is_denied,
            F.to_json(
                F.array(
                    F.struct(
                        F.lit("aml-rate-limit-sanctions").alias("policy"),
                        F.lit("rate_limit").alias("effect_type"),
                    )
                )
            ),
        ).otherwise(F.lit("[]")),
    )
    df = df.withColumn("latency_ms", (F.rand(SEED + 21) * 40 + 5).cast("int"))
    df = df.withColumn("tokens", F.lit(None).cast("string"))
    df = df.withColumn(
        "tags", F.to_json(F.array(F.lit("pack:aml"), F.lit("regulation:BSA")))
    )
    for col in ("hitl_ticket_id", "hitl_reviewer", "hitl_decision", "hitl_rationale"):
        df = df.withColumn(col, F.lit(None).cast("string"))
    df = with_identifiers(df)
    return df.select(*OUTPUT_COLUMNS)


def write_parquet(df: DataFrame) -> None:
    df = df.withColumn("day", F.to_date("timestamp"))
    (
        df.repartition("day")
        .write.partitionBy("day")
        .mode("overwrite")
        .parquet(str(OUT_DIR))
    )


def main() -> None:
    spark = build_spark()
    try:
        baseline = build_baseline_rows(spark)
        attack = build_attack_rows(spark)
        combined = baseline.unionByName(attack)
        row_count = combined.count()
        logger.info(
            "synthetic_telemetry.generated rows=%d target=%d out_dir=%s",
            row_count,
            TARGET_ROWS,
            OUT_DIR,
        )
        write_parquet(combined)
        logger.info("synthetic_telemetry.written out_dir=%s", OUT_DIR)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
