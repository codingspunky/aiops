from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.correlate import correlate
from app.db import Alert, Incident, RawAlert, RCAReport, utcnow
from app.dedup import dedup_or_insert
from app.rca_agent import run_rca
from app.schemas import CanonicalAlert

settings = get_settings()


def _serialize_incident(inc: Incident) -> dict:
    return {
        "id": inc.id,
        "title": inc.title,
        "severity": inc.severity,
        "service": inc.service,
        "alerts": [
            {
                "name": a.name,
                "severity": a.severity,
                "service": a.service,
                "labels": a.labels,
                "starts_at": a.starts_at.isoformat(),
                "count": a.count,
            }
            for a in inc.alerts
        ],
    }


async def generate_rca(db: AsyncSession, incident_id: int) -> RCAReport:
    inc = (
        await db.execute(
            select(Incident).where(Incident.id == incident_id).options(selectinload(Incident.alerts))
        )
    ).scalar_one()

    result = await run_rca(_serialize_incident(inc))

    report = (
        await db.execute(select(RCAReport).where(RCAReport.incident_id == incident_id))
    ).scalar_one_or_none()
    if report is None:
        report = RCAReport(incident_id=incident_id)
        db.add(report)

    report.root_cause = result["root_cause"]
    report.confidence = result["confidence"]
    report.contributing_factors = result["contributing_factors"]
    report.recommendations = result["recommendations"]
    report.summary = result["summary"]
    report.model = result["model"]
    report.generated_at = utcnow()
    await db.flush()
    return report


async def process_alerts(
    db: AsyncSession, source: str, raw_payload: dict, canonicals: list[CanonicalAlert]
) -> dict:
    db.add(RawAlert(source=source, payload=raw_payload))

    new_ids: list[int] = []
    incident_ids: set[int] = set()
    deduped = 0

    for ca in canonicals:
        alert, is_new = await dedup_or_insert(db, ca)
        if not is_new:
            deduped += 1
            if alert.incident_id:
                incident_ids.add(alert.incident_id)
            continue
        incident = await correlate(db, alert)
        new_ids.append(alert.id)
        incident_ids.add(incident.id)

    await db.commit()

    if settings.rca_auto:
        for iid in incident_ids:
            await generate_rca(db, iid)
        await db.commit()

    return {
        "accepted": len(canonicals),
        "deduplicated": deduped,
        "new_alerts": new_ids,
        "incident_ids": sorted(incident_ids),
    }
