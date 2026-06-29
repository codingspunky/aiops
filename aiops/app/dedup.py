from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import Alert, utcnow
from app.schemas import CanonicalAlert

settings = get_settings()


async def dedup_or_insert(db: AsyncSession, ca: CanonicalAlert) -> tuple[Alert, bool]:
    """Return (alert, is_new). If an active alert with the same fingerprint was seen
    within the suppression window, bump its count/last_seen and return is_new=False."""
    window_start = utcnow() - dt.timedelta(seconds=settings.dedup_suppress_seconds)

    existing = (
        await db.execute(
            select(Alert)
            .where(
                Alert.fingerprint == ca.fingerprint,
                Alert.status == "firing",
                Alert.last_seen_at >= window_start,
            )
            .order_by(Alert.last_seen_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.count += 1
        existing.last_seen_at = utcnow()
        if ca.status == "resolved":
            existing.status = "resolved"
        await db.flush()
        return existing, False

    alert = Alert(
        fingerprint=ca.fingerprint,
        source=ca.source,
        name=ca.name,
        service=ca.service,
        severity=ca.severity,
        status=ca.status,
        summary=ca.summary,
        labels=ca.labels,
        starts_at=ca.starts_at,
        last_seen_at=utcnow(),
    )
    db.add(alert)
    await db.flush()
    return alert, True
