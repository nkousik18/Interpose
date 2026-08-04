"""Unit test for interpose.analytics.load_synthetic_telemetry -- the one piece of
that module that's pure Python, no Spark and no live Postgres involved. The Spark
generation/aggregation logic itself is verified live (a full 10M-row run, spot-checked
against real distributions), not unit-tested -- same established pattern as
`interpose.analytics.subsample_aml`, which has no unit tests either.
"""

from interpose.analytics.load_synthetic_telemetry import _to_psycopg_dsn


def test_strips_the_psycopg_dialect_suffix() -> None:
    url = "postgresql+psycopg://interpose:interpose_dev@localhost:5433/interpose"
    assert _to_psycopg_dsn(url) == "postgresql://interpose:interpose_dev@localhost:5433/interpose"


def test_leaves_an_already_plain_url_unchanged() -> None:
    url = "postgresql://interpose:interpose_dev@localhost:5433/interpose"
    assert _to_psycopg_dsn(url) == url
