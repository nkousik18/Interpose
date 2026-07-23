"""Subsamples the IBM AML HI-Medium dataset to ~500K accounts.

Per docs/INTERPOSE_SCOPING.md Section 10.3: random-select ~500K accounts, retain
transactions where both parties are in the sample, verify the laundering ratio and
graph connectivity survive.

Deviation from the doc's literal procedure, deliberate: pure uniform random sampling
of accounts would almost certainly break at least one of the 2,756 labeled laundering
patterns in HI-Medium_Patterns.txt -- each is a short chain of specific accounts, and
the odds that all of them land together in an independently-drawn sample covering
~24% of the ~2.08M-account universe are near zero. So every account touched by a
labeled laundering transaction is included unconditionally; the remaining slots up to
TARGET_ACCOUNTS are filled by a seeded uniform random draw over everything else. This
keeps the seed/reproducibility requirement and guarantees pattern connectivity by
construction instead of leaving it to chance.

Run with: uv run --group analytics python -m interpose.analytics.subsample_aml
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from interpose.analytics.spark_env import ensure_java_home

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RAW_DIR = Path.home() / ".interpose" / "data" / "ibm-aml-raw"
OUT_DIR = Path.home() / ".interpose" / "data" / "ibm-aml"
TRANS_CSV = RAW_DIR / "HI-Medium_Trans.csv"
ACCOUNTS_CSV = RAW_DIR / "HI-Medium_accounts.csv"
PATTERNS_TXT = RAW_DIR / "HI-Medium_Patterns.txt"

SEED = 42
TARGET_ACCOUNTS = 500_000
VERIFY_PATTERN_COUNT = 100

TRANS_COLUMNS = [
    "timestamp",
    "from_bank",
    "from_account",
    "to_bank",
    "to_account",
    "amount_received",
    "receiving_currency",
    "amount_paid",
    "payment_currency",
    "payment_format",
    "is_laundering",
]


def build_spark() -> SparkSession:
    ensure_java_home()
    return (
        SparkSession.builder.appName("interpose-aml-subsample")
        .master("local[*]")
        .config("spark.driver.memory", "6g")
        .config("spark.sql.shuffle.partitions", "16")
        .getOrCreate()
    )


def load_transactions(spark: SparkSession) -> DataFrame:
    # The raw header has two columns both literally named "Account" (from-account,
    # to-account); Spark auto-disambiguates them on read, so we just rename by
    # position afterward rather than fighting the header.
    df = spark.read.option("header", True).csv(str(TRANS_CSV)).toDF(*TRANS_COLUMNS)
    return (
        df.withColumn("timestamp", F.to_timestamp("timestamp", "yyyy/MM/dd HH:mm"))
        .withColumn("amount_received", F.col("amount_received").cast("double"))
        .withColumn("amount_paid", F.col("amount_paid").cast("double"))
        .withColumn("is_laundering", F.col("is_laundering").cast("int"))
        .withColumn("from_id", F.concat_ws(":", F.col("from_bank").cast("int"), "from_account"))
        .withColumn("to_id", F.concat_ws(":", F.col("to_bank").cast("int"), "to_account"))
    )


def load_accounts(spark: SparkSession) -> DataFrame:
    df = spark.read.option("header", True).csv(str(ACCOUNTS_CSV))
    df = df.toDF("bank_name", "bank_id", "account_number", "entity_id", "entity_name")
    return df.withColumn(
        "account_id", F.concat_ws(":", F.col("bank_id").cast("int"), "account_number")
    )


def select_sample_accounts(df: DataFrame) -> tuple[DataFrame, dict[str, int]]:
    laundering = df.filter(F.col("is_laundering") == 1)
    must_include = (
        laundering.select(F.col("from_id").alias("account_id"))
        .union(laundering.select(F.col("to_id").alias("account_id")))
        .distinct()
    )
    must_include_count = must_include.count()

    universe = (
        df.select(F.col("from_id").alias("account_id"))
        .union(df.select(F.col("to_id").alias("account_id")))
        .distinct()
    )
    universe_count = universe.count()
    remaining_pool = universe.join(must_include, on="account_id", how="left_anti")
    remaining_needed = TARGET_ACCOUNTS - must_include_count

    if remaining_needed <= 0:
        logger.warning(
            "laundering-labeled accounts alone (%d) already meet or exceed the "
            "target of %d; sampling no additional background accounts",
            must_include_count,
            TARGET_ACCOUNTS,
        )
        sample = must_include
    else:
        topped_up = (
            remaining_pool.withColumn("_r", F.rand(seed=SEED))
            .orderBy("_r")
            .limit(remaining_needed)
            .select("account_id")
        )
        sample = must_include.union(topped_up).distinct()

    stats = {
        "account_universe": universe_count,
        "must_include_accounts": must_include_count,
        "sampled_accounts": sample.count(),
    }
    logger.info("account sampling stats: %s", stats)
    return sample, stats


def filter_transactions_to_sample(df: DataFrame, sample_accounts: DataFrame) -> DataFrame:
    sample_b = F.broadcast(sample_accounts)
    return df.join(sample_b, df.from_id == sample_b.account_id, "left_semi").join(
        sample_b, df.to_id == sample_b.account_id, "left_semi"
    )


def load_top_patterns(limit: int = VERIFY_PATTERN_COUNT) -> list[dict[str, Any]]:
    """Parse the first `limit` BEGIN/END laundering-pattern blocks from Patterns.txt."""
    patterns: list[dict[str, Any]] = []
    typology = None
    rows: list[dict[str, str]] = []
    with open(PATTERNS_TXT) as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("BEGIN LAUNDERING ATTEMPT"):
                typology = line.split("-", 1)[1].strip()
                rows = []
            elif line.startswith("END LAUNDERING ATTEMPT"):
                patterns.append({"typology": typology, "rows": rows})
                if len(patterns) >= limit:
                    break
            else:
                parts = line.split(",")
                rows.append(
                    {
                        "from_id": f"{int(parts[1])}:{parts[2]}",
                        "to_id": f"{int(parts[3])}:{parts[4]}",
                    }
                )
    return patterns


def verify_pattern_connectivity(
    sample_account_ids: set[str], patterns: list[dict[str, Any]]
) -> dict[str, Any]:
    broken = []
    for i, pattern in enumerate(patterns):
        accounts = {r["from_id"] for r in pattern["rows"]} | {r["to_id"] for r in pattern["rows"]}
        if not accounts <= sample_account_ids:
            broken.append(
                {
                    "index": i,
                    "typology": pattern["typology"],
                    "missing_accounts": sorted(accounts - sample_account_ids),
                }
            )
    return {
        "checked": len(patterns),
        "fully_preserved": len(patterns) - len(broken),
        "broken": broken,
    }


def main() -> None:
    spark = build_spark()
    try:
        logger.info("loading transactions from %s", TRANS_CSV)
        trans = load_transactions(spark).cache()
        total_txns = trans.count()
        laundering_txns = trans.filter(F.col("is_laundering") == 1).count()
        logger.info(
            "raw dataset: total_txns=%d laundering_txns=%d ratio_pct=%.4f",
            total_txns,
            laundering_txns,
            laundering_txns / total_txns * 100,
        )

        sample_accounts, account_stats = select_sample_accounts(trans)
        sample_accounts = sample_accounts.cache()

        logger.info("filtering transactions to the sampled account set")
        filtered = filter_transactions_to_sample(trans, sample_accounts).cache()
        filtered_total = filtered.count()
        filtered_laundering = filtered.filter(F.col("is_laundering") == 1).count()
        filtered_ratio = filtered_laundering / filtered_total * 100

        logger.info(
            "filtered dataset: total_txns=%d laundering_txns=%d ratio_pct=%.4f",
            filtered_total,
            filtered_laundering,
            filtered_ratio,
        )
        if filtered_laundering != laundering_txns:
            raise RuntimeError(
                f"expected all {laundering_txns} laundering transactions to survive "
                f"filtering (their accounts are all in the must-include set), but "
                f"only {filtered_laundering} did -- sampling logic has a bug"
            )

        logger.info(
            "verifying laundering-pattern connectivity for top %d patterns", VERIFY_PATTERN_COUNT
        )
        sample_account_ids = {
            row.account_id for row in sample_accounts.select("account_id").collect()
        }
        patterns = load_top_patterns(VERIFY_PATTERN_COUNT)
        connectivity = verify_pattern_connectivity(sample_account_ids, patterns)
        logger.info(
            "connectivity verification: %s",
            {k: v for k, v in connectivity.items() if k != "broken"},
        )
        if connectivity["broken"]:
            raise RuntimeError(
                f"{len(connectivity['broken'])} of {connectivity['checked']} checked "
                f"laundering patterns lost connectivity in the sample: "
                f"{connectivity['broken'][:3]}"
            )

        logger.info(
            "writing filtered transactions to %s (partitioned by month)", OUT_DIR / "transactions"
        )
        (
            filtered.withColumn("month", F.date_format("timestamp", "yyyy-MM"))
            .write.mode("overwrite")
            .partitionBy("month")
            .parquet(str(OUT_DIR / "transactions"))
        )

        logger.info("writing subsampled account metadata to %s", OUT_DIR / "accounts")
        accounts = load_accounts(spark)
        sample_b = F.broadcast(sample_accounts)
        (
            accounts.join(sample_b, accounts.account_id == sample_b.account_id, "left_semi")
            .write.mode("overwrite")
            .parquet(str(OUT_DIR / "accounts"))
        )

        report = {
            "seed": SEED,
            "target_accounts": TARGET_ACCOUNTS,
            "raw": {
                "total_txns": total_txns,
                "laundering_txns": laundering_txns,
                "laundering_ratio_pct": laundering_txns / total_txns * 100,
            },
            "sampled": {
                **account_stats,
                "total_txns": filtered_total,
                "laundering_txns": filtered_laundering,
                "laundering_ratio_pct": filtered_ratio,
            },
            "pattern_connectivity": connectivity,
        }
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = OUT_DIR / "subsample_report.json"
        report_path.write_text(json.dumps(report, indent=2))
        logger.info("wrote subsampling report to %s", report_path)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
