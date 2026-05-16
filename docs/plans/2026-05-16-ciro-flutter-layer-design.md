# CIRO — Flutter Layer Design
**Date:** 2026-05-16
**Status:** Validated
**Relates to:** 2026-05-16-ciro-architecture-design.md

---

## Overview

Flutter mobile app — a real-time window into the autonomous CIRO system.

**Tech choices (validated):**
- State management: Riverpod (StreamProvider for WS, AsyncNotifier for REST)
- Map: Mapbox (`mapbox_maps_flutter`)
- Navigation: `go_router` with ShellRoute + bottom nav
- HTTP: Dio (split public/protected instances)
- WebSocket: `web_socket_channel` with auto-reconnect

**4 screens:** Home → Incident Feed → Incident Detail → Map Panel

**3 incident states:**
| Status | Badge | Colour |
|---|---|---|
| `auto_escalated` | CRITICAL | 🔴 Red |
| `pending_approval` | AWAITING APPROVAL | 🟡 Amber |
| `feed_only` | MONITORING | ⚪ Grey |

---

## 1. Project Structure

```
mobile/
├── lib/
│   ├── main.dart
│   ├── config/
│   │   └── app_config.dart          # base URL, Mapbox token (from .env)
│   ├── models/
│   │   ├── incident.dart            # Incident, IncidentDetail, IncidentPin
│   │   ├── city_state.dart          # CityCard
│   │   ├── signal.dart
│   │   └── ws_event.dart            # WsEvent (freezed)
│   ├── services/
│   │   ├── api_service.dart         # Dio — public + protected instances
│   │   └── ws_service.dart          # WebSocket + auto-reconnect
│   ├── providers/
│   │   ├── city_provider.dart
│   │   ├── incident_provider.dart
│   │   ├── map_provider.dart
│   │   └── ws_provider.dart
│   ├── screens/
│   │   ├── home/
│   │   │   └── home_screen.dart
│   │   ├── feed/
│   │   │   ├── feed_screen.dart
│   │   │   └── incident_card.dart
│   │   ├── detail/
│   │   │   ├── detail_screen.dart
│   │   │   ├── reasoning_section.dart
│   │   │   ├── before_after_section.dart
│   │   │   ├── actions_timeline.dart
│   │   │   └── approve_button.dart
│   │   └── map/
│   │       └── map_screen.dart
│   ├── widgets/
│   │   ├── status_badge.dart
│   │   ├── severity_chip.dart
│   │   └── confidence_bar.dart
│   └── router.dart
├── pubspec.yaml
└── .env                             # never committed
```

---

## 2. Dependencies

**`pubspec.yaml`:**
```yaml
dependencies:
  flutter_riverpod: ^2.5.1
  riverpod_annotation: ^2.3.5
  go_router: ^14.0.0
  dio: ^5.4.3
  web_socket_channel: ^2.4.0
  mapbox_maps_flutter: ^2.3.0
  flutter_dotenv: ^5.1.0
  freezed_annotation: ^2.4.1
  json_annotation: ^4.9.0

dev_dependencies:
  build_runner: ^2.4.9
  riverpod_generator: ^2.4.0
  freezed: ^2.4.7
  json_serializable: ^6.7.1
```

**`.env`:**
```env
API_BASE_URL=https://your-cloud-run-url
WS_URL=wss://your-cloud-run-url/ws/feed
API_KEY=your-static-key
MAPBOX_TOKEN=pk.your-mapbox-token
```

---

## 3. Service Layer

### `services/api_service.dart`

Two Dio instances — public (GET) and protected (POST). A misconfigured API key
only breaks write endpoints, never reads. Feed and map remain visible.

```dart
class ApiService {
  late final Dio _publicDio;
  late final Dio _protectedDio;

  ApiService() {
    final baseOptions = BaseOptions(
      baseUrl: dotenv.env['API_BASE_URL']!,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 15),
      headers: {'Content-Type': 'application/json'},
    );

    _publicDio = Dio(baseOptions);
    _publicDio.interceptors.add(LogInterceptor(responseBody: true));

    _protectedDio = Dio(baseOptions.copyWith(
      headers: {
        'X-API-Key': dotenv.env['API_KEY']!,
        'Content-Type': 'application/json',
      },
    ));
    _protectedDio.interceptors.add(LogInterceptor(responseBody: true));
  }

  // ── Public GET endpoints ──────────────────────────────────
  Future<List<CityCard>> getCities() async {
    final res = await _publicDio.get('/api/v1/cities');
    return (res.data as List).map((e) => CityCard.fromJson(e)).toList();
  }

  Future<List<Incident>> getIncidents({String? severity, String? status}) async {
    final res = await _publicDio.get('/api/v1/incidents', queryParameters: {
      if (severity != null) 'severity': severity,
      if (status != null)   'status': status,
    });
    return (res.data as List).map((e) => Incident.fromJson(e)).toList();
  }

  Future<IncidentDetail> getIncident(String id) async {
    final res = await _publicDio.get('/api/v1/incidents/$id');
    return IncidentDetail.fromJson(res.data);
  }

  Future<List<IncidentPin>> getMapPins() async {
    final res = await _publicDio.get('/api/v1/map/pins');
    return (res.data as List).map((e) => IncidentPin.fromJson(e)).toList();
  }

  Future<Map<String, dynamic>> getMapRoutes(String city) async {
    final res = await _publicDio.get('/api/v1/map/routes/$city');
    return res.data;
  }

  // ── Protected POST endpoints ──────────────────────────────
  Future<void> approveIncident(String id) async {
    await _protectedDio.post('/api/v1/incidents/$id/approve',
      data: {'approved_by': 'controller'});
  }

  Future<void> triggerDemo(String scenario) async {
    await _protectedDio.post('/api/v1/demo/trigger',
      data: {'scenario': scenario});
  }

  Future<void> resetDemo() async {
    await _protectedDio.post('/api/v1/demo/reset');
  }
}
```

### `services/ws_service.dart`

Auto-reconnect on error/close. Ping every 20s to keep FastAPI alive.
Broadcast stream — multiple providers can listen simultaneously.

```dart
class WsService {
  WebSocketChannel? _channel;
  final _controller = StreamController<WsEvent>.broadcast();
  Timer? _pingTimer;
  Timer? _reconnectTimer;
  bool _disposed = false;

  Stream<WsEvent> get events => _controller.stream;

  void connect(String wsUrl) {
    _channel = WebSocketChannel.connect(Uri.parse(wsUrl));
    _channel!.stream.listen(
      (raw) => _controller.add(WsEvent.fromJson(jsonDecode(raw as String))),
      onError: (_) => _scheduleReconnect(wsUrl),
      onDone:  () => _scheduleReconnect(wsUrl),
    );
    _pingTimer = Timer.periodic(const Duration(seconds: 20), (_) {
      _channel?.sink.add('ping');
    });
  }

  void _scheduleReconnect(String wsUrl) {
    if (_disposed) return;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 3), () {
      if (!_disposed) connect(wsUrl);
    });
  }

  void dispose() {
    _disposed = true;
    _pingTimer?.cancel();
    _reconnectTimer?.cancel();
    _channel?.sink.close();
    _controller.close();
  }
}
```

### `models/ws_event.dart`

```dart
@freezed
class WsEvent with _$WsEvent {
  // Incident events (from DB trigger)
  const factory WsEvent.incidentEvent({
    required String event,        // incident_created | incident_approved
                                  // | incident_actioned | incident_updated
    required String incidentId,
    required String city,
    required String severity,
    required String status,
  }) = IncidentWsEvent;

  // Pipeline status events (from AgentClient)
  const factory WsEvent.pipelineEvent({
    required String event,        // pipeline_started | pipeline_complete | pipeline_error
    required String stage,        // 'sentinel' | 'commander' | 'pipeline'
    String? message,              // error message — only on pipeline_error
  }) = PipelineWsEvent;

  factory WsEvent.fromJson(Map<String, dynamic> json) {
    final event = json['event'] as String;
    if (event.startsWith('pipeline_')) {
      return WsEvent.pipelineEvent(
        event: event,
        stage: json['stage'] as String,
        message: json['message'] as String?,
      );
    }
    return WsEvent.incidentEvent(
      event: event,
      incidentId: json['incident_id'] as String,
      city: json['city'] as String,
      severity: json['severity'] as String,
      status: json['status'] as String,
    );
  }
}
```

---

## 4. Riverpod Providers

### WS Event → Provider Invalidation Map

| Event | Cities | Incidents | IncidentDetail(id) | MapPins |
|---|---|---|---|---|
| `incident_created` | ✅ | ✅ | — | ✅ |
| `incident_approved` | ✅ | — | ✅ (matching id) | — |
| `incident_actioned` | ✅ | ✅ | ✅ (matching id) | ✅ |
| `incident_updated` | — | ✅ | ✅ (matching id) | — |

### Providers

```dart
// ── Singleton services ────────────────────────────────────

@riverpod
ApiService apiService(ApiServiceRef ref) => ApiService();

@riverpod
WsService wsService(WsServiceRef ref) {
  final service = WsService();
  service.connect(dotenv.env['WS_URL']!);
  ref.onDispose(service.dispose);
  return service;
}

@riverpod
Stream<WsEvent> wsEvents(WsEventsRef ref) {
  return ref.watch(wsServiceProvider).events;
}

// ── City state ────────────────────────────────────────────

@riverpod
class Cities extends _$Cities {
  @override
  Future<List<CityCard>> build() async {
    ref.listen(wsEventsProvider, (_, next) {
      next.whenData((event) {
        if ({'incident_created', 'incident_approved',
             'incident_actioned'}.contains(event.event)) {
          ref.invalidateSelf();
        }
      });
    });
    return ref.read(apiServiceProvider).getCities();
  }
}

// ── Incident feed ─────────────────────────────────────────

@riverpod
class Incidents extends _$Incidents {
  @override
  Future<List<Incident>> build({String? severity, String? status}) async {
    ref.listen(wsEventsProvider, (_, next) {
      next.whenData((event) {
        // incident_approved excluded — only affects detail view, not feed list
        if ({'incident_created', 'incident_updated',
             'incident_actioned'}.contains(event.event)) {
          ref.invalidateSelf();
        }
      });
    });
    return ref.read(apiServiceProvider).getIncidents(
      severity: severity, status: status);
  }
}

// ── Incident detail — family provider ────────────────────

@riverpod
class IncidentDetail extends _$IncidentDetail {
  @override
  Future<IncidentDetailModel> build(String id) async {
    ref.listen(wsEventsProvider, (_, next) {
      next.whenData((event) {
        if (event.incidentId == id &&
            {'incident_approved', 'incident_actioned',
             'incident_updated'}.contains(event.event)) {
          ref.invalidateSelf();
        }
      });
    });
    return ref.read(apiServiceProvider).getIncident(id);
  }
}

// ── Approve — family provider (scoped to incidentId) ─────

@riverpod
class ApproveIncident extends _$ApproveIncident {
  @override
  AsyncValue<void> build(String incidentId) => const AsyncData(null);

  Future<void> approve(String incidentId) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() =>
      ref.read(apiServiceProvider).approveIncident(incidentId));
    // WS event drives UI update — no manual invalidation needed
  }
}

// ── Map ───────────────────────────────────────────────────

@riverpod
Future<List<IncidentPin>> mapPins(MapPinsRef ref) async {
  ref.listen(wsEventsProvider, (_, next) {
    next.whenData((event) {
      if ({'incident_created', 'incident_actioned'}.contains(event.event)) {
        ref.invalidateSelf();
      }
    });
  });
  return ref.read(apiServiceProvider).getMapPins();
}

@riverpod
Future<Map<String, dynamic>> mapRoutes(MapRoutesRef ref, String city) {
  return ref.read(apiServiceProvider).getMapRoutes(city);
  // Not WS-reactive — Map screen polls every 30s
}

// ── Demo controls ─────────────────────────────────────────

@riverpod
class DemoControls extends _$DemoControls {
  @override
  AsyncValue<void> build() => const AsyncData(null);

  Future<void> trigger(String scenario) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() =>
      ref.read(apiServiceProvider).triggerDemo(scenario));
  }

  Future<void> reset() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() =>
      ref.read(apiServiceProvider).resetDemo());
    if (state is AsyncData) {
      ref.invalidate(citiesProvider);
      ref.invalidate(incidentsProvider);
      ref.invalidate(mapPinsProvider);
    }
  }
}
```

---

## 5. Screen Implementations

### Home Screen

```dart
class HomeScreen extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cities = ref.watch(citiesProvider);
    return Scaffold(
      body: cities.when(
        loading: () => const CityCardSkeleton(),
        error:   (e, _) => ErrorBanner(message: e.toString()),
        data: (cards) => Column(children: [
          const CiroHeader(),
          ...cards.map((c) => CityCard(card: c)),
          const SizedBox(height: 16),
          _DemoControls(),
        ]),
      ),
    );
  }
}

class _DemoControls extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final demo = ref.watch(demoControlsProvider);
    final hasIncidents = ref.watch(incidentsProvider()).valueOrNull?.isNotEmpty ?? false;

    // React to pipeline status WS events
    ref.listen(wsEventsProvider, (_, next) {
      next.whenData((event) {
        if (event is PipelineWsEvent) {
          switch (event.event) {
            case 'pipeline_error':
              ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                backgroundColor: Colors.red.shade800,
                content: Text('Pipeline failed: ${event.message ?? "Unknown error"}'),
                duration: const Duration(seconds: 8),
              ));
            case 'pipeline_complete':
              ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                content: Text('✓ Pipeline complete — check the feed'),
                duration: Duration(seconds: 3),
              ));
          }
        }
      });
    });

    return Row(children: [
      ElevatedButton(
        onPressed: (demo.isLoading || hasIncidents) ? null :
          () => ref.read(demoControlsProvider.notifier).trigger('karachi'),
        child: demo.isLoading
          ? const Row(children: [
              SizedBox(width: 14, height: 14,
                child: CircularProgressIndicator(strokeWidth: 2)),
              SizedBox(width: 8),
              Text('Running...')
            ])
          : const Text('▶ Trigger Demo'),
      ),
      TextButton(
        onPressed: () => ref.read(demoControlsProvider.notifier).reset(),
        child: const Text('Reset'),
      ),
    ]);
  }
}
```

### Incident Feed Screen

```dart
class FeedScreen extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final incidents = ref.watch(incidentsProvider());
    return Scaffold(
      appBar: AppBar(
        title: const Text('Incident Feed'),
        bottom: const _FilterBar(),
      ),
      body: incidents.when(
        loading: () => const IncidentListSkeleton(),
        error:   (e, _) => ErrorBanner(message: e.toString()),
        data: (list) => ListView.builder(
          itemCount: list.length,
          itemBuilder: (ctx, i) => IncidentCard(
            incident: list[i],
            onTap: () => context.push('/feed/${list[i].id}'),
          ),
        ),
      ),
    );
  }
}

class IncidentCard extends StatelessWidget {
  final Incident incident;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: CrisisTypeIcon(type: incident.crisisType),
      title:   Text(incident.crisisType.label),
      subtitle: Text(incident.affectedZones.join(', ')),
      trailing: Column(children: [
        StatusBadge(status: incident.status),
        ConfidenceBar(value: incident.confidence),
      ]),
      onTap: onTap,
    );
  }
}
```

### Incident Detail Screen

Five sections — reasoning, evidence, before/after, actions, approve button.
Sections 3 and 4 only render after Commander acts (`stateSnapshot != null`).

```dart
class DetailScreen extends ConsumerWidget {
  final String incidentId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(incidentDetailProvider(incidentId));
    return Scaffold(
      appBar: AppBar(
        title: const Text('Incident Detail'),
        actions: [StatusBadge(status: detail.valueOrNull?.status ?? '')],
      ),
      body: detail.when(
        loading: () => const DetailSkeleton(),
        error:   (e, _) => ErrorBanner(message: e.toString()),
        data:    (d) => SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(children: [
            DetailHeader(
              crisisType: d.crisisType, severity: d.severity,
              city: d.city, confidence: d.confidence),
            const SizedBox(height: 24),
            ReasoningSection(reasoning: d.reasoning),
            const SizedBox(height: 16),
            EvidenceSection(evidence: d.evidenceSummary),
            const SizedBox(height: 16),
            if (d.stateSnapshot != null)
              BeforeAfterSection(snapshot: d.stateSnapshot!),
            const SizedBox(height: 16),
            if (d.actionsTaken.isNotEmpty)
              ActionsTimeline(actions: d.actionsTaken),
            const SizedBox(height: 24),
            if (d.status == 'pending_approval')
              ApproveButton(incidentId: d.id),
          ]),
        ),
      ),
    );
  }
}
```

### ApproveButton — family-scoped, no state bleed across incidents

```dart
class ApproveButton extends ConsumerWidget {
  final String incidentId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Family provider — each incidentId has isolated approve state
    final approveState = ref.watch(approveIncidentProvider(incidentId));

    return switch (approveState) {
      AsyncLoading() => FilledButton(
          onPressed: null,
          child: Row(children: [
            const SizedBox(width: 16, height: 16,
              child: CircularProgressIndicator(strokeWidth: 2)),
            const SizedBox(width: 8),
            const Text('Approving...'),
          ])),
      AsyncError(:final error) => Column(children: [
          FilledButton(
            onPressed: () => ref
              .read(approveIncidentProvider(incidentId).notifier)
              .approve(incidentId),
            child: const Text('Approve Response')),
          Text('Error: $error',
            style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ]),
      _ => FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor: const Color(0xFFF59E0B),
            minimumSize: const Size.fromHeight(52),
          ),
          onPressed: () => ref
            .read(approveIncidentProvider(incidentId).notifier)
            .approve(incidentId),
          child: const Text('✓  Approve Response',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        ),
    };
  }
}
```

### Map Screen — single annotation manager for all pins

```dart
class MapScreen extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final pins   = ref.watch(mapPinsProvider);
    final routes = ref.watch(mapRoutesProvider('karachi'));

    return MapWidget(
      key: const ValueKey('karachi_map'),
      onMapCreated: (controller) => _setupMap(controller, pins, routes),
      cameraOptions: CameraOptions(
        center: Point(coordinates: Position(67.0011, 24.8607)),
        zoom: 11.5,
      ),
    );
  }

  Future<void> _setupMap(
      MapboxMap map, AsyncValue pins, AsyncValue routes) async {
    pins.whenData((pinList) async {
      // One manager for all pins — Mapbox has a hard limit on manager count
      final mgr = await map.annotations.createPointAnnotationManager();
      for (final pin in pinList) {
        await mgr.create(PointAnnotationOptions(
          geometry: Point(coordinates: Position(pin.lng, pin.lat)),
          iconImage: _iconForStatus(pin.status),
          iconSize: 1.4,
        ));
      }
    });
    // Route polylines and flood zone polygons added similarly
  }

  String _iconForStatus(String status) => switch (status) {
    'auto_escalated'   => 'incident-critical',
    'pending_approval' => 'incident-pending',
    _                  => 'incident-monitoring',
  };
}
```

---

## 6. Navigation

### `router.dart`

```dart
final router = GoRouter(
  initialLocation: '/',
  routes: [
    ShellRoute(
      builder: (context, state, child) => AppShell(child: child),
      routes: [
        GoRoute(
          path: '/',
          builder: (context, state) => const HomeScreen(),
        ),
        GoRoute(
          path: '/feed',
          builder: (context, state) => const FeedScreen(),
          routes: [
            GoRoute(
              path: ':id',
              builder: (context, state) => DetailScreen(
                incidentId: state.pathParameters['id']!,
              ),
            ),
          ],
        ),
        GoRoute(
          path: '/map',
          builder: (context, state) => const MapScreen(),
        ),
      ],
    ),
  ],
);
```

### `AppShell` — bottom nav + WS snackbar listener

Snackbar listener lives here because `AppShell` is always mounted — context
is guaranteed. Avoids the null-crash risk of accessing context from the app root.

```dart
class AppShell extends ConsumerWidget {
  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // WS snackbar — safe context, AppShell always mounted
    ref.listen(wsEventsProvider, (_, next) {
      next.whenData((event) {
        if (event.event == 'incident_created') {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(
              '🚨 New ${event.severity.toUpperCase()} incident — ${event.city}'),
            action: SnackBarAction(
              label: 'View',
              onPressed: () => context.push('/feed/${event.incidentId}'),
            ),
            duration: const Duration(seconds: 6),
          ));
        }
      });
    });

    final location = GoRouterState.of(context).uri.path;
    return Scaffold(
      body: child,
      bottomNavigationBar: NavigationBar(
        selectedIndex: _indexFromPath(location),
        onDestinationSelected: (i) => _navigate(context, i),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home), label: 'Home'),
          NavigationDestination(
            icon: Icon(Icons.feed_outlined),
            selectedIcon: Icon(Icons.feed), label: 'Feed'),
          NavigationDestination(
            icon: Icon(Icons.map_outlined),
            selectedIcon: Icon(Icons.map), label: 'Map'),
        ],
      ),
    );
  }

  int _indexFromPath(String path) {
    if (path.startsWith('/feed')) return 1;
    if (path.startsWith('/map'))  return 2;
    return 0;
  }

  void _navigate(BuildContext context, int index) {
    switch (index) {
      case 0: context.go('/');
      case 1: context.go('/feed');
      case 2: context.go('/map');
    }
  }
}
```

### `main.dart`

```dart
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await dotenv.load(fileName: '.env');
  runApp(const ProviderScope(child: CiroApp()));
}

class CiroApp extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      routerConfig: router,
      title: 'CIRO',
      theme: _buildTheme(),
    );
  }
}
```

---

## 7. Demo Navigation Flow

```
Home: tap "▶ Trigger Demo"
        │
        ▼
Pipeline runs → critical incident written to DB
        │
        ▼
WS: incident_created → AppShell snackbar:
  "🚨 New CRITICAL incident — Karachi  [View]"
        │
        ├─ Tap [View] → context.push('/feed/{id}')
        │               DetailScreen: reasoning trace + evidence
        │               BeforeAfter + Actions Taken appear after Commander acts
        │
        └─ Stay on Feed
               New IncidentCard animates in at top
               🔴 CRITICAL badge

For medium incident (pending_approval):
  WS: incident_created → Feed shows 🟡 AWAITING APPROVAL card
  Tap card → DetailScreen → Approve button visible
  Tap Approve → loading spinner → WS: incident_actioned
  → Actions Taken section populates
  → BeforeAfter diff appears
  → badge updates to grey (actioned)
```
