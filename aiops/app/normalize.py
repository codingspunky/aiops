from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any

from app.schemas import CanonicalAlert


def _parse_ts(value: Any) -> dt.datetime:
    if isinstance(value, dt.datetime):
        ts = value
    elif isinstance(value, (int, float)):
        ts = dt.datetime.fromtimestamp(float(value), tz=dt.timezone.utc)
    elif isinstance(value, str) and value:
        s = value.replace("Z", "+00:00")
        try:
            ts = dt.datetime.fromisoformat(s)
        except ValueError:
            ts = dt.datetime.now(dt.timezone.utc)
    else:
        ts = dt.datetime.now(dt.timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return ts


def compute_fingerprint(name: str, service: str | None, labels: dict[str, Any]) -> str:
    """Stable identity for dedup. Excludes timestamps/values."""
    key_parts = [name, service or ""]
    for k in sorted(labels):
        if k in {"value", "timestamp", "startsAt", "endsAt"}:
            continue
        key_parts.append(f"{k}={labels[k]}")
    raw = "|".join(key_parts)
    return hashlib.sha1(raw.encode()).hexdigest()


def _finalize(alert: CanonicalAlert) -> CanonicalAlert:
    if not alert.fingerprint:
        alert.fingerprint = compute_fingerprint(alert.name, alert.service, alert.labels)
    return alert


# --- Source adapters -------------------------------------------------------

def from_prometheus(payload: dict[str, Any]) -> list[CanonicalAlert]:
    """Alertmanager webhook payload: {"alerts": [{labels, annotations, ...}]}."""
    out: list[CanonicalAlert] = []
    for a in payload.get("alerts", [payload]):
        labels = dict(a.get("labels", {}))
        ann = a.get("annotations", {})
        name = labels.get("alertname") or a.get("name") or "unknown"
        service = labels.get("service") or labels.get("job")
        out.append(_finalize(CanonicalAlert(
            source="prometheus",
            name=name,
            service=service,
            severity=labels.get("severity", "info"),
            status=a.get("status", "firing"),
            summary=ann.get("summary") or ann.get("description"),
            labels=labels,
            starts_at=_parse_ts(a.get("startsAt")),
            fingerprint=a.get("fingerprint"),
        )))
    return out


def from_grafana(payload: dict[str, Any]) -> list[CanonicalAlert]:
    """Grafana unified-alerting webhook."""
    out: list[CanonicalAlert] = []
    common = payload.get("commonLabels", {})
    for a in payload.get("alerts", [payload]):
        labels = {**common, **a.get("labels", {})}
        ann = a.get("annotations", {})
        out.append(_finalize(CanonicalAlert(
            source="grafana",
            name=labels.get("alertname") or payload.get("title", "unknown"),
            service=labels.get("service"),
            severity=labels.get("severity", payload.get("severity", "info")),
            status=a.get("status", payload.get("status", "firing")),
            summary=ann.get("summary") or ann.get("description"),
            labels=labels,
            starts_at=_parse_ts(a.get("startsAt")),
        )))
    return out


def from_csv_row(row: dict[str, Any]) -> CanonicalAlert:
    """One CSV row -> one alert. Reserved cols promote to fields; rest become labels."""
    reserved = {"source", "name", "service", "severity", "status", "summary", "starts_at"}
    labels = {k: v for k, v in row.items() if k not in reserved and v not in (None, "")}
    return _finalize(CanonicalAlert(
        source=row.get("source", "csv"),
        name=row.get("name", "unknown"),
        service=row.get("service") or None,
        severity=row.get("severity", "info"),
        status=row.get("status", "firing"),
        summary=row.get("summary"),
        labels=labels,
        starts_at=_parse_ts(row.get("starts_at")),
    ))


NORMALIZERS = {
    "prometheus": from_prometheus,
    "grafana": from_grafana,
}
