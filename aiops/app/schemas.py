from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, Field


class CanonicalAlert(BaseModel):
    """Source-agnostic alert produced by normalization."""
    source: str
    name: str
    service: str | None = None
    severity: str = "info"
    status: str = "firing"
    summary: str | None = None
    labels: dict[str, Any] = Field(default_factory=dict)
    starts_at: dt.datetime
    fingerprint: str | None = None  # filled by normalizer if absent


class AlertOut(BaseModel):
    id: int
    fingerprint: str
    source: str
    name: str
    service: str | None
    severity: str
    status: str
    summary: str | None
    labels: dict[str, Any]
    starts_at: dt.datetime
    count: int
    incident_id: int | None

    class Config:
        from_attributes = True


class RCAOut(BaseModel):
    root_cause: str
    confidence: float
    contributing_factors: list[Any]
    recommendations: list[Any]
    summary: str
    model: str
    generated_at: dt.datetime

    class Config:
        from_attributes = True


class IncidentOut(BaseModel):
    id: int
    title: str
    status: str
    severity: str
    service: str | None
    opened_at: dt.datetime
    updated_at: dt.datetime
    alerts: list[AlertOut] = []
    rca: RCAOut | None = None

    class Config:
        from_attributes = True


class IngestResult(BaseModel):
    accepted: int
    deduplicated: int
    new_alerts: list[int]
    incident_ids: list[int]
