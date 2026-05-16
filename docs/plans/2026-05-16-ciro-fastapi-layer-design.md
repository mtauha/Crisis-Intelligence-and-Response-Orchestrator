# CIRO — FastAPI Layer Design
**Date:** 2026-05-16
**Status:** Validated
**Relates to:** 2026-05-16-ciro-architecture-design.md

---

## Overview

FastAPI is a thin, read-heavy API gateway. It owns three responsibilities:
1. **Serve** — expose DB data to Flutter via REST endpoints
2. **Push** — broadcast real-time events to Flutter via WebSocket (LISTEN/NOTIFY)
3. **Trigger** — invoke agent pipeline and Commander via AgentClient

It contains no business logic. All decisions are made by agents.

**Tech choices (validated):**
- ORM: SQLModel (single model for DB + Pydantic schema)
- Auth: Static API key (state-changing endpoints only)
- WebSocket: PostgreSQL LISTEN/NOTIFY via asyncpg
- Agent trigger: Hybrid — in-process local, Agent Engine in production
- Commander approval trigger: FastAPI BackgroundTasks → AgentClient

---

## 1. Project Structure

```
api/
├── main.py                  # FastAPI app init, lifespan, router registration
├── dependencies.py          # Shared: DB session, API key auth, AgentClient
├── config.py                # Settings (env vars via pydantic-settings)
├── connection_manager.py    # ConnectionManager singleton — shared by websocket.py
│                            #   and agent_client.py (avoids circular import)
├── routers/
│   ├── cities.py            # GET /cities, GET /cities/{city}/state
│   ├── incidents.py         # GET /incidents, GET /incidents/{id},
│   │                        #   POST /incidents/{id}/approve
│   ├── map.py               # GET /map/pins, GET /map/routes/{city}
│   ├── signals.py           # GET /signals
│   └── demo.py              # POST /demo/trigger, POST /demo/reset
├── websocket.py             # WS /ws/feed + PostgreSQL LISTEN/NOTIFY listener
└── agent_client.py          # Agent Engine + local runner + pipeline status events
```

---

## 2. App Setup

**`config.py`:**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str           # postgresql+asyncpg://...
    API_KEY: str                # static key for Flutter + demo control
    ENV: str = "local"          # "local" | "production"
    GEMINI_ENABLED: bool = True
    GCP_PROJECT: str = ""
    GCP_REGION: str = "us-central1"
    AGENT_ENGINE_PIPELINE_ID: str = ""
    AGENT_ENGINE_COMMANDER_ID: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
```

**`main.py`:**
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from api.websocket import start_db_listener, stop_db_listener

@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_db_listener()   # starts PostgreSQL LISTEN on startup
    yield
    await stop_db_listener()    # cancels task + closes connection on shutdown

app = FastAPI(title="CIRO API", version="1.0.0", lifespan=lifespan)

app.include_router(cities_router,    prefix="/api/v1")
app.include_router(incidents_router, prefix="/api/v1")
app.include_router(map_router,       prefix="/api/v1")
app.include_router(signals_router,   prefix="/api/v1")
app.include_router(demo_router,      prefix="/api/v1")
app.include_router(ws_router)        # /ws/feed — no prefix
```

**`.env.example`:**
```env
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/ciro
API_KEY=your-static-key-here
ENV=local

GEMINI_ENABLED=true

# Production only
GCP_PROJECT=your-project-id
GCP_REGION=us-central1
AGENT_ENGINE_PIPELINE_ID=projects/.../reasoningEngines/...
AGENT_ENGINE_COMMANDER_ID=projects/.../reasoningEngines/...
```

---

## 3. SQLModel Database Models

**`db/models.py`:**
```python
from sqlmodel import SQLModel, Field
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ARRAY, JSONB
from typing import Optional
from datetime import datetime
import uuid


class Signal(SQLModel, table=True):
    __tablename__ = "signals"
    id:                    uuid.UUID       = Field(default_factory=uuid.uuid4, primary_key=True)
    city:                  str
    source:                str             # 'weather' | 'social'
    signal_type:           str             # 'rainfall_mm' | 'social_post' | ...
    crisis_type:           str             # 'urban_flooding' | 'heatwave' | 'road_blockage'
    value:                 dict            = Field(sa_column=Column(JSONB))
    location:              dict            = Field(sa_column=Column(JSONB))
    confidence_hint:       float
    verification_tag:      str             # 'VERIFIED'|'UNVERIFIED'|'LOW_CORROBORATION'|'SOCIAL_CONSENSUS'
    cross_referenced_with: list[uuid.UUID] = Field(
        default=[],
        sa_column=Column(ARRAY(PG_UUID(as_uuid=True)))  # matches Signal.id type
    )
    raw_text:              Optional[str]   = None
    collected_at:          datetime        = Field(default_factory=datetime.utcnow)
    processed:             bool            = Field(default=False)


class Incident(SQLModel, table=True):
    __tablename__ = "incidents"
    id:               uuid.UUID       = Field(default_factory=uuid.uuid4, primary_key=True)
    city:             str
    crisis_type:      str
    severity:         str             # 'low' | 'medium' | 'critical'
    status:           str             # see status lifecycle below
    confidence:       float
    reasoning:        str
    evidence_summary: dict            = Field(sa_column=Column(JSONB))
    affected_zones:   list[str]       = Field(default=[], sa_column=Column(ARRAY(TEXT)))
    signal_ids:       list[uuid.UUID] = Field(
        default=[],
        sa_column=Column(ARRAY(PG_UUID(as_uuid=True)))  # matches Signal.id type
    )
    state_snapshot:   Optional[dict]  = Field(
        default=None,
        sa_column=Column(JSONB)
        # Commander writes: {"before": {"status": "normal", ...},
        #                    "after":  {"status": "critical", ...}}
        # Null until Commander acts. Per-incident — never shared across incidents.
    )
    created_at:       datetime        = Field(default_factory=datetime.utcnow)
    approved_at:      Optional[datetime] = None
    approved_by:      Optional[str]   = None   # 'controller' for MVP


class CityState(SQLModel, table=True):
    __tablename__ = "city_state"
    city:             str             = Field(primary_key=True)
    status:           str             = Field(default="normal")  # 'normal'|'warning'|'critical'
    active_incidents: int             = Field(default=0)
    last_updated:     datetime        = Field(default_factory=datetime.utcnow)
    state_snapshot:   Optional[dict]  = Field(default=None, sa_column=Column(JSONB))
    # city_state.state_snapshot = current live city state (feeds Home screen)
    # incident.state_snapshot   = per-incident before/after diff (feeds Incident Detail)


class Action(SQLModel, table=True):
    __tablename__ = "actions"
    id:          uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    incident_id: uuid.UUID = Field(foreign_key="incidents.id")
    action_type: str       # 'ticket'|'city_state'|'route'|'cooling_center'|'alert'
    payload:     dict      = Field(sa_column=Column(JSONB))
    executed_at: datetime  = Field(default_factory=datetime.utcnow)


class Ticket(SQLModel, table=True):
    __tablename__ = "tickets"
    id:          uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    incident_id: uuid.UUID = Field(foreign_key="incidents.id")
    title:       str
    status:      str       = Field(default="open")  # 'open' | 'monitoring'
    authority:   str       # 'NDMA' | 'Punjab Health Department' | 'Islamabad Traffic Police'
    created_at:  datetime  = Field(default_factory=datetime.utcnow)


class Route(SQLModel, table=True):
    __tablename__ = "routes"
    id:             uuid.UUID      = Field(default_factory=uuid.uuid4, primary_key=True)
    city:           str
    route_name:     str
    status:         str            = Field(default="open")  # 'open'|'rerouted'|'blocked'
    original_path:  dict           = Field(sa_column=Column(JSONB))
    rerouted_path:  Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    updated_at:     datetime       = Field(default_factory=datetime.utcnow)
```

**Status lifecycle — 6 states:**

| Status | Set by | Meaning |
|---|---|---|
| `pending_commander` | Analyst | Critical — waiting for Commander to act |
| `pending_approval` | Analyst | Medium — waiting for operator tap |
| `approved` | FastAPI `/approve` | Medium — operator approved, Commander not yet run |
| `auto_escalated` | Commander | Critical — Commander acted autonomously |
| `actioned` | Commander | Medium — Commander acted after approval |
| `feed_only` | Analyst | Low — feed only, no further progression |

**Response models (read-only, not table-backed):**
```python
class IncidentDetail(SQLModel):
    """Enriched response for GET /incidents/{id}"""
    id:               uuid.UUID
    city:             str
    crisis_type:      str
    severity:         str
    status:           str
    confidence:       float
    reasoning:        str
    evidence_summary: dict
    affected_zones:   list[str]
    state_snapshot:   Optional[dict]  # per-incident before/after diff
    created_at:       datetime
    approved_at:      Optional[datetime]
    actions_taken:    list[Action]
    ticket:           Optional[Ticket]

class CityCard(SQLModel):
    """Response for GET /cities"""
    city:             str
    status:           str
    active_incidents: int
    last_updated:     datetime

class IncidentPin(SQLModel):
    """Response for GET /map/pins"""
    incident_id:  uuid.UUID
    crisis_type:  str
    severity:     str
    status:       str
    lat:          float
    lng:          float
    zone:         str
```

---

## 4. Auth & Shared Dependencies

**`dependencies.py`:**
```python
from fastapi import Security, HTTPException, Depends
from fastapi.security import APIKeyHeader
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine(settings.DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db():
    async with SessionLocal() as session:
        yield session

api_key_header = APIKeyHeader(name="X-API-Key")

async def require_api_key(key: str = Security(api_key_header)):
    if key != settings.API_KEY:
        raise HTTPException(403, "Invalid API key")
```

**Auth scope:**
- `GET` endpoints — no auth (Flutter reads freely)
- `POST /incidents/{id}/approve` — requires `X-API-Key`
- `POST /demo/trigger` — requires `X-API-Key`
- `POST /demo/reset` — requires `X-API-Key`

---

## 5. Key Router Implementations

**`routers/cities.py`:**
```python
@router.get("/cities", response_model=list[CityCard])
async def get_cities(db: AsyncSession = Depends(get_db)):
    result = await db.exec(select(CityState))
    return result.all()

@router.get("/cities/{city}/state")
async def get_city_state(city: str, db: AsyncSession = Depends(get_db)):
    state = await db.get(CityState, city)
    if not state:
        raise HTTPException(404, f"City '{city}' not found")
    return state
```

**`routers/incidents.py`:**
```python
@router.get("/incidents", response_model=list[Incident])
async def list_incidents(
    city: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(Incident).order_by(Incident.created_at.desc())
    if city:     query = query.where(Incident.city == city)
    if severity: query = query.where(Incident.severity == severity)
    if status:   query = query.where(Incident.status == status)
    return (await db.exec(query)).all()


@router.get("/incidents/{id}", response_model=IncidentDetail)
async def get_incident(id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    incident = await db.get(Incident, id)
    if not incident:
        raise HTTPException(404, "Incident not found")

    actions = (await db.exec(
        select(Action).where(Action.incident_id == id).order_by(Action.executed_at)
    )).all()
    ticket = (await db.exec(
        select(Ticket).where(Ticket.incident_id == id)
    )).first()

    return IncidentDetail(**incident.model_dump(), actions_taken=actions, ticket=ticket)


@router.post("/incidents/{id}/approve", dependencies=[Depends(require_api_key)])
async def approve_incident(
    id: uuid.UUID,
    body: ApproveRequest,                   # { "approved_by": "controller" }
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    agent: AgentClient = Depends(get_agent_client)
):
    # Atomic conditional update — only succeeds if status=pending_approval
    result = await db.exec(
        update(Incident)
        .where(Incident.id == id, Incident.status == "pending_approval")
        .values(status="approved", approved_at=datetime.utcnow(), approved_by=body.approved_by)
        .returning(Incident)
    )
    if not result.first():
        raise HTTPException(409, "Incident is not in pending_approval state")
    await db.commit()

    # Trigger Commander — non-blocking, tied to request lifecycle
    background_tasks.add_task(agent.trigger_commander, incident_id=str(id))
    return {"status": "approved", "incident_id": str(id)}
```

**`routers/demo.py`:**
```python
router = APIRouter(tags=["demo"], dependencies=[Depends(require_api_key)])

@router.post("/demo/trigger")
async def trigger_demo(
    body: DemoTriggerRequest,               # { "scenario": "karachi" }
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    agent: AgentClient = Depends(get_agent_client)
):
    active = await db.exec(select(func.count(Incident.id)))
    if active.first() > 0:
        raise HTTPException(400, "Reset demo before triggering again")

    background_tasks.add_task(agent.trigger_pipeline, scenario=body.scenario)
    return {"status": "pipeline_started", "scenario": body.scenario}


@router.post("/demo/reset")
async def reset_demo(db: AsyncSession = Depends(get_db)):
    # FK-safe deletion order
    await db.exec(delete(Route))      # no FK — clears stale reroutes
    await db.exec(delete(Action))     # FK → incidents
    await db.exec(delete(Ticket))     # FK → incidents
    await db.exec(delete(Incident))
    await db.exec(delete(Signal))
    await db.exec(
        update(CityState).values(status="normal", active_incidents=0, state_snapshot=None)
    )
    await db.commit()
    return {"status": "reset_complete"}
```

---

## 6. WebSocket + PostgreSQL LISTEN/NOTIFY

**DB trigger (migration file):**
```sql
CREATE OR REPLACE FUNCTION notify_incident_change()
RETURNS TRIGGER AS $$
BEGIN
  PERFORM pg_notify(
    'incidents_channel',
    json_build_object(
      'event',       TG_OP,
      'incident_id', NEW.id::text,
      'city',        NEW.city,
      'severity',    NEW.severity,
      'status',      NEW.status
    )::text
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER incidents_notify_trigger
  AFTER INSERT OR UPDATE ON incidents
  FOR EACH ROW EXECUTE FUNCTION notify_incident_change();
```

**`connection_manager.py` — shared singleton (avoids circular import):**
```python
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)

    async def broadcast(self, message: dict):
        dead = set()
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        self.active -= dead

# Singleton — imported by both websocket.py and agent_client.py
manager = ConnectionManager()
```

**`websocket.py`:**
```python
import asyncio, asyncpg, json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from api.connection_manager import manager

router = APIRouter()

@router.websocket("/ws/feed")
async def websocket_feed(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()     # Flutter sends pings to keep alive
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ── Listener lifecycle ────────────────────────────────────────

_listener_conn: asyncpg.Connection | None = None
_keep_alive_task: asyncio.Task | None = None

async def start_db_listener():
    global _listener_conn, _keep_alive_task
    _listener_conn = await asyncpg.connect(
        settings.DATABASE_URL.replace("+asyncpg", "")
    )
    await _listener_conn.add_listener("incidents_channel", handle_notify)
    _keep_alive_task = asyncio.create_task(_keep_alive(_listener_conn))

async def stop_db_listener():
    if _keep_alive_task:
        _keep_alive_task.cancel()
    if _listener_conn and not _listener_conn.is_closed():
        await _listener_conn.close()

async def _keep_alive(conn: asyncpg.Connection):
    while True:
        await asyncio.sleep(30)
        if conn.is_closed():
            break

async def handle_notify(connection, pid, channel, payload):
    data = json.loads(payload)
    event_map = {
        ("INSERT", None):             "incident_created",
        ("UPDATE", "actioned"):       "incident_actioned",
        ("UPDATE", "auto_escalated"): "incident_actioned",
        ("UPDATE", "approved"):       "incident_approved",
    }
    key = (data["event"], data["status"] if data["event"] == "UPDATE" else None)
    event_type = event_map.get(key, "incident_updated")

    await manager.broadcast({
        "event":       event_type,
        "incident_id": data["incident_id"],
        "city":        data["city"],
        "severity":    data["severity"],
        "status":      data["status"],
    })
```

**Flutter event handling:**

| Event | Source | Flutter action |
|---|---|---|
| `pipeline_started` | AgentClient | Home: Trigger button → loading, show stage banner |
| `pipeline_error` | AgentClient | Home: Show error banner with stage + message |
| `pipeline_complete` | AgentClient | Home: Trigger button → ready again |
| `incident_created` | DB trigger | Feed: Animate new card in, update Home badge |
| `incident_approved` | DB trigger | Detail: Update badge → "Actioning..." |
| `incident_actioned` | DB trigger | Detail: Populate Actions Taken + BeforeAfter |
| `incident_updated` | DB trigger | Detail: Re-fetch if currently viewing |

---

## 7. AgentClient

**`agent_client.py`:**
```python
import asyncio, logging
import vertexai
from vertexai.preview import reasoning_engines
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from api.connection_manager import manager   # shared singleton — no circular import

logger = logging.getLogger(__name__)


class AgentClient:

    def _get_local_pipeline(self):
        from agents.pipeline import pipeline
        return pipeline

    def _get_local_commander(self):
        from agents.commander.commander_agent import commander_agent
        return commander_agent

    def _get_pipeline_engine(self):
        vertexai.init(project=settings.GCP_PROJECT, location=settings.GCP_REGION)
        return reasoning_engines.ReasoningEngine(settings.AGENT_ENGINE_PIPELINE_ID)

    def _get_commander_engine(self):
        vertexai.init(project=settings.GCP_PROJECT, location=settings.GCP_REGION)
        return reasoning_engines.ReasoningEngine(settings.AGENT_ENGINE_COMMANDER_ID)

    async def trigger_pipeline(self, scenario: str) -> None:
        logger.info(f"[AgentClient] Triggering pipeline — scenario: {scenario}")
        await manager.broadcast({"event": "pipeline_started", "stage": "sentinel"})
        try:
            if settings.ENV == "local":
                await self._run_local(self._get_local_pipeline(), {"scenario": scenario})
            else:
                await self._run_engine(self._get_pipeline_engine(), {"scenario": scenario})
            await manager.broadcast({"event": "pipeline_complete", "stage": "commander"})
        except Exception as e:
            await manager.broadcast({
                "event":   "pipeline_error",
                "stage":   "pipeline",
                "message": str(e),
            })
            raise

    async def trigger_commander(self, incident_id: str) -> None:
        logger.info(f"[AgentClient] Triggering Commander — incident: {incident_id}")
        # Commander approval doesn't emit pipeline_* events — feedback comes via
        # DB trigger → incident_actioned WS event when Commander writes to DB
        try:
            if settings.ENV == "local":
                await self._run_local(self._get_local_commander(), {"incident_id": incident_id})
            else:
                await self._run_engine(self._get_commander_engine(), {"incident_id": incident_id})
        except Exception as e:
            logger.error(f"[AgentClient] Commander failed: {e}", exc_info=True)
            raise

    async def _run_local(self, agent, message: dict) -> None:
        try:
            session_service = InMemorySessionService()
            runner = Runner(agent=agent, app_name="ciro", session_service=session_service)
            session = await session_service.create_session(app_name="ciro", user_id="system")
            async for event in runner.run_async(
                user_id="system", session_id=session.id, new_message=message
            ):
                logger.debug(f"[Agent] {event}")
        except Exception as e:
            logger.error(f"[AgentClient] Local run failed: {e}", exc_info=True)
            raise

    async def _run_engine(self, engine, input_data: dict) -> None:
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: engine.query(input=input_data)
                # run_in_executor offloads blocking SDK call to thread pool
                # keeps event loop free — WebSocket broadcast continues uninterrupted
            )
        except Exception as e:
            logger.error(f"[AgentClient] Engine run failed: {e}", exc_info=True)
            raise


_agent_client = AgentClient()

def get_agent_client() -> AgentClient:
    return _agent_client
```

**Pipeline status event payloads:**
```json
// Emitted by AgentClient before pipeline runs
{ "event": "pipeline_started", "stage": "sentinel" }

// Emitted by AgentClient after all agents complete
{ "event": "pipeline_complete", "stage": "commander" }

// Emitted by AgentClient on any exception
{ "event": "pipeline_error", "stage": "pipeline", "message": "..." }
```

---

## 8. Endpoint Summary

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/cities` | None | Karachi city card |
| GET | `/api/v1/cities/{city}/state` | None | Full city state |
| GET | `/api/v1/incidents` | None | Incident feed (filterable) |
| GET | `/api/v1/incidents/{id}` | None | Full incident detail |
| POST | `/api/v1/incidents/{id}/approve` | API Key | Approve medium incident |
| GET | `/api/v1/map/pins` | None | Incident map pins |
| GET | `/api/v1/map/routes/{city}` | None | Route statuses + GeoJSON |
| GET | `/api/v1/signals` | None | Raw signals (debug) |
| POST | `/api/v1/demo/trigger` | API Key | Fire pipeline |
| POST | `/api/v1/demo/reset` | API Key | Reset all state |
| WS | `/ws/feed` | None | Real-time incident + pipeline events |

## 9. WS Event Reference

| Event | Source | Payload fields |
|---|---|---|
| `pipeline_started` | AgentClient | `stage` |
| `pipeline_complete` | AgentClient | `stage` |
| `pipeline_error` | AgentClient | `stage`, `message` |
| `incident_created` | DB trigger | `incident_id`, `city`, `severity`, `status` |
| `incident_approved` | DB trigger | `incident_id`, `city`, `severity`, `status` |
| `incident_actioned` | DB trigger | `incident_id`, `city`, `severity`, `status` |
| `incident_updated` | DB trigger | `incident_id`, `city`, `severity`, `status` |
