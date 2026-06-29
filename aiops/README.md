# AIOps Correlation Engine

Vendor-neutral alert correlation + LLM RCA pipeline. Vertical slice of the
architecture: ingest → normalize → dedup → correlate → store → RCA agent → JSON API.

## Pipeline mapping

| Stage | File |
|-------|------|
| Alert Ingestion API (FastAPI) | `app/main.py` |
| Normalization (Prometheus/Grafana/CSV adapters) | `app/normalize.py` |
| Deduplication (fingerprint + suppression window) | `app/dedup.py` |
| Correlation Engine (Union-Find over time/label/topology rules) | `app/correlate.py` |
| Incident Store (SQLAlchemy async, SQLite/Postgres) | `app/db.py` |
| RCA AI Agent (LangGraph: gather → analyze → recommend) | `app/rca_agent.py` |
| Orchestration | `app/pipeline.py` |
| React Dashboard | not built — consume the `/incidents` API |

## Run (local, no external deps)

```
pip install -r requirements.txt
python smoke_test.py            # end-to-end against SQLite + mock LLM
uvicorn app.main:app --reload   # serve the API on :8000
```

On Windows / PowerShell the commands are identical (`python`, `uvicorn ...`).

## Endpoints

- `POST /ingest/prometheus` — Alertmanager webhook payload
- `POST /ingest/grafana` — Grafana unified-alerting webhook
- `POST /ingest/csv` — multipart CSV upload (cols: source,name,service,severity,status,summary,starts_at + any label cols)
- `GET  /incidents?status=open` — incidents with alerts + RCA
- `GET  /incidents/{id}`
- `POST /incidents/{id}/rca` — re-run the RCA agent

## Correlation rules (`app/correlate.py`)

An incoming alert joins an open incident (within `CORRELATION_WINDOW_SECONDS`) when any
member alert matches by: (1) same `service`, (2) shared value on a configured label key
(`cluster`/`namespace`/`host`/`instance`), or (3) topology adjacency. If it bridges
multiple incidents they are merged via Union-Find.

## Wiring the real LLM

Set in `.env`: `MOCK_LLM=false`, `LLM_BASE_URL` pointed at your WiseGateway/LiteLLM
`/v1` endpoint, `LLM_API_KEY`, `LLM_MODEL`. The agent uses the OpenAI SDK with
`response_format=json_object`.

## Obvious next steps

- Populate `TOPOLOGY` in `correlate.py` from a CMDB/service-map source.
- Move RCA generation to a background task / queue so ingestion stays fast under burst.
- Switch to Postgres and add Alembic migrations (currently `create_all`).
- Add incident resolution + auto-resolve on `status=resolved` alerts.
- Build the React dashboard against `/incidents`.
