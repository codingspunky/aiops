from __future__ import annotations

"""Main entry point for the AIOps Correlation Engine FastAPI application.

Provides route definitions for health checks, data ingestion, and incident
management. The FastAPI app is instantiated with a lifespan that initializes
the database."""

import csv
import io
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import Incident, SessionLocal, init_db
from app.normalize import from_csv_row, from_grafana, from_prometheus
from app.pipeline import generate_rca, process_alerts
from app.schemas import IncidentOut, IngestResult


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="AIOps Correlation Engine", lifespan=lifespan)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


async def get_db() -> AsyncSession:
    async with SessionLocal() as db:
        yield db


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ingest/prometheus", response_model=IngestResult)
async def ingest_prometheus(payload: dict[str, Any], db: AsyncSession = Depends(get_db)):
    cas = from_prometheus(payload)
    return await process_alerts(db, "prometheus", payload, cas)


@app.post("/ingest/grafana", response_model=IngestResult)
async def ingest_grafana(payload: dict[str, Any], db: AsyncSession = Depends(get_db)):
    cas = from_grafana(payload)
    return await process_alerts(db, "grafana", payload, cas)


@app.post("/ingest/csv", response_model=IngestResult)
async def ingest_csv(file: UploadFile, db: AsyncSession = Depends(get_db)):
    text = (await file.read()).decode()
    rows = list(csv.DictReader(io.StringIO(text)))
    cas = [from_csv_row(r) for r in rows]
    return await process_alerts(db, "csv", {"rows": len(rows)}, cas)


@app.get("/incidents", response_model=list[IncidentOut])
async def list_incidents(status: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Incident).options(
        selectinload(Incident.alerts), selectinload(Incident.rca)
    ).order_by(Incident.updated_at.desc())
    if status:
        stmt = stmt.where(Incident.status == status)
    rows = (await db.execute(stmt)).scalars().all()
    return rows


@app.get("/incidents/{incident_id}", response_model=IncidentOut)
async def get_incident(incident_id: int, db: AsyncSession = Depends(get_db)):
    inc = (
        await db.execute(
            select(Incident).where(Incident.id == incident_id).options(
                selectinload(Incident.alerts), selectinload(Incident.rca)
            )
        )
    ).scalar_one_or_none()
    if inc is None:
        raise HTTPException(404, "incident not found")
    return inc


@app.post("/incidents/{incident_id}/rca", response_model=IncidentOut)
async def rerun_rca(incident_id: int, db: AsyncSession = Depends(get_db)):
    await generate_rca(db, incident_id)
    await db.commit()
    return await get_incident(incident_id, db)
