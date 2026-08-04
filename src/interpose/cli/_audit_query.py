"""Shared audit-log query helper for the `interpose` CLI -- pulled out of
`main.py` specifically so `demo.py` can reuse it without a circular import
(`main.py` registers `demo_app`, so `demo.py` can't import back from `main.py`).
"""

from __future__ import annotations

from sqlalchemy import create_engine, select

from interpose.audit.models import AuditEntry


def fetch_all_entries(database_url: str) -> list[dict]:
    """Every audit entry, ordered by id (= chain order). Not filtered by date here --
    see verify_audit's docstring for why the whole chain always gets verified."""
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(select(AuditEntry).order_by(AuditEntry.id)).all()
            columns = [c.name for c in AuditEntry.__table__.columns]
            return [dict(zip(columns, row, strict=True)) for row in rows]
    finally:
        engine.dispose()
