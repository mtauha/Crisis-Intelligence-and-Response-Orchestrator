# CIRO — Development Roadmap
**Project:** Crisis Intelligence & Response Orchestrator
**Deadline:** May 20, 2026
**Team:**
- **Muhammad** — AI Agents + Backend (FastAPI, PostgreSQL, Vertex AI)
- **Affan** — Frontend (Flutter, Mapbox, Riverpod)

**Demo target:** Single city (Karachi), single crisis (Urban Flooding), full autonomous pipeline on stage.

---

## Status Legend

| Symbol | Meaning |
|--------|---------|
| 🔴 Must Have | Blocking the demo — ship or fail |
| 🟡 Should Have | Strongly expected; cut only if time-critical |
| 🟢 Nice to Have | Polish; cut freely if needed |
| 👤 Muhammad | AI Agents + Backend owner |
| 👥 Affan | Flutter Frontend owner |
| 🤝 Both | Requires coordination or shared effort |

---

## Capacity Plan

| Day | Date | Muhammad | Affan |
|-----|------|----------|---------|
| 1 | May 16 | Foundation + Agents start | Foundation + Flutter setup |
| 2 | May 17 | Agents complete + API start | Models, services, providers |
| 3 | May 18 | API complete | Screens (Home, Feed) |
| 4 | May 19 | Gemini stubs + Cloud deploy | Screens (Detail, Map) + Integration |
| 5 | May 20 | Hardening + demo rehearsal | Polish + demo rehearsal |

**Rule:** Both tracks must reach the integration checkpoint (Phase 5) by end of Day 3 (May 18). If either track is behind, drop 🟢 tasks immediately — never sacrifice integration for polish.

---

## Phase 0 — Foundation
**Timeline:** Day 1 (May 16) | **Owner:** 🤝 Both | **Priority:** 🔴

This phase must be completed together before either track diverges. Blocking everything downstream.

### Tasks

| # | Task | Owner | Priority | Notes |
|---|------|-------|----------|-------|
| 0.1 | Initialize monorepo structure per `ciro/` layout in architecture doc | 🤝 Both | 🔴 | Agree on folder layout before any code is written |
| 0.2 | Write PostgreSQL schema — all 6 tables (`signals`, `incidents`, `city_state`, `actions`, `tickets`, `routes`) | 👤 Muhammad | 🔴 | Copy from architecture doc; add indexes on `city`, `status`, `processed` |
| 0.3 | Write Alembic migration files — schema + PostgreSQL LISTEN/NOTIFY trigger function | 👤 Muhammad | 🔴 | `notify_incident_change()` trigger must be in a migration, not applied manually |
| 0.4 | Write `db/seed.py` — Karachi `city_state` baseline + mock Karachi routes (GeoJSON) | 👤 Muhammad | 🔴 | `city_state` seed row required before any agent or API call succeeds. Route GeoJSON for 3–4 Karachi roads needed for Commander's `block_flood_routes()` |
| 0.5 | Create mock data files — `weather_signals.json` + `social_signals.json` | 👤 Muhammad | 🔴 | Use values from architecture doc (87.4mm rainfall, Gulshan + Nazimabad posts). Pre-load to breach Urban Flooding threshold |
| 0.6 | Write `.env.example` — all keys for both tracks | 🤝 Both | 🔴 | Agree on `API_KEY` value for local dev so Flutter can hit protected endpoints from day one |
| 0.7 | Flutter project init — `flutter create`, add all `pubspec.yaml` deps, confirm `build_runner` works | 👥 Affan | 🔴 | Run `flutter pub get` + `dart run build_runner build` before writing a single model |
| 0.8 | Obtain Mapbox access token and add to `.env` | 👥 Affan | 🔴 | Mapbox token can take time to provision — do this first, not last |

### Definition of Done
- `docker-compose up` (or equivalent) starts PostgreSQL locally
- Migrations apply cleanly; seed runs without error
- Flutter project compiles and shows a blank screen
- Both members have `.env` populated

---

## Phase 1 — AI Agent Pipeline
**Timeline:** Days 1–2 (May 16–17) | **Owner:** 👤 Muhammad | **Priority:** 🔴

Build the three-agent SequentialAgent pipeline. At the end of this phase, a manual Python invocation should collect mock signals, detect a critical Urban Flooding incident, and write the full incident + actions to the database — with no Flutter or API involved.

### Tasks

| # | Task | Priority | Notes |
|---|------|----------|-------|
| 1.1 | `agents/sentinel/tools/` — implement `read_weather.py`, `read_social.py`, `write_signal.py` | 🔴 | `read_weather` and `read_social` read from `mock_data/`. `write_signal` wraps DB insert. All must match the `BaseCollector`-style interface |
| 1.2 | `agents/sentinel/sentinel_agent.py` — `LlmAgent` with full system prompt | 🔴 | Copy system prompt verbatim from agent layer design doc. Include Roman Urdu keywords, city inference rules, cross-referencing logic, confidence table, and noise filter |
| 1.3 | `agents/analyst/tools/` — implement `read_signals.py`, `check_incident.py`, `write_incident.py`, `mark_processed.py` | 🔴 | `check_incident` must return existing open incident to prevent duplicates (dedup check) |
| 1.4 | `agents/analyst/analyst_agent.py` — `LlmAgent` with full system prompt | 🔴 | Copy system prompt from agent layer design doc. Severity thresholds, confidence formula, escalation rules, dedup check all live here |
| 1.5 | `agents/commander/actions/` — implement `tickets.py`, `city_state.py`, `routes.py`, `alerts.py` | 🔴 | Each action function writes to DB and logs an `Action` row. `block_flood_routes()` marks seeded Karachi routes as `blocked` |
| 1.6 | `agents/commander/commander_agent.py` — `BaseAgent` with `CRISIS_CONFIG` + idempotency guard | 🔴 | Deterministic — no LLM. Entry state check (`pending_commander` or `approved`) must guard against double-execution |
| 1.7 | `agents/pipeline.py` — `SequentialAgent` wiring Sentinel → Analyst → Commander | 🔴 | Include both local runner and Agent Engine trigger modes from the start |
| 1.8 | `stubs/` + `record_stubs.py` — Gemini stub infrastructure | 🟡 | Scaffold the stub loader with `GEMINI_ENABLED=false` path. Recording happens in Phase 6; structure must exist now so agents conditionally branch correctly |
| 1.9 | Local pipeline smoke test — `python -m ciro.pipeline --scenario karachi` | 🔴 | Should write: 2 signals, 1 critical incident (`status=pending_commander`), 4 actions, 1 ticket, 1 route blocked, `city_state=critical`. Verify rows in DB |

### Dependencies
- Phase 0 must be complete (DB schema + seed + mock data files exist)

### Definition of Done
- Running the pipeline locally with `GEMINI_ENABLED=true` (or `false` with hardcoded stub values) produces a complete DB state
- All 6 tables have expected rows after one pipeline run
- Pipeline is idempotent: running it a second time without reset produces no duplicate incident (dedup check fires)

---

## Phase 2 — Backend API
**Timeline:** Days 2–3 (May 17–18) | **Owner:** 👤 Muhammad | **Priority:** 🔴

Build the FastAPI gateway. At the end of this phase, all 10 endpoints respond correctly, the WebSocket broadcasts on DB changes, and the demo trigger/reset cycle works end-to-end without Flutter.

### Tasks

| # | Task | Priority | Notes |
|---|------|----------|-------|
| 2.1 | `db/models.py` — SQLModel models for all 6 tables + 3 response models (`IncidentDetail`, `CityCard`, `IncidentPin`) | 🔴 | Match architecture doc exactly. `ARRAY(PG_UUID)` for `signal_ids` and `cross_referenced_with`. `JSONB` for all `dict` fields |
| 2.2 | `api/config.py` + `api/dependencies.py` — settings, async DB session, API key auth | 🔴 | `require_api_key` dependency must be applied to `/approve`, `/demo/trigger`, `/demo/reset` only. All `GET` endpoints remain open |
| 2.3 | `api/main.py` — FastAPI app init, lifespan (DB listener start/stop), router registration | 🔴 | Lifespan must start `start_db_listener()` before serving any requests |
| 2.4 | `api/routers/cities.py` — `GET /cities`, `GET /cities/{city}/state` | 🔴 | |
| 2.5 | `api/routers/incidents.py` — `GET /incidents` (with filters), `GET /incidents/{id}`, `POST /incidents/{id}/approve` | 🔴 | `/approve` must be atomic conditional update — only succeeds if `status=pending_approval`. Return 409 otherwise. Triggers Commander via `BackgroundTasks` |
| 2.6 | `api/routers/map.py` — `GET /map/pins`, `GET /map/routes/{city}` | 🔴 | `/map/pins` returns lat/lng from `signals.location` JSONB joined to incident. `/map/routes` returns GeoJSON route data |
| 2.7 | `api/routers/signals.py` — `GET /signals` (debug endpoint) | 🟡 | Low effort; useful for judges reviewing raw data |
| 2.8 | `api/routers/demo.py` — `POST /demo/trigger`, `POST /demo/reset` | 🔴 | `reset` must delete in FK-safe order: `routes` → `actions` → `tickets` → `incidents` → `signals`, then reset `city_state` to normal. Guard `trigger` against running when incidents already exist |
| 2.9 | `api/connection_manager.py` — `ConnectionManager` singleton | 🔴 | Singleton pattern critical — both `websocket.py` and `agent_client.py` import the same instance. Avoids circular import |
| 2.10 | `api/websocket.py` — `WS /ws/feed` endpoint + PostgreSQL LISTEN/NOTIFY listener + keep-alive task | 🔴 | `handle_notify` must correctly map `(TG_OP, status)` tuples to the 4 event types Flutter expects |
| 2.11 | `api/agent_client.py` — `AgentClient` with local runner + Agent Engine modes + pipeline status WS broadcasts | 🔴 | `trigger_pipeline` broadcasts `pipeline_started` before running and `pipeline_complete` after. `trigger_commander` does not broadcast — feedback comes via DB trigger |
| 2.12 | API integration test — `POST /demo/trigger` → pipeline runs → `GET /incidents` returns 1 critical incident → WS client receives `incident_created` event | 🔴 | Use a simple `websockets` Python client to verify WS broadcast. Curl or HTTPie for REST |

### Dependencies
- Phase 1 must be complete (pipeline runs and writes to DB)
- Phase 0.3 (LISTEN/NOTIFY migration) must be applied before 2.10

### Definition of Done
- All 10 endpoints return correct data (test with curl)
- WS client receives `incident_created` + `incident_actioned` events during a full trigger cycle
- Demo reset clears all tables and city_state returns to `normal`
- Approval flow: `POST /approve` on a `pending_approval` incident triggers Commander, incident moves to `actioned`

---

## Phase 3 — Flutter Foundation
**Timeline:** Days 1–2 (May 16–17) | **Owner:** 👥 Affan | **Priority:** 🔴

Build all non-visual infrastructure for the Flutter app. At the end of this phase, providers are wired to live API responses (even if the backend is stubbed locally), WebSocket events update state, and navigation works.

### Tasks

| # | Task | Priority | Notes |
|---|------|----------|-------|
| 3.1 | `config/app_config.dart` — load `.env` via `flutter_dotenv` (base URL, WS URL, API key, Mapbox token) | 🔴 | |
| 3.2 | `models/` — write `incident.dart`, `city_state.dart`, `signal.dart`, `ws_event.dart` with `@freezed` + `@JsonSerializable` | 🔴 | Run `dart run build_runner build` after each model. `WsEvent` uses a custom `fromJson` factory that branches on `event.startsWith('pipeline_')` |
| 3.3 | `services/api_service.dart` — Dio with two instances: `_publicDio` (no auth) + `_protectedDio` (X-API-Key header) | 🔴 | Implement all 8 methods from the Flutter design doc. A misconfigured API key must only break write endpoints — reads must remain functional |
| 3.4 | `services/ws_service.dart` — WebSocket with auto-reconnect (3s delay) + 20s ping timer + broadcast `StreamController` | 🔴 | Add `AppLifecycleObserver` to reconnect when app returns from background — this is missing from the design doc and will cause silent failures on a demo device |
| 3.5 | `providers/` — implement all 7 providers: `Cities`, `Incidents`, `IncidentDetail` (family), `ApproveIncident` (family), `MapPins`, `MapRoutes`, `DemoControls` | 🔴 | Wire each provider's WS invalidation logic per the event→provider mapping table in the Flutter design doc |
| 3.6 | `router.dart` — `ShellRoute` + bottom nav (Home, Feed, Map) + `AppShell` with WS snackbar listener | 🔴 | WS snackbar listener belongs in `AppShell`, not `main.dart` — guaranteed mounted context avoids null crashes |
| 3.7 | `main.dart` — `ProviderScope`, `dotenv.load`, `MaterialApp.router` | 🔴 | |

### Dependencies
- Phase 0.7 + 0.8 (Flutter init + Mapbox token) must be complete
- Muhammad should share the `API_KEY` value and local backend URL on Day 2 so Affan can test providers against real data

### Definition of Done
- `flutter run` compiles with no errors
- `citiesProvider` fetches real data from local backend (or a mock JSON server as fallback)
- WS events received in `wsEventsProvider` stream trigger `ref.invalidateSelf()` on the correct providers
- Navigation between all 3 tabs works

---

## Phase 4 — Flutter Screens
**Timeline:** Days 2–4 (May 17–19) | **Owner:** 👥 Affan | **Priority:** 🔴 (core screens), 🟡 (polish)

Build all 4 screens and shared widgets. Screens should be built against live backend data — no mocking inside Flutter.

### Tasks

| # | Task | Priority | Notes |
|---|------|----------|-------|
| 4.1 | Shared widgets — `StatusBadge`, `SeverityChip`, `ConfidenceBar`, `ErrorBanner`, skeleton loaders | 🔴 | Build these first — all 4 screens depend on them. `StatusBadge` drives 3 colours: red (`auto_escalated`), amber (`pending_approval`), grey (`feed_only`) |
| 4.2 | Home Screen — `CityCard` with status badge + active incident count, `DemoControls` (trigger/reset buttons) | 🔴 | `DemoControls` listens to `wsEventsProvider` for `pipeline_started`, `pipeline_error`, `pipeline_complete`. Trigger button disables while pipeline runs or incidents exist |
| 4.3 | Incident Feed Screen — `ListView`, `IncidentCard`, filter bar | 🔴 | New cards must animate in when `incident_created` WS event fires — `AnimatedList` or `AnimatedSwitcher`. Filter bar: by crisis type + by status |
| 4.4 | Incident Detail — `DetailHeader`, `ReasoningSection`, `EvidenceSection` | 🔴 | `ReasoningSection` is the judges' window into the AI. Make it prominent and readable |
| 4.5 | Incident Detail — `BeforeAfterSection` (conditional on `stateSnapshot != null`) + `ActionsTimeline` (conditional on `actionsTaken.isNotEmpty`) | 🔴 | These sections only appear after Commander acts. They should animate in when the `incident_actioned` WS event is received and provider re-fetches |
| 4.6 | Incident Detail — `ApproveButton` (conditional on `status=pending_approval`) | 🔴 | Family-scoped provider prevents approve state bleeding between incidents. Button → spinner → WS event drives final state, not manual invalidation |
| 4.7 | Map Screen — Mapbox `MapWidget`, single `PointAnnotationManager`, pins by severity | 🔴 | Use a **single** annotation manager for all pins — Mapbox has a hard limit on manager count. Icons: `incident-critical` (red), `incident-pending` (amber), `incident-monitoring` (grey). Register custom icons as Mapbox style assets before adding annotations |
| 4.8 | Map Screen — route polylines + flood zone polygons | 🟡 | Route statuses from `GET /map/routes/karachi`. Blocked routes in red, open in green. Flood zone polygon for Gulshan-e-Iqbal + Nazimabad zones |
| 4.9 | Map Screen — tap pin → mini card with status badge + Approve shortcut for `pending_approval` pins | 🟡 | |
| 4.10 | Critical status badge pulsing animation (Home Screen `CityCard` + Feed `IncidentCard`) | 🟡 | `AnimationController` with repeat + `FadeTransition` or `ScaleTransition` on the red badge |
| 4.11 | App background reconnect — `AppLifecycleObserver` in `WsService` | 🟡 | Was omitted from design doc. Without this, the demo device loses WS connection after screen lock and never recovers silently. High risk for a demo scenario |

### Dependencies
- Phase 3 complete (providers + services working)
- Phase 2 complete (backend up with real data) by Day 3 for integration work

### Definition of Done
- All 4 screens render with live data
- `pending_approval` incident shows Approve button; tapping it updates the UI via WS (no manual refresh)
- Map shows pins after a pipeline trigger
- `BeforeAfterSection` populates on Detail screen after Commander acts

---

## Phase 5 — Integration & Contract Testing
**Timeline:** Day 3–4 (May 18–19) | **Owner:** 🤝 Both | **Priority:** 🔴

This is the most critical coordination phase. Both tracks converge. The goal is to verify the full end-to-end demo scenario works exactly as it will on stage — including all edge cases the judges will see.

### Tasks

| # | Task | Owner | Priority |
|---|------|-------|----------|
| 5.1 | Point Flutter `.env` at Muhammad's backend URL | 🤝 Both | 🔴 |
| 5.2 | Full critical path test: `Trigger Demo` → pipeline runs → `incident_created` WS fires → Feed animates in 🔴 card | 🤝 Both | 🔴 |
| 5.3 | Critical detail test: tap 🔴 incident → `ReasoningSection` shows Gemini text → `BeforeAfterSection` + `ActionsTimeline` populated | 🤝 Both | 🔴 |
| 5.4 | Medium path test: force a `medium` severity incident (adjust mock data) → Feed shows 🟡 card → tap Approve → spinner → WS `incident_actioned` → Actions section populates | 🤝 Both | 🔴 |
| 5.5 | Map test: trigger → pins appear at correct lat/lng → blocked route turns red | 🤝 Both | 🔴 |
| 5.6 | Reset cycle test: `Reset` → all data clears → `GET /incidents` returns empty → Flutter feed clears → `Trigger Demo` runs again cleanly | 🤝 Both | 🔴 |
| 5.7 | Contract audit: verify all JSON field names match between FastAPI response models and Flutter `fromJson` deserializers | 🤝 Both | 🔴 |
| 5.8 | WS reconnect test: kill backend, restart, verify Flutter reconnects within 3s and next event is received | 🤝 Both | 🟡 |
| 5.9 | Low severity smoke test: verify `feed_only` incident appears in feed with grey badge and no Approve button | 👥 Affan | 🟡 |

### Known Risk Points
- **`incident_id` vs `incidentId`**: FastAPI returns snake_case, Flutter expects camelCase via `json_serializable`. Confirm `@JsonKey(name: 'incident_id')` annotations are present on all WsEvent fields.
- **`stateSnapshot` timing**: `BeforeAfterSection` renders after `incident_actioned` event triggers re-fetch. Verify the provider re-fetch completes before the section tries to render (use `AsyncValue.when` loading state).
- **Map annotation manager count**: Confirm only one `PointAnnotationManager` is created for the life of the map, not one per incident.

---

## Phase 6 — Gemini Integration & Stub Recording
**Timeline:** Day 4 (May 19) | **Owner:** 👤 Muhammad | **Priority:** 🔴

Record authentic Gemini outputs once. Switch to stub replay for all demo runs. This gives compelling AI reasoning text with zero API latency or dependency risk on stage.

### Tasks

| # | Task | Priority | Notes |
|---|------|----------|-------|
| 6.1 | Set `GEMINI_ENABLED=true`, configure `GEMINI_API_KEY` in `.env` | 🔴 | |
| 6.2 | Run full pipeline once against cloud backend with live Gemini | 🔴 | Use `POST /demo/trigger` on the deployed Cloud Run instance |
| 6.3 | Capture Sentinel + Analyst outputs — verify schema compliance (all required fields present, confidence in range, reasoning ≥ 2 sentences, zone names correct) | 🔴 | If output is schema-invalid, fix the system prompt and re-run before recording |
| 6.4 | Run `record_stubs.py --scenario karachi` — saves to `stubs/sentinel_karachi_flooding.json` + `stubs/analyst_karachi_flooding.json` | 🔴 | |
| 6.5 | Set `GEMINI_ENABLED=false`, re-run pipeline — verify stub replay produces identical DB state as live run | 🔴 | Confidence score, zone names, reasoning text must match. Commander must run correctly on stub Analyst output |
| 6.6 | Verify Commander is unaffected by stub mode (it has no LLM dependency — this is a sanity check) | 🟡 | |

### Definition of Done
- `GEMINI_ENABLED=false` pipeline run completes in under 5 seconds
- Reasoning text in `incidents.reasoning` is authentic Gemini prose (not a placeholder)
- No Gemini API calls made during demo mode

---

## Phase 7 — Cloud Deployment
**Timeline:** Days 4–5 (May 19–20) | **Owner:** 👤 Muhammad | **Priority:** 🔴

Deploy to Google Cloud. Demo runs on cloud infrastructure, not localhost. Protects against "works on my machine" failures.

### Tasks

| # | Task | Priority | Notes |
|---|------|----------|-------|
| 7.1 | Provision Cloud SQL (PostgreSQL) instance — apply migrations + seed Karachi data | 🔴 | Use the same `alembic upgrade head` + `python -m ciro.db.seed` commands as local |
| 7.2 | Write `Dockerfile` for FastAPI + `.dockerignore` | 🔴 | Multi-stage build. Copy `agents/`, `api/`, `db/`, `mock_data/`, `stubs/`, `.env` (do not commit `.env` — inject via Cloud Run env vars) |
| 7.3 | Deploy FastAPI to Cloud Run — set all env vars (`DATABASE_URL`, `API_KEY`, `ENV=production`, `GEMINI_ENABLED=false`, GCP project/region) | 🔴 | Use `--allow-unauthenticated` so Flutter can reach GET endpoints without Cloud IAM |
| 7.4 | Write `deploy_agents.py` — registers `ciro_pipeline` + `commander_agent` to Vertex AI Agent Engine | 🔴 | Use `reasoning_engines.ReasoningEngine.create()`. Store returned resource names in `.env` as `AGENT_ENGINE_PIPELINE_ID` + `AGENT_ENGINE_COMMANDER_ID` |
| 7.5 | Update Flutter `.env` — `API_BASE_URL` + `WS_URL` → Cloud Run URL | 🔴 | WSS (secure WebSocket) required. Cloud Run supports WebSocket upgrades natively |
| 7.6 | Production smoke test — `POST /demo/trigger` on Cloud Run → full pipeline → Flutter on device shows critical incident | 🔴 | Run from a real device on a cellular connection (not Wi-Fi) to simulate stage conditions |
| 7.7 | Production reset → trigger cycle × 3 — verify clean state on every reset | 🔴 | |

### Definition of Done
- Cloud Run URL is reachable from a real device
- Full pipeline runs on Agent Engine (not local runner)
- Flutter APK (or running emulator) connects to Cloud Run WebSocket and receives live events

---

## Phase 8 — Demo Polish & Hardening
**Timeline:** Day 5 (May 20) | **Owner:** 🤝 Both | **Priority:** 🟡 / 🟢

Cut freely from this phase if earlier phases are behind. The demo works without any of these — they make it impressive.

### Muhammad

| # | Task | Priority | Notes |
|---|------|----------|-------|
| 8.1 | Record fallback demo video — full trigger cycle on working cloud deployment | 🔴 | Stage Wi-Fi failure mitigation. Non-negotiable. Record before any last-minute changes |
| 8.2 | Verify stub pipeline runs in <5s end-to-end | 🟡 | Judges watching a spinner for 20s is a demo killer |
| 8.3 | Prepare manual trigger script — one command triggers full demo cycle without touching Flutter | 🟡 | Useful if Flutter crashes on stage |

### Affan

| # | Task | Priority | Notes |
|---|------|----------|-------|
| 8.4 | Critical badge pulsing animation — `AnimationController` repeat on red `StatusBadge` | 🟡 | High visual impact for judges |
| 8.5 | Map flood zone polygon — Gulshan-e-Iqbal + Nazimabad highlighted in semi-transparent red | 🟡 | Uses GeoJSON polygon from seed data |
| 8.6 | Tap-pin mini card — bottom sheet on pin tap with status badge + Approve shortcut | 🟢 | |
| 8.7 | Loading skeleton screens on all 4 screens | 🟡 | Prevents "blank screen then snap" during pipeline run |
| 8.8 | Confidence bar visual — animated fill, colour-coded by severity | 🟢 | |

### Both

| # | Task | Priority | Notes |
|---|------|----------|-------|
| 8.9 | End-to-end demo rehearsal × 2 — full cycle on stage device, timed | 🔴 | Target: < 90 seconds from Trigger tap to Actions timeline visible |
| 8.10 | `README.md` — setup steps, demo instructions, architecture diagram reference | 🟡 | Judges may review the repo |

---

## Dependency Graph

```
Phase 0 (Foundation)
    │
    ├──► Phase 1 (Agents) ──► Phase 6 (Gemini Stubs)
    │         │                        │
    │         ▼                        ▼
    │    Phase 2 (API) ─────────► Phase 7 (Cloud Deploy)
    │                                  │
    ├──► Phase 3 (Flutter Foundation)  │
    │         │                        │
    │         ▼                        ▼
    │    Phase 4 (Screens)        Phase 8 (Polish)
    │         │                        ▲
    └─────────┴──► Phase 5 (Integration) ─┘
```

---

## Risk Register

| Risk | Likelihood | Impact | Owner | Mitigation |
|------|-----------|--------|-------|------------|
| Gemini output fails Pydantic schema validation | Medium | High | Muhammad | Default to `severity=low` on parse failure. Test schema compliance before recording stubs |
| Vertex AI Agent Engine latency >10s on stage | High | High | Muhammad | `GEMINI_ENABLED=false` + stub replay. Never rely on live Gemini for the demo |
| Stage Wi-Fi drops during live demo | High | Fatal | Both | Record fallback video (Phase 8.1). Cache last known state in Flutter |
| Flutter WS drops silently after screen lock | Medium | High | Affan | `AppLifecycleObserver` reconnect (Phase 3.4, 4.11) |
| Mapbox annotation manager limit hit | Low | Medium | Affan | Single `PointAnnotationManager` for all pins — do not create per-incident |
| API/Flutter JSON contract mismatch discovered late | Medium | High | Both | Run contract audit in Phase 5.7 before Day 4 |
| Cloud SQL migration fails on production schema | Low | High | Muhammad | Test `alembic upgrade head` on a clean local DB before applying to Cloud SQL |
| Demo reset leaves orphaned DB rows (FK violation) | Low | High | Muhammad | FK-safe deletion order in `demo/reset`: routes → actions → tickets → incidents → signals |

---

## MoSCoW Summary

### Must Have (Demo fails without these)
- Full Sentinel → Analyst → Commander pipeline with mock Karachi flooding data
- `POST /demo/trigger` + `POST /demo/reset` working on Cloud Run
- Flutter Home Screen with CityCard status + Trigger/Reset buttons
- Incident Feed with real-time WS card animation
- Incident Detail with AI Reasoning Trace + BeforeAfter diff
- WebSocket live push for all 4 event types
- Approve flow: `pending_approval` → tap → Commander runs → UI updates
- Gemini stub recording (zero API dependency on stage)
- Fallback demo video

### Should Have (Expected but survivable without)
- Map screen with incident pins + blocked route polylines
- `GET /signals` debug endpoint
- Skeleton loaders and error banners
- App lifecycle WS reconnect
- Critical badge pulsing animation

### Could Have (Cut freely if behind)
- Map flood zone polygon highlights
- Tap-pin mini card with Approve shortcut
- Animated confidence bar
- `GET /map/routes` polyline rendering

### Won't Have (Explicitly deferred)
- User authentication
- Lahore / Islamabad support
- Heatwave or Road Blockage demo scenarios
- Live API integrations (OpenWeatherMap, X/Twitter, Google Maps)
- Scheduled cron pipeline (manual trigger only for demo)
- Settings screen
- Push notifications (OS-level)
