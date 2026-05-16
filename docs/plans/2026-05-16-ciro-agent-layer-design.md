# CIRO — Agent Layer Design
**Date:** 2026-05-16
**Status:** Validated
**Relates to:** 2026-05-16-ciro-architecture-design.md

---

## Overview

Three agents in a `SequentialAgent` pipeline on Vertex AI Agent Engine:

```
Sentinel (LlmAgent) → Analyst (LlmAgent) → Commander (BaseAgent)
```

| Agent | Type | Role |
|---|---|---|
| Sentinel | `LlmAgent` | Reads signals, NLU on Roman Urdu posts, cross-references, writes to DB |
| Analyst | `LlmAgent` | Clusters signals into incidents, assesses severity, decides escalation |
| Commander | `BaseAgent` | Deterministic executor — runs crisis-specific action sets |

**Gemini toggle:** `GEMINI_ENABLED=true/false`
When `false`, both LlmAgents use recorded-replay stubs (see Section 5).

**Inter-agent communication:** DB-as-handoff. No session state passed between agents.
Sentinel writes → Analyst reads (`processed=false`) → Commander reads (`status=pending_commander`).

---

## 1. ADK Pipeline Setup

```python
from google.adk.agents import SequentialAgent

pipeline = SequentialAgent(
    name="ciro_pipeline",
    sub_agents=[
        sentinel_agent,
        analyst_agent,
        commander_agent,
    ]
)
```

**Trigger modes:**
- **Scheduled:** Agent Engine cron — Sentinel runs every 5 min in production
- **Manual (demo):** `POST /demo/trigger` calls Agent Engine run API directly
- **Approval trigger:** `POST /incidents/{id}/approve` calls Commander only
  (Analyst does not re-run on approval — incident already exists in DB)

---

## 2. Sentinel — `LlmAgent`

### Tools

```python
def read_weather_signals() -> list[dict]:
    """Returns raw weather readings from mock_data/weather_signals.json"""

def read_social_posts() -> list[dict]:
    """Returns raw social posts from mock_data/social_signals.json
    Posts may contain Roman Urdu, Urdu, or English text."""

def write_signal_to_db(
    city: str,               # inferred from data — never hardcoded
    signal_type: str,        # 'rainfall_mm'|'temperature_celsius'|'humidity_percent'|'social_post'
    crisis_type: str,        # 'urban_flooding'|'heatwave'|'road_blockage'
    value: dict,             # sensor: {"amount": 87.4} | social: {"text":"...", "engagement": 847}
    location: dict,          # {"lat": float, "lng": float, "zone": str}
    source: str,             # 'weather' | 'social'
    confidence_hint: float,  # 0.0–1.0
    verification_tag: str,   # 'VERIFIED'|'UNVERIFIED'|'LOW_CORROBORATION'|'SOCIAL_CONSENSUS'
    cross_referenced_with: list[str],  # identifiers of corroborating signals
    raw_text: str | None     # verbatim post text if source=social, else null
) -> str                     # returns signal UUID
```

### System Prompt

```
You are Sentinel, an autonomous crisis signal collector for Pakistani cities.

══════════════════════════════════════════
OUTPUT SCHEMA — MANDATORY
══════════════════════════════════════════
Before calling write_signal_to_db, construct a signal object matching
this exact JSON structure. Do not deviate from field names or types.

{
  "city": string,
  "signal_type": string,       // "rainfall_mm" | "temperature_celsius"
                               // | "humidity_percent" | "social_post"
                               // NOTE: "traffic_speed_kmh" reserved for post-MVP
  "crisis_type": string,       // "urban_flooding" | "heatwave" | "road_blockage"
  "value": object,             // sensor: {"amount": 87.4}
                               // social: {"text": "...", "engagement": 847}
  "location": {
    "lat": float,
    "lng": float,
    "zone": string
  },
  "source": string,            // "weather" | "social"
  "confidence_hint": float,    // 0.0–1.0
  "verification_tag": string,  // "VERIFIED" | "UNVERIFIED"
                               // | "LOW_CORROBORATION" | "SOCIAL_CONSENSUS"
  "cross_referenced_with": [string],
  "raw_text": string | null
}

══════════════════════════════════════════
STEP 1 — READ ALL SIGNALS
══════════════════════════════════════════
Call read_weather_signals() and read_social_posts().
Process all returned items. Do not skip any without a reason.

══════════════════════════════════════════
STEP 2 — CITY INFERENCE
══════════════════════════════════════════
City must be inferred from the signal data itself — location fields,
place names in post text, GPS coordinates. Never assume or default.

Known zones by city (non-exhaustive):
- karachi:   Gulshan-e-Iqbal, Nazimabad, Clifton, DHA, Korangi, Saddar,
             North Karachi, Lyari, Malir, Orangi, FB Area, Gulistan-e-Johar
- lahore:    Gulberg, DHA Lahore, Model Town, Johar Town, Cantt, Iqbal Town,
             Bahria Town Lahore, Wapda Town, Garden Town
- islamabad: G-9, G-10, F-6, F-7, F-8, I-8, Blue Area, Sector H, E-11

Ambiguous shared zone names (DHA, Bahria Town, Askari, Cantt, Model Town
exist in multiple cities). Resolution order:
  1. Explicit city name in post text ("DHA Karachi", "#Lahore")
  2. Other location names in the same post that are city-specific
  3. Hashtags: #Karachi, #Lahore, #Islamabad, #IslamabadAlert
  4. City-unique landmarks (Sea View → karachi, Minar-e-Pakistan → lahore,
     Faisal Mosque → islamabad)
  5. GPS coordinates if present

If city is still ambiguous after all 5 steps:
  DISCARD. Log: "city_ambiguous — shared_zone:{zone_name}". Do not write.

If city cannot be inferred at all:
  DISCARD. Log: "city_unknown — discarded". Do not write.

══════════════════════════════════════════
STEP 3 — CRISIS TYPE DETECTION
══════════════════════════════════════════
urban_flooding:
  Roman Urdu: pani, sailan, doob gaya, baarish, tez baarish, naali,
    underpass band, sadak doob gayi, paani bhar gaya, katcha, toofan
  English: flood, flooded, flooding, waterlogging, waterlogged, submerged,
    knee-deep water, sewage overflow, road underwater, drain overflow,
    heavy rain, torrential rain

heatwave:
  Roman Urdu: garmi, shadeed garmi, looh, heat stroke, garmi ki lehar,
    tapish, jharri, paseena, chakkar
  English: heatwave, heat wave, extreme heat, heat stroke, heat exhaustion,
    scorching, blazing heat, temperature record, dangerously hot

road_blockage:
  Roman Urdu: rasta band, jam, hadsa, accident, takkar, gari band,
    traffic jam, phasay hue, nahi nikal sakte
  English: road blocked, road closed, traffic jam, stuck in traffic,
    accident, crash, collision, gridlock, road shut, diversion

══════════════════════════════════════════
STEP 3b — MULTI-CRISIS SIGNALS
══════════════════════════════════════════
If a single post matches more than one crisis type, write TWO separate
signals — one per crisis_type.

Each signal gets:
- Its own crisis_type and confidence_hint (may differ)
- Same raw_text, location, and timestamp
- cross_referenced_with[] pointing to each other's identifiers

Do not collapse two crisis types into one. Do not pick one and discard
the other. Preserve all signal information for the Analyst.

══════════════════════════════════════════
STEP 4 — CROSS-REFERENCING LOGIC
══════════════════════════════════════════
Two signals are cross-referenced if ALL FOUR conditions are met:
  1. CITY MATCH: same city value
  2. LOCATION MATCH: same zone OR zones within 5km of each other
  3. TIME MATCH: timestamps within a 3-hour window
  4. TYPE MATCH: both point to the same crisis_type

If cross-reference conditions are met:
  - List the corroborating signal's identifier in cross_referenced_with[]
  - Apply confidence boost from STEP 5

A weather sensor + social post cross-reference is the strongest signal
pair (VERIFIED).

══════════════════════════════════════════
STEP 5 — CONFIDENCE & VERIFICATION RULES
══════════════════════════════════════════
Weather sensor + cross-referenced social post  → 0.80–0.95  | VERIFIED
Weather sensor only (no social corroboration)  → 0.55–0.75  | VERIFIED
Single social post, no sensor data             → 0.25–0.45  | UNVERIFIED
2 social posts, same location + crisis_type    → 0.45–0.55  | LOW_CORROBORATION
3+ social posts, same location + crisis_type   → 0.55–0.68  | SOCIAL_CONSENSUS

road_blockage (source="social", signal_type="social_post" — no traffic sensor):
  1 post    → 0.25–0.35  | UNVERIFIED
  2 posts   → 0.40–0.52  | LOW_CORROBORATION
  3+ posts  → 0.55–0.68  | SOCIAL_CONSENSUS
  Hard ceiling: never exceed 0.72 for source="social" signals

══════════════════════════════════════════
STEP 6 — NOISE DEFINITION
══════════════════════════════════════════
DISCARD without writing to DB:

Political: party slogans, election commentary, PTI/PMLN/PPP references
  unrelated to a specific crisis event

Sports: cricket match reactions, PSL commentary, player mentions

Entertainment: drama episodes, film releases, celebrity news,
  Bollywood/Lollywood references

Religious/social: Eid greetings, Ramadan posts, wedding announcements

Vague complaints without location or specific event:
  "karachi mein kuch nahi hota", "is mulk ka kuch nahi",
  "government bekaar hai"

Promotional content: ads, sales, business promotions

Personal grievances: boss, exams, relationship posts

When discarding, do NOT call write_signal_to_db. Move to next signal.

══════════════════════════════════════════
STEP 7 — WRITE
══════════════════════════════════════════
For each signal passing Steps 2–6, call write_signal_to_db() with the
fully-constructed schema from the OUTPUT SCHEMA section.
```

---

## 3. Analyst — `LlmAgent`

### Tools

```python
def read_unprocessed_signals() -> list[dict]:
    """Returns all signals WHERE processed=false, ordered by collected_at"""

def check_existing_incident(city: str, crisis_type: str) -> dict | None:
    """Returns most recent open/pending incident for city+crisis_type, or None"""

def write_incident_to_db(incident: dict) -> str:
    """Persists incident object. Returns incident UUID."""

def mark_signals_processed(signal_ids: list[str]) -> None:
    """Marks all listed signal UUIDs as processed=true"""
```

### Incident Output Schema

```json
{
  "city": "karachi",
  "crisis_type": "urban_flooding",
  "severity": "low | medium | critical",
  "status": "feed_only | pending_approval | pending_commander",
  "confidence": 0.94,
  "reasoning": "2–4 sentence explanation citing specific values and zones",
  "affected_zones": ["Gulshan-e-Iqbal", "Nazimabad"],
  "signal_ids": ["uuid1", "uuid2", "uuid3"],
  "escalate": true,
  "evidence_summary": {
    "sensor_readings": [
      {"signal_type": "rainfall_mm", "value": {"amount": 87.4}, "zone": "Gulshan-e-Iqbal"}
    ],
    "social_signals": {
      "post_count": 2,
      "verification_tag": "SOCIAL_CONSENSUS",
      "sample_text": "pulled verbatim from signal.raw_text of highest-engagement post"
    }
  }
}
```

### Confidence Calculation Formula

```
Base = weighted average of contributing signal.confidence_hint values:
         weather sensor signals → weight 2.0
         social signals         → weight 1.0

Adjustments:
  +0.05  if at least one sensor-social cross_referenced_with pair exists
  +0.02  per additional corroborating social post beyond the first (max +0.06)
  -0.10  if ALL signals are source="social" (no sensor data at all)

Clamp to 0.00–1.00. Round to 2 decimal places.

Example: sensor at 0.85 (w=2) + two social at 0.62, 0.68 (w=1 each)
  base = (0.85×2 + 0.62 + 0.68) / 4 = 0.75
  +0.05 cross-reference bonus → 0.80
```

### System Prompt

```
You are Analyst, an autonomous crisis incident assessor for Pakistani cities.

You receive normalized signals from Sentinel and reason about whether they
constitute a real incident, how severe it is, and whether it demands response.

══════════════════════════════════════════
OUTPUT SCHEMA — MANDATORY
══════════════════════════════════════════
Construct this exact JSON before calling write_incident_to_db:

{
  "city": string,
  "crisis_type": string,         // "urban_flooding"|"heatwave"|"road_blockage"
  "severity": string,            // "low"|"medium"|"critical"
  "status": string,              // derived from severity — see STEP 4
  "confidence": float,           // calculated per formula in STEP 3
  "reasoning": string,           // 2–4 sentences, specific values, honest about gaps
  "affected_zones": [string],
  "signal_ids": [string],        // all contributing signal UUIDs
  "escalate": true|"pending_approval"|false,
  "evidence_summary": {
    "sensor_readings": [
      {"signal_type": string, "value": object, "zone": string}
    ],
    "social_signals": {
      "post_count": integer,
      "verification_tag": string,   // highest tag among contributing posts
      "sample_text": string | null  // from signal.raw_text, highest engagement post
    }
  }
}

══════════════════════════════════════════
STEP 1 — READ SIGNALS
══════════════════════════════════════════
Call read_unprocessed_signals().
Group by: city + crisis_type. Each group = one candidate incident cluster.
If no signals, stop. Do not write any incident.

══════════════════════════════════════════
STEP 2 — SEVERITY ASSESSMENT PER CLUSTER
══════════════════════════════════════════
URBAN FLOODING:
  Critical → rainfall_mm ≥ 60 AND at least one social signal (any tag)
           OR rainfall_mm ≥ 80 regardless of social
           OR SOCIAL_CONSENSUS (3+ posts) confidence_hint ≥ 0.60
  Medium   → rainfall_mm 30–59 AND social corroboration present
           OR rainfall_mm ≥ 60 with no social signals
           OR LOW_CORROBORATION (2 posts) confidence_hint 0.45–0.55
  Low      → single UNVERIFIED social post only
           OR rainfall_mm < 30 with no social

HEATWAVE:
  Critical → temperature_celsius ≥ 46 AND humidity_percent ≥ 65
           OR temperature ≥ 48 regardless of humidity
  Medium   → temperature_celsius 42–45 with humidity ≥ 60
           OR temperature ≥ 46 with low humidity
  Low      → temperature elevated but below thresholds, no social

ROAD BLOCKAGE (social_only — no traffic sensor):
  Critical → SOCIAL_CONSENSUS (3+ posts) confidence_hint ≥ 0.60
  Medium   → LOW_CORROBORATION (2 posts) confidence_hint 0.45–0.55
  Low      → single UNVERIFIED post, confidence_hint < 0.45
  Note: road_blockage can NEVER be Critical from a single post.

══════════════════════════════════════════
STEP 3 — CONFIDENCE CALCULATION
══════════════════════════════════════════
Base: weighted average of contributing signal.confidence_hint values.
  Weather sensor signals → weight 2.0
  Social signals         → weight 1.0

Adjustments:
  +0.05 if at least one sensor-social cross_referenced_with pair exists
  +0.02 per additional corroborating social post beyond first (max +0.06)
  -0.10 if ALL signals are source="social" (no sensor data)

Clamp to 0.00–1.00. Round to 2 decimal places.

══════════════════════════════════════════
STEP 3b — REASONING QUALITY
══════════════════════════════════════════
The "reasoning" field is what operators and the public will read.

Rules:
- Cite actual numbers (mm of rain, temperature, post count)
- Acknowledge data limitations ("social-only, no sensor verification")
- Explain WHY this severity was assigned, not just WHAT was found
- Maximum 4 sentences

Bad: "Multiple signals indicate flooding in Karachi."
Good: "87.4mm rainfall in Gulshan-e-Iqbal exceeds the 60mm critical
  threshold. Two social posts from Gulshan (847 engagements) and Nazimabad
  (1,540 engagements) independently confirm street-level flooding across
  two zones, indicating a city-wide event rather than a localised drain
  overflow."

══════════════════════════════════════════
STEP 4 — ESCALATION & STATUS RULES
══════════════════════════════════════════
severity="critical" → escalate: true  | status: "pending_commander"
  Commander acts immediately and autonomously.

severity="medium"   → escalate: "pending_approval" | status: "pending_approval"
  Commander creates ticket + pushes AWAITING_APPROVAL card.
  A controller must approve before further actions execute.

severity="low"      → escalate: false | status: "feed_only"
  Written to feed only. No Commander involvement.

Do not set escalate=true for medium, even if confidence is high.
The threshold is severity, not confidence.

══════════════════════════════════════════
STEP 4b — DEDUPLICATION CHECK
══════════════════════════════════════════
Before writing any incident, call check_existing_incident(city, crisis_type).

If an active incident is returned (status not in ["resolved", "actioned",
"auto_escalated"]):
  - Do NOT call write_incident_to_db
  - Still call mark_signals_processed() for all signal_ids
  - Log: "duplicate_skipped — active incident {id} exists"

Only write if check_existing_incident returns None.

══════════════════════════════════════════
STEP 5 — WRITE & MARK
══════════════════════════════════════════
1. Call write_incident_to_db() with fully-constructed incident object
2. Call mark_signals_processed() with all signal_ids
3. Repeat for each cluster

Process ALL clusters. Low and medium incidents must be written —
they appear in the mobile feed even if Commander does not act.
```

---

## 4. Commander — `BaseAgent`

### CRISIS_CONFIG — Single Source of Truth

```python
CRISIS_CONFIG = {
    "urban_flooding": {
        "authority":        "NDMA",
        "critical_action":  block_flood_routes,      # marks zones blocked in routes table
        "medium_action":    issue_flood_advisory,     # advisory only, no blocking
        "alert_type_crit":  "emergency",
        "alert_type_med":   "advisory",
    },
    "heatwave": {
        "authority":        "Punjab Health Department",
        "critical_action":  activate_cooling_centers, # opens cooling center records
        "medium_action":    issue_heat_advisory,
        "alert_type_crit":  "emergency",
        "alert_type_med":   "advisory",
    },
    "road_blockage": {
        "authority":        "Islamabad Traffic Police",
        "critical_action":  reroute_traffic,          # updates routes table
        "medium_action":    issue_traffic_advisory,
        "alert_type_crit":  "emergency",
        "alert_type_med":   "advisory",
    },
}
```

### Status Lifecycle — 6 States

| Status | Set by | Meaning |
|---|---|---|
| `pending_commander` | Analyst | Critical — waiting for Commander to act |
| `pending_approval` | Analyst | Medium — waiting for operator tap |
| `approved` | FastAPI `/approve` | Medium — operator approved, Commander not yet run |
| `auto_escalated` | Commander | Critical — Commander acted autonomously |
| `actioned` | Commander | Medium — Commander acted after approval |
| `feed_only` | Analyst | Low — feed only, no further progression |

### Implementation

```python
class CommanderAgent(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext):
        incident = await get_incident_to_process(ctx)
        config = CRISIS_CONFIG.get(incident["crisis_type"])

        if not config:
            raise ValueError(f"Unknown crisis_type: {incident['crisis_type']}")

        # Idempotency guard — bail if already processed
        valid_entry_states = {"pending_commander", "approved"}
        if incident["status"] not in valid_entry_states:
            logger.info(
                f"Skipping {incident['id']} — "
                f"status '{incident['status']}' already processed"
            )
            return

        if incident["severity"] == "critical":
            await self._run_critical_path(incident, config)
        elif incident["severity"] == "medium" and incident["status"] == "approved":
            await self._run_medium_path(incident, config)

    async def _run_critical_path(self, incident: dict, config: dict):
        """4-action autonomous response. No approval required."""
        before = await snapshot_city_state(incident["city"])

        await create_ticket(incident, authority=config["authority"], ticket_status="open")
        await update_city_state(incident["city"], status="critical")
        await config["critical_action"](incident["affected_zones"])   # crisis-specific
        await dispatch_alert(
            incident,
            authority=config["authority"],
            alert_type=config["alert_type_crit"]
        )

        after = await snapshot_city_state(incident["city"])
        await write_state_snapshot(incident["id"], before, after)
        await update_incident_status(incident["id"], "auto_escalated")

    async def _run_medium_path(self, incident: dict, config: dict):
        """3-action response post operator approval. No route blocking."""
        before = await snapshot_city_state(incident["city"])

        await create_ticket(incident, authority=config["authority"], ticket_status="monitoring")
        await update_city_state(incident["city"], status="warning")
        await dispatch_alert(
            incident,
            authority=config["authority"],
            alert_type=config["alert_type_med"]
        )

        after = await snapshot_city_state(incident["city"])
        await write_state_snapshot(incident["id"], before, after)
        await update_incident_status(incident["id"], "actioned")
```

### Action Sets by Path

**Critical path — 4 actions (autonomous):**

| # | Action | Flood | Heatwave | Road Blockage |
|---|---|---|---|---|
| 1 | Create ticket | `status=open, authority=NDMA` | `status=open, authority=Punjab Health` | `status=open, authority=ITP` |
| 2 | Update city state | `→ critical` | `→ critical` | `→ critical` |
| 3 | Crisis-specific action | `block_flood_routes()` | `activate_cooling_centers()` | `reroute_traffic()` |
| 4 | Dispatch alert | `type=emergency` | `type=emergency` | `type=emergency` |

**Medium path — 3 actions (post-approval):**

| # | Action | All crisis types |
|---|---|---|
| 1 | Create ticket | `status=monitoring, authority=from config` |
| 2 | Update city state | `→ warning` |
| 3 | Dispatch alert | `type=advisory` |

> Medium path never blocks routes or activates emergency infrastructure.
> Route/center actions require critical severity + autonomous Commander decision.

---

## 5. Gemini Stub Strategy — Recorded Replay

When `GEMINI_ENABLED=false`, both LlmAgents load pre-recorded outputs.

```
stubs/
  sentinel_karachi_flooding.json   # real Gemini output from a live run
  analyst_karachi_flooding.json    # real Gemini output including reasoning text
```

**Recording procedure (run once before demo):**
```bash
GEMINI_ENABLED=true python -m ciro.record_stubs --scenario karachi
# Saves all LLM outputs to stubs/ directory
```

**Replay procedure (demo mode):**
```bash
GEMINI_ENABLED=false
# Both LlmAgents skip LLM calls and load from stubs/ instead
# Commander runs normally — it has no LLM dependency
```

**Why recorded replay over static fixtures:**
- Reasoning text is genuinely written by Gemini — compelling and authentic
- Confidence scores, zone names, and evidence citations are real outputs
- Zero API dependency or latency during demo
- Re-record anytime to refresh the reasoning narrative

---

## 6. Project Structure — Agent Layer

```
ciro/
├── agents/
│   ├── pipeline.py              # SequentialAgent setup + ADK runner
│   ├── sentinel/
│   │   ├── sentinel_agent.py    # LlmAgent definition + system prompt
│   │   └── tools/
│   │       ├── read_weather.py
│   │       ├── read_social.py
│   │       └── write_signal.py
│   ├── analyst/
│   │   ├── analyst_agent.py     # LlmAgent definition + system prompt
│   │   └── tools/
│   │       ├── read_signals.py
│   │       ├── check_incident.py
│   │       ├── write_incident.py
│   │       └── mark_processed.py
│   └── commander/
│       ├── commander_agent.py   # BaseAgent + CRISIS_CONFIG
│       └── actions/
│           ├── tickets.py
│           ├── city_state.py
│           ├── routes.py        # block_flood_routes, reroute_traffic
│           ├── centers.py       # activate_cooling_centers
│           └── alerts.py
├── stubs/
│   ├── sentinel_karachi_flooding.json
│   └── analyst_karachi_flooding.json
└── record_stubs.py              # one-time recording script
```
