"""Run: python smoke_test.py  (uses SQLite + mock LLM, no server/keys needed)."""
import asyncio
import datetime as dt
import json

from app.db import SessionLocal, init_db
from app.normalize import from_prometheus
from app.pipeline import process_alerts


def _alert(name, service, severity, cluster, minutes_ago=0):
    ts = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes_ago)).isoformat()
    return {
        "status": "firing",
        "labels": {"alertname": name, "service": service, "severity": severity, "cluster": cluster},
        "annotations": {"summary": f"{name} on {service}"},
        "startsAt": ts,
    }


async def main():
    await init_db()

    # Three alerts: two share a service, one shares the cluster -> should correlate into ONE incident.
    payload = {"alerts": [
        _alert("HighLatency", "checkout", "critical", "prod-1", 2),
        _alert("ErrorRateHigh", "checkout", "warning", "prod-1", 1),
        _alert("PodRestart", "payments", "major", "prod-1", 0),
    ]}
    # An unrelated alert on a different cluster/service -> separate incident.
    other = {"alerts": [_alert("DiskFull", "logging", "warning", "prod-2", 0)]}

    async with SessionLocal() as db:
        r1 = await process_alerts(db, "prometheus", payload, from_prometheus(payload))
        r2 = await process_alerts(db, "prometheus", other, from_prometheus(other))

    print("ingest 1:", json.dumps(r1))
    print("ingest 2:", json.dumps(r2))

    # Dedup check: re-send the same first alert.
    dup = {"alerts": [_alert("HighLatency", "checkout", "critical", "prod-1", 2)]}
    async with SessionLocal() as db:
        r3 = await process_alerts(db, "prometheus", dup, from_prometheus(dup))
    print("ingest 3 (dup):", json.dumps(r3))

    from app.db import Incident
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    async with SessionLocal() as db:
        incs = (await db.execute(
            select(Incident).options(selectinload(Incident.alerts), selectinload(Incident.rca))
        )).scalars().all()
        print(f"\n=== {len(incs)} incidents ===")
        for inc in incs:
            print(f"\n[{inc.id}] {inc.title}  status={inc.status} severity={inc.severity}")
            for a in inc.alerts:
                print(f"    - {a.name} ({a.service}) count={a.count}")
            if inc.rca:
                print(f"    RCA: {inc.rca.summary}")
                print(f"    Recs: {inc.rca.recommendations[:2]}")


if __name__ == "__main__":
    asyncio.run(main())
