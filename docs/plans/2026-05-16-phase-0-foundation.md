# Phase 0 Foundation Implementation Plan

**For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish the fundamental backend and database structure for the CIRO multi-agent pipeline, enabling real-time crisis processing and mobile consumption.

**Architecture:** A monolithic-style FastAPI backend with a PostgreSQL Blackboard. Agents and endpoints share the database state. Alembic migrations handle schema and PostgreSQL LISTEN/NOTIFY trigger injection. Mock data is stored as local JSONs to bypass live APIs for the demo.

**Tech Stack:** FastAPI, SQLModel, PostgreSQL (asyncpg), Alembic, Pytest

---

### Task 1: Monorepo Directory Structure, Config & Dependencies

**Files:**
- Create: `pytest.ini`
- Create: `requirements.txt`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create directories and `__init__.py` files

**Step 1: Write directory structure and config files**

```bash
mkdir -p ciro/api/routers ciro/agents/sentinel/tools ciro/agents/analyst/tools ciro/agents/commander/actions ciro/db ciro/mock_data ciro/stubs tests
touch ciro/__init__.py ciro/api/__init__.py ciro/api/routers/__init__.py ciro/agents/__init__.py ciro/agents/sentinel/__init__.py ciro/agents/sentinel/tools/__init__.py ciro/agents/analyst/__init__.py ciro/agents/analyst/tools/__init__.py ciro/agents/commander/__init__.py ciro/agents/commander/actions/__init__.py ciro/db/__init__.py ciro/mock_data/__init__.py ciro/stubs/__init__.py
```

Create `.env.example` at the project root:
```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ciro
API_KEY=local-dev-key
ENV=local
GEMINI_ENABLED=true
GCP_PROJECT=your-project-id
GCP_REGION=us-central1
AGENT_ENGINE_PIPELINE_ID=
AGENT_ENGINE_COMMANDER_ID=
COLLECTOR_MODE=mock
```

Create `pytest.ini`:
```ini
[pytest]
pythonpath = .
asyncio_mode = auto
```

Create `requirements.txt`:
```text
fastapi
uvicorn
sqlmodel
sqlalchemy
asyncpg
psycopg2-binary
alembic
pydantic-settings
pytest
pytest-asyncio
```

Create `docker-compose.yml`:
```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: ciro
    ports:
      - "5432:5432"
```

**Step 2: Run dependencies and database**

Run: `docker-compose up -d`
Run: `uv venv`
Run: `uv pip install -r requirements.txt`

**Step 3: Commit**

```bash
git add .env.example pytest.ini requirements.txt docker-compose.yml ciro/ tests/
git commit -m "chore: initialize monorepo structure, dependencies, and docker config"
```

---

### Task 2: Database Schema Models

**Files:**
- Create: `tests/test_models.py`
- Create: `ciro/db/models.py`

**Step 1: Write the failing test**

```python
# tests/test_models.py
from ciro.db.models import Signal, Incident, CityState, Action, Ticket, Route
import uuid

def test_models_instantiation():
    cs = CityState(city="karachi", status="normal", active_incidents=0)
    assert cs.city == "karachi"
    
    sig = Signal(city="karachi", source="weather", signal_type="rain", crisis_type="urban_flooding", value={"rain": 10}, location={"lat": 0, "lng": 0}, confidence_hint=0.9, verification_tag="VERIFIED")
    assert sig.value["rain"] == 10
    
    inc = Incident(id=uuid.uuid4(), city="karachi", crisis_type="flood", severity="low", status="feed_only", confidence=0.5, reasoning="test", evidence_summary={"a": "b"})
    assert inc.severity == "low"
    
    act = Action(incident_id=inc.id, action_type="ticket", payload={"foo": "bar"})
    assert act.payload["foo"] == "bar"
    
    tkt = Ticket(incident_id=inc.id, title="Test", authority="NDMA")
    assert tkt.status == "open"
    
    rt = Route(city="karachi", route_name="Route A", original_path={"type": "LineString"})
    assert rt.status == "open"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL with "ImportError: cannot import name 'Signal'"

**Step 3: Write minimal implementation**

```python
# ciro/db/models.py
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, TEXT
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ARRAY, JSONB
from typing import Optional, List
from datetime import datetime
import uuid

class Signal(SQLModel, table=True):
    __tablename__ = "signals"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    city: str
    source: str
    signal_type: str
    crisis_type: str
    value: dict = Field(sa_column=Column(JSONB))
    location: dict = Field(sa_column=Column(JSONB))
    confidence_hint: float
    verification_tag: str
    cross_referenced_with: List[uuid.UUID] = Field(default=[], sa_column=Column(ARRAY(PG_UUID(as_uuid=True))))
    raw_text: Optional[str] = None
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    processed: bool = Field(default=False)

class Incident(SQLModel, table=True):
    __tablename__ = "incidents"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    city: str
    crisis_type: str
    severity: str
    status: str
    confidence: float
    reasoning: str
    evidence_summary: dict = Field(sa_column=Column(JSONB))
    affected_zones: List[str] = Field(default=[], sa_column=Column(ARRAY(TEXT)))
    signal_ids: List[uuid.UUID] = Field(default=[], sa_column=Column(ARRAY(PG_UUID(as_uuid=True))))
    # Per-incident before/after diff. Feeds the Incident Detail screen.
    state_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None

class CityState(SQLModel, table=True):
    __tablename__ = "city_state"
    city: str = Field(primary_key=True)
    status: str = Field(default="normal")
    active_incidents: int = Field(default=0)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    # Current live city state snapshot. Feeds the Home screen.
    state_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSONB))

class Action(SQLModel, table=True):
    __tablename__ = "actions"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    incident_id: uuid.UUID = Field(foreign_key="incidents.id")
    action_type: str
    payload: dict = Field(sa_column=Column(JSONB))
    executed_at: datetime = Field(default_factory=datetime.utcnow)

class Ticket(SQLModel, table=True):
    __tablename__ = "tickets"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    incident_id: uuid.UUID = Field(foreign_key="incidents.id")
    title: str
    status: str = Field(default="open")
    authority: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Route(SQLModel, table=True):
    __tablename__ = "routes"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    city: str
    route_name: str
    status: str = Field(default="open")
    original_path: dict = Field(sa_column=Column(JSONB))
    rerouted_path: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_models.py ciro/db/models.py
git commit -m "feat: implement SQLModel definitions for 6 core tables"
```

---

### Task 3: Database Migrations & Triggers

**Files:**
- Create: `alembic.ini`
- Create: `ciro/db/migrations/env.py`
- Modify: `ciro/db/migrations/versions/<revision>_init.py`

**Step 1: Initialize alembic**

Run: `alembic init ciro/db/migrations`

**Step 2: Configure alembic.ini and env.py**

Modify `alembic.ini` to explicitly set the synchronous driver:
```ini
sqlalchemy.url = postgresql://postgres:postgres@localhost:5432/ciro
```

Modify `ciro/db/migrations/env.py` to import models:
```python
import sys
from os.path import dirname, abspath
sys.path.insert(0, dirname(dirname(dirname(abspath(__file__)))))

from sqlmodel import SQLModel
import ciro.db.models
target_metadata = SQLModel.metadata
```

**Step 3: Generate and Modify Initial Migration**

Run: `alembic revision --autogenerate -m "init"`

Then open the generated migration file and add the LISTEN/NOTIFY and active incidents triggers to `upgrade()`:
```python
def upgrade():
    # ... (auto-generated table creations) ...
    
    op.execute("""
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
    """)
    op.execute("""
    CREATE TRIGGER incidents_notify_trigger
      AFTER INSERT OR UPDATE ON incidents
      FOR EACH ROW EXECUTE FUNCTION notify_incident_change();
    """)
    
    op.execute("""
    CREATE OR REPLACE FUNCTION update_active_incidents()
    RETURNS TRIGGER AS $$
    BEGIN
      UPDATE city_state 
      SET active_incidents = (
        SELECT count(*) FROM incidents 
        WHERE city = COALESCE(NEW.city, OLD.city) 
        AND status NOT IN ('resolved', 'feed_only')
      )
      WHERE city = COALESCE(NEW.city, OLD.city);
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("""
    CREATE TRIGGER incidents_active_count_trigger
      AFTER INSERT OR UPDATE OR DELETE ON incidents
      FOR EACH ROW EXECUTE FUNCTION update_active_incidents();
    """)

def downgrade():
    op.execute("DROP TRIGGER IF EXISTS incidents_active_count_trigger ON incidents;")
    op.execute("DROP FUNCTION IF EXISTS update_active_incidents();")
    op.execute("DROP TRIGGER IF EXISTS incidents_notify_trigger ON incidents;")
    op.execute("DROP FUNCTION IF EXISTS notify_incident_change();")
    # ... (auto-generated table drops) ...
```

**Step 4: Apply Migration**

Run: `alembic upgrade head`
Expected: Tables and triggers are successfully created in PostgreSQL.

**Step 5: Commit**

```bash
git add alembic.ini ciro/db/migrations/
git commit -m "feat: setup Alembic and apply init migration with triggers"
```

---

### Task 4: Database Seed Script

*Note: The `signals` table is intentionally left empty. Sentinel populates signals at runtime, so we do not seed them here.*

**Files:**
- Create: `ciro/db/seed.py`

**Step 1: Write seed script implementation**

```python
# ciro/db/seed.py
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import select
from ciro.db.models import CityState, Route
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/ciro")
engine = create_async_engine(DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def seed():
    async with SessionLocal() as session:
        # Check idempotency for Karachi
        result = await session.exec(select(CityState).where(CityState.city == "karachi"))
        if not result.first():
            # Seed Karachi City State
            karachi_state = CityState(city="karachi", status="normal", active_incidents=0)
            session.add(karachi_state)
            
            # Seed Routes
            route1 = Route(
                city="karachi", route_name="Gulshan Underpass", status="open",
                original_path={"type": "LineString", "coordinates": [[67.0946, 24.9215], [67.0950, 24.9220]]}
            )
            route2 = Route(
                city="karachi", route_name="Nazimabad Route", status="open",
                original_path={"type": "LineString", "coordinates": [[67.0439, 24.9056], [67.0450, 24.9060]]}
            )
            session.add(route1)
            session.add(route2)
            
            await session.commit()
            print("Seed data inserted successfully.")
        else:
            print("Seed data already exists.")

if __name__ == "__main__":
    asyncio.run(seed())
```

**Step 2: Run seed script to verify**

Run: `uv run python -m ciro.db.seed`
Expected: Output `Seed data inserted successfully.`
Run again: `uv run python -m ciro.db.seed`
Expected: Output `Seed data already exists.`

**Step 3: Commit**

```bash
git add ciro/db/seed.py
git commit -m "feat: add db seed script with idempotency guard"
```

---

### Task 5: Mock Data Files

*Note: `traffic_signals.json` is explicitly deferred to post-MVP (Road Blockage scenario) as per architecture design.*

**Files:**
- Create: `tests/test_mock_data.py`
- Create: `ciro/mock_data/weather_signals.json`
- Create: `ciro/mock_data/social_signals.json`

**Step 1: Write the failing test**

```python
# tests/test_mock_data.py
import json
import os

def test_weather_signals():
    path = os.path.join("ciro", "mock_data", "weather_signals.json")
    with open(path) as f:
        data = json.load(f)
    assert "signals" in data
    assert data["signals"][0]["value"] == 87.4

def test_social_signals():
    path = os.path.join("ciro", "mock_data", "social_signals.json")
    with open(path) as f:
        data = json.load(f)
    assert len(data["signals"]) == 2
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mock_data.py -v`
Expected: FAIL with "FileNotFoundError"

**Step 3: Write minimal implementation**

Create `ciro/mock_data/weather_signals.json`:
```json
{
  "signals": [
    {
      "city": "karachi",
      "signal_type": "rainfall_mm",
      "value": 87.4,
      "timestamp": "2025-07-15T14:30:00Z",
      "location": { "lat": 24.8607, "lng": 67.0011, "zone": "Gulshan-e-Iqbal" }
    }
  ]
}
```

Create `ciro/mock_data/social_signals.json`:
```json
{
  "signals": [
    {
      "city": "karachi",
      "signal_type": "social_post",
      "value": {
        "text": "Road completely submerged near Gulshan underpass, cars stranded #KarachiFloods",
        "source": "twitter_mock",
        "engagement": 847
      },
      "timestamp": "2025-07-15T14:22:00Z",
      "location": { "lat": 24.9215, "lng": 67.0946, "zone": "Gulshan Underpass" }
    },
    {
      "city": "karachi",
      "signal_type": "social_post",
      "value": {
        "text": "Nazimabad underpass completely flooded. Water level rising fast. Avoid the area! #Karachi",
        "source": "twitter_mock",
        "engagement": 1540
      },
      "timestamp": "2025-07-15T14:26:00Z",
      "location": { "lat": 24.9056, "lng": 67.0439, "zone": "Nazimabad" }
    }
  ]
}
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_mock_data.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add ciro/mock_data/ tests/test_mock_data.py
git commit -m "feat: add mock JSON files for weather and social signals"
```
