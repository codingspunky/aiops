from __future__ import annotations

import datetime as dt
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db import Alert, Incident, utcnow

settings = get_settings()

# Optional service dependency graph: service -> adjacent services.
# Populate from your CMDB/topology source; empty disables topology correlation.
TOPOLOGY: dict[str, set[str]] = {}


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def add(self, x: int) -> None:
        self.parent.setdefault(x, x)

    def find(self, x: int) -> int:
        self.add(x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def _related(a: Alert, b: Alert) -> bool:
    """Correlation predicate between two alerts."""
    # 1. same service
    if a.service and b.service and a.service == b.service:
        return True
    # 2. shared value on any configured label key
    for k in settings.correlation_label_keys:
        va, vb = a.labels.get(k), b.labels.get(k)
        if va is not None and va == vb:
            return True
    # 3. topology adjacency
    if a.service and b.service:
        if b.service in TOPOLOGY.get(a.service, ()) or a.service in TOPOLOGY.get(b.service, ()):
            return True
    return False


def _rank_severity(values: Iterable[str]) -> str:
    order = ["info", "warning", "minor", "major", "critical"]
    best = "info"
    for v in values:
        if v in order and order.index(v) > order.index(best):
            best = v
    return best


async def _open_incidents_in_window(db: AsyncSession, since: dt.datetime) -> list[Incident]:
    rows = (
        await db.execute(
            select(Incident)
            .where(Incident.status == "open", Incident.updated_at >= since)
            .options(selectinload(Incident.alerts))
        )
    ).scalars().all()
    return list(rows)


def _title_for(alert: Alert) -> str:
    scope = alert.service or alert.labels.get("cluster") or alert.labels.get("host") or "infra"
    return f"{alert.severity.upper()} on {scope}: {alert.name}"


async def correlate(db: AsyncSession, alert: Alert) -> Incident:
    """Attach a freshly stored alert to an incident, merging incidents if it
    bridges more than one. Returns the resulting incident."""
    window = utcnow() - dt.timedelta(seconds=settings.correlation_window_seconds)
    candidates = await _open_incidents_in_window(db, window)

    # Incidents whose any member alert correlates with the new alert
    matched = [
        inc for inc in candidates
        if any(_related(alert, m) for m in inc.alerts)
    ]

    if not matched:
        inc = Incident(
            title=_title_for(alert),
            severity=alert.severity,
            service=alert.service,
        )
        db.add(inc)
        await db.flush()
        alert.incident_id = inc.id
        await db.flush()
        return inc

    # Merge all matched incidents into the lowest-id one (Union-Find over incident ids)
    uf = UnionFind()
    ids = [inc.id for inc in matched]
    for i in ids[1:]:
        uf.union(ids[0], i)
    primary_id = uf.find(ids[0])
    primary = next(inc for inc in matched if inc.id == primary_id)

    for inc in matched:
        if inc.id == primary.id:
            continue
        for m in list(inc.alerts):
            m.incident_id = primary.id
        inc.status = "merged"

    alert.incident_id = primary.id
    severities = [a.severity for a in primary.alerts] + [alert.severity]
    primary.severity = _rank_severity(severities)
    primary.updated_at = utcnow()
    await db.flush()
    return primary
