# CIRO — Crisis Intelligence & Response Orchestrator
## Architecture Design
**Date:** 2026-05-16
**Status:** Validated

---

## Overview

CIRO is an autonomous multi-agent crisis response system. The MVP focuses on **Karachi** only. The system continuously monitors signals, detects crises, and executes response actions without waiting for user input. The mobile app is a window into an already-acting system.

> **MVP Scope:** Karachi only. Lahore and Islamabad are deferred to a post-MVP phase.

**Tech Stack:**
- **Orchestration:** Vertex AI Agent Development Kit (ADK) + Agent Engine
- **Backend:** FastAPI (thin API gateway on Cloud Run)
- **Database:** PostgreSQL on Cloud SQL
- **Mobile:** Flutter
- **LLM:** Gemini API via ADK (toggleable via `GEMINI_ENABLED` env var)

**Demo Scenario:** Single city, single crisis:
- Karachi → Urban Flooding

---

## 1. Agent Orchestration Flow

```
Mock JSON Files  (or Live APIs in production)
      │
      ▼
┌─────────────────────────────────────────────┐
│           Vertex AI Agent Engine            │
│                                             │
│  ┌─────────────┐                            │
│  │  Sentinel   │  Runs on schedule (cron)   │
│  │   Agent     │  Reads signal collectors   │
│  │             │  Writes raw signals to DB  │
│  └──────┬──────┘                            │
│         │ triggers                          │
│  ┌──────▼──────┐                            │
│  │  Analyst    │  Reads signals from DB     │
│  │   Agent     │  Calls Gemini (or stub)    │
│  │             │  Writes incidents to DB    │
│  └──────┬──────┘  Only escalates if critical│
│         │ triggers                          │
│  ┌──────▼──────┐                            │
│  │  Commander  │  Updates city state        │
│  │   Agent     │  Creates emergency ticket  │
│  │             │  Stores authority alert    │
│  └─────────────┘  Pushes to mobile feed     │
└─────────────────────────────────────────────┘
      │
      ▼
PostgreSQL (Cloud SQL) ──► FastAPI Gateway ──► Flutter App
```

**Key decisions:**
- ADK's `SequentialAgent` chains Sentinel → Analyst → Commander
- Gemini toggle: `GEMINI_ENABLED=true/false`. When `false`, Analyst uses a deterministic rule-based stub with identical output schema
- Agent Engine handles scheduling (Sentinel every 5 min in prod, manual trigger for demo)
- All inter-agent communication goes through the DB — no direct agent-to-agent calls

---

## 2. Sentinel's Signal Collector Layer

Sentinel uses a pluggable collector architecture. Each data source is a separate module with a common interface. Swapping mock ↔ live is a one-line config change.

```
Sentinel Agent
│
├── collectors/
│   ├── base.py              → Abstract BaseCollector
│   ├── weather_collector.py → MODE=mock: reads JSON | MODE=live: OpenWeatherMap / PMD
│   ├── traffic_collector.py → MODE=mock: reads JSON | MODE=live: Google Maps / TomTom
│   └── social_collector.py  → MODE=mock: reads JSON | MODE=live: X API v2
│
└── sentinel_agent.py        → runs all collectors → normalizes → writes to signals table
```

**BaseCollector interface:**
```python
class BaseCollector:
    def collect(self, city: str) -> list[Signal]:
        """Returns normalized Signal objects regardless of source"""
        raise NotImplementedError
```

**Config:**
```env
COLLECTOR_MODE=mock          # demo
COLLECTOR_MODE=live          # production

OPENWEATHER_API_KEY=...
GOOGLE_MAPS_API_KEY=...
TWITTER_BEARER_TOKEN=...
```

**Live API targets for production:**
| Signal Type | Live API |
|---|---|
| Weather / Rainfall | OpenWeatherMap or Pakistan Meteorological Dept (PMD) |
| Temperature / Humidity | OpenWeatherMap |
| Traffic speed | Google Maps Traffic API / TomTom |
| Social posts | X (Twitter) API v2 keyword search |

> Sentinel is the **only** agent that ever touches external APIs. Analyst and Commander only read from the `signals` table.

---

## 3. Database Schema

```sql
-- Raw signals collected by Sentinel
CREATE TABLE signals (
    id           UUID PRIMARY KEY,
    city         TEXT,
    source       TEXT,              -- 'weather' | 'traffic' | 'social'
    signal_type  TEXT,              -- 'rainfall_mm' | 'temp_celsius' | 'speed_kmh' | 'social_post'
    value        JSONB,
    collected_at TIMESTAMPTZ,
    processed    BOOLEAN DEFAULT FALSE
);

-- Incidents detected and reasoned by Analyst
CREATE TABLE incidents (
    id              UUID PRIMARY KEY,
    city            TEXT,
    crisis_type     TEXT,           -- 'urban_flooding' (MVP) | 'heatwave' | 'road_blockage' (post-MVP)
    severity        TEXT,           -- 'low' | 'medium' | 'critical'
    status          TEXT,           -- 'feed_only'         (low: no Commander)
                                    -- 'pending_approval'  (medium: awaiting operator tap)
                                    -- 'approved'          (medium: operator approved, Commander acted)
                                    -- 'auto_escalated'    (critical: Commander acted autonomously)
                                    -- 'resolved'
    confidence      FLOAT,          -- 0.0 – 1.0
    reasoning       TEXT,           -- Gemini explanation or stub text
    evidence_summary JSONB,         -- sensor readings + social signal summary
    affected_zones  TEXT[],         -- zone names covered by this incident
    signal_ids      UUID[],         -- signals that triggered this
    created_at      TIMESTAMPTZ,
    approved_at     TIMESTAMPTZ,    -- set when operator approves medium incident
    approved_by     TEXT            -- operator identifier (MVP: 'controller')
);

-- City state — before/after is the core demo story
CREATE TABLE city_state (
    city             TEXT PRIMARY KEY,
    status           TEXT,          -- 'normal' | 'warning' | 'critical'
    active_incidents INT DEFAULT 0,
    last_updated     TIMESTAMPTZ,
    state_snapshot   JSONB          -- full before/after diff stored here
);

-- Actions taken by Commander
CREATE TABLE actions (
    id           UUID PRIMARY KEY,
    incident_id  UUID REFERENCES incidents(id),
    action_type  TEXT,              -- 'ticket' | 'reroute' | 'alert' | 'feed_push'
    payload      JSONB,
    executed_at  TIMESTAMPTZ
);

-- Emergency tickets
CREATE TABLE tickets (
    id           UUID PRIMARY KEY,
    incident_id  UUID REFERENCES incidents(id),
    title        TEXT,
    status       TEXT DEFAULT 'open',
    authority    TEXT,              -- 'NDMA' (MVP) | 'Punjab Health' | 'Islamabad Traffic Police' (post-MVP)
    created_at   TIMESTAMPTZ
);

-- Mock route data (updated by Commander on road blockage)
CREATE TABLE routes (
    id             UUID PRIMARY KEY,
    city           TEXT,
    route_name     TEXT,
    status         TEXT,            -- 'open' | 'rerouted' | 'blocked'
    original_path  JSONB,
    rerouted_path  JSONB,
    updated_at     TIMESTAMPTZ
);
```

> The before/after story lives in `city_state.state_snapshot` — Commander writes a JSON diff of what changed. The mobile Incident Detail screen reads this directly.

---

## 4. FastAPI Gateway Endpoints

FastAPI reads from the DB and exposes clean endpoints to Flutter. No business logic here.

**Base URL:** `/api/v1`

### City & Dashboard
```
GET  /cities                  → Karachi city status + active incident count (MVP: single city)
GET  /cities/{city}/state     → Full city state object (current snapshot)
```

### Incidents
```
GET  /incidents               → All incidents, sorted by created_at desc
                                Query params: ?city=karachi&severity=critical
                                              &status=pending_approval
GET  /incidents/{id}          → Full incident detail:
                                  - reasoning trace + evidence_summary
                                  - before/after state diff
                                  - list of actions taken
                                  - linked signals
                                  - status (feed_only | pending_approval | approved | auto_escalated)
POST /incidents/{id}/approve  → Operator approves a pending_approval incident
                                Triggers Commander to execute medium action set
                                Body: { "approved_by": "controller" }
```

### Map Data
```
GET  /map/pins                → Active incident locations (lat/lng + crisis type + severity)
GET  /map/routes/{city}       → Route statuses (open/rerouted/blocked) with GeoJSON paths
```

### Demo Control
```
POST /demo/trigger            → Fires full Sentinel→Analyst→Commander pipeline
                                Body: { "scenario": "karachi" }
POST /demo/reset              → Resets all city states to normal, clears incidents
```

### Signals (debug/transparency)
```
GET  /signals                 → Raw signals from Sentinel
                                Query params: ?city=karachi&source=weather
```

### WebSocket (live push)
```
WS   /ws/feed                 → Pushes events to Flutter in real-time:
                                {
                                  "event": "incident_created",
                                  "incident_id": "uuid",
                                  "severity": "critical" | "medium" | "low",
                                  "status": "auto_escalated" | "pending_approval" | "feed_only"
                                }
                                {
                                  "event": "incident_approved",
                                  "incident_id": "uuid"
                                  // Flutter re-fetches incident to show Commander actions
                                }
```

---

## 5. Mock Data Structure

Two JSON files for Karachi, pre-loaded to breach the Urban Flooding threshold.

**`mock_data/weather_signals.json`**
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

**`mock_data/social_signals.json`**
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

> `traffic_signals.json` is not needed for MVP (Urban Flooding crisis). Add for post-MVP Road Blockage scenario.

**Crisis trigger threshold (Analyst rules — MVP):**

| Crisis | City | Trigger Condition |
|---|---|---|
| Urban Flooding | Karachi | `rainfall_mm > 50` AND social post mentions flood |

---

## 6. Flutter App Screens

### Screen → Endpoint Mapping

| Screen | Data Source | Update Method |
|---|---|---|
| Home | `GET /cities` | WebSocket push |
| Incident Feed | `GET /incidents` | WebSocket push |
| Incident Detail | `GET /incidents/{id}` | On-demand fetch |
| Approval Flow | `POST /incidents/{id}/approve` | User action |
| Map Panel | `GET /map/pins` + `GET /map/routes/{city}` | Poll every 30s |

### Three Incident States in the UI

| Incident Status | Feed Badge | Detail Screen Behaviour |
|---|---|---|
| `auto_escalated` (critical) | 🔴 `CRITICAL` — pulsing red | Shows Commander actions already taken. Read-only. |
| `pending_approval` (medium) | 🟡 `AWAITING APPROVAL` — amber | Shows reasoning + evidence. Shows **Approve** button. |
| `feed_only` (low) | ⚪ `MONITORING` — grey | Shows reasoning. No action controls. |

### Screen Descriptions

**Home Screen**
- Single Karachi city card (post-MVP: expandable to multiple cities)
- Card: status badge (`NORMAL` / `WARNING` / `CRITICAL`), active incident count, last updated time
- Status badge pulses with animation when `critical`
- WebSocket updates card live when Commander changes city state

**Incident Feed Screen**
- List of incident cards sorted by `created_at` desc
- Each card: crisis type icon, status badge (see table above), confidence score, timestamp
- Filter bar: by crisis type, by status (pending_approval filter useful for operators)
- New cards animate in via WebSocket — no manual refresh needed

**Incident Detail Screen**
- Header: crisis type + severity + status badge
- **Agent Reasoning Trace** — expandable, Gemini's full reasoning text
- **Signal Evidence** — sensor readings + social post count + sample raw_text
- **Before / After State** — two-panel diff (shown only after Commander acts):
  ```
  BEFORE                      AFTER
  Status: Normal      →       Status: Critical
  Routes: 2 open      →       Routes: 1 open, 1 blocked
  Tickets: 0          →       Tickets: 1 open (NDMA)
  ```
- **Actions Taken** — timeline of Commander's actions with timestamps
  (shown only after Commander acts — auto or approved)
- **Approve Button** — shown only when `status=pending_approval`:
  - Tapping calls `POST /incidents/{id}/approve`
  - Button changes to spinner → then to `APPROVED` confirmation
  - WebSocket `incident_approved` event triggers feed card badge update
  - Actions Taken section populates as Commander executes

**Map Panel**
- Map centered on Karachi
- Incident pins: red (critical/auto_escalated), amber (pending_approval), grey (feed_only)
- Tap pin → mini card with status badge + Approve shortcut for pending incidents
- Flooded zones highlighted; affected routes shown after Commander acts

### WebSocket Push Flow

```
Analyst writes incident to DB
        │
        ▼
FastAPI WS broadcasts:
{ "event": "incident_created", "incident_id": "uuid",
  "severity": "critical"|"medium"|"low",
  "status": "auto_escalated"|"pending_approval"|"feed_only" }
        │
        ├─ critical → Flutter shows 🔴 CRITICAL card
        │            Commander already acting
        │
        ├─ medium  → Flutter shows 🟡 AWAITING APPROVAL card
        │            Operator taps Approve → POST /incidents/{id}/approve
        │            FastAPI triggers Commander medium action set
        │            WS broadcasts: { "event": "incident_approved", "incident_id": "uuid" }
        │            Flutter re-fetches incident, populates Actions Taken
        │
        └─ low     → Flutter shows ⚪ MONITORING card. No further action.
```

---

## 7. Commander Actions Per Severity

Commander is a `BaseAgent` — deterministic, no LLM. It reads the incident
from DB and pattern-matches on `crisis_type + severity` to execute the
correct action set.

### Critical Path — Autonomous (no approval needed)
Triggered immediately when Analyst writes `severity=critical`.

| # | Action | What happens |
|---|---|---|
| 1 | Create emergency ticket | Inserts row in `tickets` (status=open, authority=NDMA) |
| 2 | Update city state | Writes before/after snapshot to `city_state` (status → critical) |
| 3 | Simulate route impact | Updates `routes` — marks flood-affected roads as `blocked` |
| 4 | Dispatch authority alert | Stores drafted NDMA alert in `actions` as `dispatched` |

### Medium Path — Post-Approval (operator must tap Approve)
Triggered when operator calls `POST /incidents/{id}/approve`.

| # | Action | What happens |
|---|---|---|
| 1 | Create monitoring ticket | Inserts row in `tickets` (status=monitoring, authority=NDMA) |
| 2 | Update city state | Writes before/after snapshot to `city_state` (status → warning) |
| 3 | Dispatch advisory alert | Stores advisory (not emergency) alert in `actions` as `dispatched` |

> Medium path has 3 actions (no route blocking — not severe enough to reroute without confirmation).

### Low Path — Feed Only
Commander does not act. Incident written to feed by Analyst. No tickets, no alerts.

**Authority (MVP):**
| Crisis | City | Authority |
|---|---|---|
| Urban Flooding | Karachi | NDMA |

---

## 8. Project Structure

```
ciro/
├── agents/
│   ├── sentinel/
│   │   ├── sentinel_agent.py
│   │   └── collectors/
│   │       ├── base.py
│   │       ├── weather_collector.py
│   │       ├── traffic_collector.py
│   │       └── social_collector.py
│   ├── analyst/
│   │   ├── analyst_agent.py
│   │   └── gemini_stub.py
│   └── commander/
│       └── commander_agent.py
├── api/
│   ├── main.py
│   ├── routers/
│   │   ├── cities.py
│   │   ├── incidents.py
│   │   ├── map.py
│   │   ├── signals.py
│   │   └── demo.py
│   └── websocket.py
├── db/
│   ├── models.py
│   ├── migrations/
│   └── seed.py
├── mock_data/
│   ├── weather_signals.json
│   ├── traffic_signals.json
│   └── social_signals.json
├── mobile/
│   └── lib/
│       ├── screens/
│       │   ├── home_screen.dart
│       │   ├── feed_screen.dart
│       │   ├── detail_screen.dart
│       │   └── map_screen.dart
│       └── services/
│           ├── api_service.dart
│           └── websocket_service.dart
├── .env.example
└── README.md
```
