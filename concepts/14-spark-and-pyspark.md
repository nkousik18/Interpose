# Spark and PySpark

## What Spark is

Apache Spark is a distributed data-processing engine: it splits a large dataset into
partitions, spreads the work of transforming them across many machines (or many CPU
cores on one machine), and combines the results. It was built for the case where a
dataset doesn't fit comfortably in one process's memory, or where a computation
benefits from parallelism.

**PySpark** is the Python API to Spark. Spark itself is written in Scala and runs on
the Java Virtual Machine (JVM); PySpark's Python objects are a thin wrapper that talks
to a real JVM process underneath via a bridge library called `py4j`. That's why
installing PySpark alone isn't enough — Spark needs an actual Java runtime to launch
against, which is a new dependency for this project (everything else so far has been
pure Python, containers, or Go-based CLI tools).

## Why Interpose uses it at all, on a laptop-sized job

Two jobs in the scoping doc call for Spark:

1. **Subsampling the IBM AML dataset** (Section 10.3) — trimming ~32M raw transaction
   rows down to the ~500K-account slice the demo actually runs against.
2. **Aggregating gateway telemetry** (Section 11.7, later phase) — turning a
   synthetic 10M-record audit corpus into governance dashboards.

Neither job strictly *needs* a distributed engine at this data size — DuckDB or Polars
would do the job on a single machine, arguably with less ceremony. Spark is used
anyway because it's an explicit resume-gap skill this project is built to close (see
scoping doc Section 4.6): the goal is to be able to speak credibly about Spark job
design, not just to move some CSV rows around. `local[*]` mode (see below) lets us get
real Spark API experience without needing a cluster.

## Local mode vs. a real cluster

Spark can run in a few "master" configurations. The one used here is `local[*]`: Spark
runs entirely inside one process on this laptop, and `*` tells it to use all available
CPU cores as if they were separate worker machines. There's no real cluster, no
network shuffle between physical nodes — but the same `SparkSession` API, the same
partitioning and lazy-execution model, and the same code you'd point at a real cluster
all apply. Later (Section 11.7, Phase 2+), the same jobs are meant to run on Kubernetes
via the Spark Operator, which is a real multi-pod cluster — `local[*]` is the
development-time stand-in for that.

## The Java dependency, concretely

Spark 4.x (the current PyPI release, newer than the 3.5 the scoping doc names) needs a
JDK Spark itself has been tested against — not just any Java. This machine had
Homebrew's default `openjdk` at version 25, which is too new to be a safe bet for
Spark compatibility, so a second, older JDK was installed side by side:
`brew install openjdk@17`. Homebrew installs it "keg-only" (not linked to the
system `java` command) specifically so it doesn't fight with other Java installs on
the machine.

PySpark finds its JVM via the `JAVA_HOME` environment variable, read at the moment a
`SparkSession` is created (not at import time). Rather than requiring every session or
script to `export JAVA_HOME=...` by hand, `src/interpose/analytics/spark_env.py`
provides `ensure_java_home()`, which sets it (only if unset) to the `openjdk@17` path
and raises a clear error if that install is missing. Every analytics job should call
this before constructing a `SparkSession`.

## Where this lives in the project

- Dependency: `pyspark` lives in its own `analytics` dependency group in
  `pyproject.toml` (`uv sync --group analytics` / `uv run --group analytics ...`),
  not the default install — it's only needed for the batch jobs in
  `src/interpose/analytics/` (component C8 in the scoping doc), not the gateway
  itself.
- Helper: `src/interpose/analytics/spark_env.py::ensure_java_home()`.
- First real job: `src/interpose/analytics/subsample_aml.py`, the AML dataset
  subsampling script (scoping doc Section 10.3) — ran successfully against the full
  31.9M-row HI-Medium CSV in `local[*]` mode in about 3.5 minutes on this laptop.

## A DataFrame pattern worth remembering: broadcast + semi-join

The subsampling job needed to filter 32M transactions down to only those where both
the sender and receiver account are in a 500K-account sample set. The Spark-idiomatic
way to do a large-table-filtered-by-small-set operation like this is a **broadcast
join**: instead of shuffling the 32M-row table across the cluster to match it against
the 500K-row sample, Spark ships the small side (the 500K accounts, a few MB) to every
worker and joins locally. Combined with a **left-semi join** (`"left_semi"` — keep
only matching rows from the left table, don't add any columns from the right), this
expresses "keep every transaction where the account is in this set" without ever
collecting the big table to one place or writing a slow row-by-row Python check. This
pattern — broadcast the small side, semi-join to filter — generalizes to any
"filter big data by membership in a small reference set" problem in Spark.
