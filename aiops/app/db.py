from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class RawAlert(Base):
    """Untouched payload as received, for audit/replay."""
    __tablename__ = "raw_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    received_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Alert(Base):
    """Normalized, canonical alert."""
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(128), index=True)
    source: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(256))
    service: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    severity: Mapped[str] = mapped_column(String(16), default="info")
    status: Mapped[str] = mapped_column(String(16), default="firing")  # firing|resolved
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    labels: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    starts_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    count: Mapped[int] = mapped_column(Integer, default=1)  # bumped by dedup
    last_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    incident_id: Mapped[int | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    incident: Mapped[Incident | None] = relationship(back_populates="alerts")


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|resolved
    severity: Mapped[str] = mapped_column(String(16), default="info")
    service: Mapped[str | None] = mapped_column(String(128), nullable=True)
    opened_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    alerts: Mapped[list[Alert]] = relationship(
        back_populates="incident", order_by="Alert.starts_at"
    )
    rca: Mapped[RCAReport | None] = relationship(
        back_populates="incident", uselist=False
    )


class RCAReport(Base):
    __tablename__ = "rca_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), unique=True)
    root_cause: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    contributing_factors: Mapped[list[Any]] = mapped_column(JSON, default=list)
    recommendations: Mapped[list[Any]] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(64))
    generated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    incident: Mapped[Incident] = relationship(back_populates="rca")


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
