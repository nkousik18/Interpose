# Synthetic telemetry, and why the dashboards query Postgres, not Prometheus

Follows [[14-spark-and-pyspark]] and [[29-embedded-analytics-with-duckdb]] (Spark and
DuckDB, the project's two "bulk data" tools) and [[26-helm-and-the-interpose-chart]]
(the Grafana deployment this day rewires). Phase 3 Day 15;
`docs/INTERPOSE_SCOPING.md` Sections 10.6, 12.4 — the Spark analytics demo and the
four Grafana dashboards.

## A dashboard architecture question the code answered before any panel got built

Day 9 provisioned all four dashboards as Prometheus panels — reasonable at the time,
since Section 12.3 does describe real golden-signal metrics
(`interpose_tool_calls_total` and friends) as Interpose's eventual observability
layer. But by Day 15, checking rather than assuming: no Prometheus is deployed
anywhere in this project, nothing exports `/metrics`, and there wasn't even a
Grafana *datasource* configured for the placeholder Prometheus UID the old dashboards
referenced — they would have shown a connection error, not just empty panels.

Section 10.6, separately, describes exactly what this day's roadmap items actually
ask for: a Spark job generating synthetic telemetry into a **Postgres** table, a
second Spark job aggregating it into **Postgres** summary tables. That's a
Postgres-centric design, and it's one this project can build today with zero new
infrastructure. So all four dashboards were rebuilt against a Postgres datasource
instead — Dashboard 1 (Gateway Health), the one Section 12.3 most clearly describes
as Prometheus's job, is *approximated* from the audit log's own `status`/`latency_ms`
columns rather than faked or left broken. Real data, honestly sourced differently
than the doc's metric names imply — named explicitly in the dashboard's own "how to
read" panel, not left implicit.

## Generating 10M rows without a join that doesn't scale

`generate_synthetic_telemetry.py` needs a non-uniform time distribution (diurnal
cycle, weekend dip, 3 incident spikes) across ~10M rows. The naive way — draw a
random timestamp per row, weighted by an hourly lookup table via a range join — would
force Spark into a broadcast *nested-loop* join (weights don't have an equality key),
comparing 10M rows against every one of 672 hourly buckets. The actual implementation
computes each bucket's target row count *once*, on the 672-row bucket table alone
(`allocate_row_counts`), then turns each bucket directly into that many rows via
`F.explode(F.sequence(...))` — no join against the full row count at all. Real
result: 10M rows generated, with a real 4-week diurnal/weekly pattern and 3 named
incident windows, in under a minute on a laptop.

## Why Spark writes Parquet, then a separate step COPYs into Postgres

The obvious move — `df.write.format("jdbc")...` straight into Postgres — was tried
first. It failed with `No suitable driver`: `spark.jars.packages` needs Ivy to fetch
the Postgres JDBC driver from Maven at runtime, and despite this environment having
real internet access (confirmed directly), Ivy's resolution came back empty with no
error, for reasons not worth chasing down for a one-time demo loader. There's also no
existing precedent in this project for Spark writing to Postgres directly — the audit
store itself writes via SQLAlchemy (concept 18), not Spark. So the loader
(`load_synthetic_telemetry.py`) does the simpler thing instead: Spark writes Parquet
(as `subsample_aml.py` already does, concept 14), and a plain Python step reads it
back with `pyarrow` and `COPY`s it into Postgres in batches — one fewer moving part,
consistent with how every other Postgres write in this project already happens.
10M rows loaded this way in about 3.5 minutes.

## Two real aggregation bugs, caught by looking at the row counts, not assuming correctness

**`agg_cost_daily` grouped by `{day, agent_id, tool, provider}` first, and produced
918,819 rows** — 500 agents × ~100 tools × 2 providers × 28 days, most combinations
appearing only a handful of times. A table nearly a million rows isn't
"dashboard-ready" in any useful sense, caught only by actually counting the output
rather than trusting that a query which ran without error was a query that produced
something useful. Fixed by dropping `tool` from the grouping — Section 12.4's own
panel list only ever asks for cost "per agent" and "per provider," never both
simultaneously with a third dimension.

**`agg_aml_pack_daily`'s `mark_investigated_pending` column double-counted with
`_approved`** — it summed every `COMPLETED` row, which includes the HITL-approved
ones, rather than the mutually exclusive "completed with no HITL decision at all."
Renamed to `mark_investigated_auto_passed` and fixed to require
`hitl_decision IS NULL`. Documented alongside it: in the real AML pack,
`aml-write-hitl-gate` (Phase 3 Day 14) holds *every* `mark_investigated` call
unconditionally, so this bucket would always be empty for real traffic — it's
nonzero here only because the synthetic generator applies its generic outcome mix
uniformly across every tool, including ones a real policy pack would never let reach
a plain PASS.

## Related

- [[14-spark-and-pyspark]]
- [[29-embedded-analytics-with-duckdb]]
- [[26-helm-and-the-interpose-chart]]
- [[31-response-side-policy-evaluation-and-the-aml-pack]]
