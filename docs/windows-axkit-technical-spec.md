# Windows AXKit-Style Library for Talon (Technical Spec)

## 1) Purpose

Define a Windows-first accessibility library for Talon that is:

- Fast enough for interactive use (labels and actions feel immediate).
- Reliable enough for daily operation (predictable success/failure behavior).
- Extensible as a platform (other Talon projects can add adapters and features without forking core behavior).

This document proposes a project codename: **WinAXKit**.

---

## 2) Product Goals and Non-Goals

### Goals

1. **Focused-window-first performance**
   - Prefer active-window subtree traversal over desktop-wide scans.
   - Keep common action latency under a target budget on normal hardware.
2. **Deterministic reliability**
   - Every request resolves to: success, safe fallback, or explicit structured failure.
   - No silent no-ops.
3. **Library-first architecture**
   - Stable public APIs for query, targeting, labeling, action dispatch, and telemetry.
   - App-specific logic isolated in adapters/plugins.
4. **Observability by default**
   - Built-in metrics and trace events to diagnose misses and regressions.
5. **Thread-safe concurrency**
   - Use multiple threads where it improves responsiveness while preserving deterministic behavior.

### Non-Goals (initial phases)

1. Perfect automation coverage across all Windows apps.
2. Replacing Talon core label APIs globally in one step.
3. Deep non-Windows support in core modules.

---

## 3) Reliability Requirements ("Bulletproof" Definition)

The system is considered production-ready when the following are true:

1. **Bounded latency**
   - Common operations (`show_window_numbers`, `click_label`) complete or fail clearly within timeout policy.
2. **Structured outcomes**
   - Calls return `Success`, `FallbackUsed`, or `Failure` with machine-readable error codes.
3. **No ambiguous state**
   - Overlay/session state is explicit and recoverable after focus changes, stale elements, or provider errors.
4. **Graceful degradation**
   - If UIA is insufficient in a target app, configured fallback chains are attempted.
5. **Idempotent cancellation**
   - Duplicate cancel/hide calls do not corrupt overlay state.
6. **Crash containment**
   - Adapter failures cannot crash the host process or poison subsequent sessions.

---

## 4) Architecture Overview

```
Talon Commands / Actions
        |
        v
API Facade (winaxkit.api)
        |
        +--> Session Manager
        |       +--> Overlay Lifecycle
        |       +--> Focus Tracking
        |
        +--> Query Planner
        |       +--> Scope Resolver (active window/app/desktop)
        |       +--> Filter Compiler (control/content/pattern constraints)
        |
        +--> UIA Engine
        |       +--> Snapshot Builder (cache requests)
        |       +--> Event Subscriptions (focus/property/structure)
        |       +--> Action Dispatcher (Invoke/Selection/Value/...)
        |
        +--> Target Resolver
        |       +--> Ranking
        |       +--> Deduplication
        |
        +--> Fallback Orchestrator
        |       +--> Keyboard fallback
        |       +--> OCR/grid fallback
        |
        +--> Adapter Registry
        |       +--> App adapters (Chromium/Electron/Office/JetBrains/...)
        |
        +--> Telemetry & Diagnostics
                +--> Metrics
                +--> Trace logs
                +--> Debug snapshots
```

---

## 5) Module Layout

Recommended Python package layout:

```
winaxkit/
  api/
    public.py
    types.py
    errors.py
  core/
    session.py
    focus.py
    scheduler.py
    cancellation.py
  uia/
    client.py
    cache.py
    events.py
    tree.py
    patterns.py
  query/
    planner.py
    scope.py
    filters.py
    ranking.py
  labels/
    model.py
    allocator.py
    presenter.py
  actions/
    dispatcher.py
    strategies.py
  fallback/
    orchestrator.py
    keyboard.py
    grid.py
  adapters/
    registry.py
    base.py
    chromium.py
    electron.py
    office.py
    jetbrains.py
  telemetry/
    metrics.py
    trace.py
    dump.py
  config/
    schema.py
    defaults.py
```

---

## 6) Public API (Library Contract)

All APIs should be callable by other Talon projects without requiring internal imports.

### Core Types

```python
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterable, Protocol


class OutcomeKind(str, Enum):
    SUCCESS = "success"
    FALLBACK_USED = "fallback_used"
    FAILURE = "failure"


class ErrorCode(str, Enum):
    TIMEOUT = "timeout"
    STALE_ELEMENT = "stale_element"
    PATTERN_UNSUPPORTED = "pattern_unsupported"
    PROVIDER_MISSING = "provider_missing"
    WINDOW_CHANGED = "window_changed"
    ACCESS_DENIED = "access_denied"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ActionOutcome:
    kind: OutcomeKind
    code: ErrorCode | None
    message: str
    elapsed_ms: int
    used_fallback: str | None = None
    data: dict[str, Any] | None = None


@dataclass(frozen=True)
class QueryScope:
    mode: str  # "active_window" | "active_app" | "desktop"
    window_id: int | None = None
    app_name: str | None = None


@dataclass(frozen=True)
class QuerySpec:
    selector: str
    scope: QueryScope
    include_offscreen: bool = False
    include_disabled: bool = False
    max_results: int = 500
```

### Primary Facade

```python
class WinAXKitAPI(Protocol):
    def show_window_numbers(self, spec: QuerySpec | None = None) -> ActionOutcome: ...
    def show_window_names(self, spec: QuerySpec | None = None) -> ActionOutcome: ...
    def hide_labels(self) -> ActionOutcome: ...

    def click_label(self, label: str) -> ActionOutcome: ...
    def focus_label(self, label: str) -> ActionOutcome: ...
    def invoke_label(self, label: str) -> ActionOutcome: ...

    def query(self, spec: QuerySpec) -> list[dict[str, Any]]: ...
    def perform(self, target_id: str, action: str, **kwargs: Any) -> ActionOutcome: ...

    def warm_active_window_cache(self) -> ActionOutcome: ...
    def refresh_active_session(self) -> ActionOutcome: ...

    def register_adapter(self, adapter: "Adapter") -> None: ...
    def unregister_adapter(self, adapter_id: str) -> None: ...

    def subscribe_events(self, callback: Callable[[dict[str, Any]], None]) -> str: ...
    def unsubscribe_events(self, subscription_id: str) -> None: ...
```

### Adapter API (Extension Contract)

```python
class Adapter(Protocol):
    adapter_id: str
    priority: int

    def matches(self, app_name: str, exe_path: str | None, window_title: str) -> bool: ...

    def pre_query(self, spec: QuerySpec) -> QuerySpec:
        return spec

    def post_query(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return nodes

    def choose_action(self, node: dict[str, Any], requested_action: str) -> str:
        return requested_action

    def on_failure(self, outcome: ActionOutcome, context: dict[str, Any]) -> ActionOutcome:
        return outcome
```

Adapter rules:

1. Adapters must not mutate global state outside provided hooks.
2. Adapters must be deterministic for equal inputs.
3. Adapters must fail closed (return unchanged input/outcome when uncertain).

---

## 7) Threading and Concurrency Model

### Design

Use a hybrid model:

1. **Main command thread**
   - Receives Talon command/action calls.
2. **UIA worker pool** (bounded)
   - Executes expensive query snapshots and pattern inspection.
3. **Event thread**
   - Receives UIA focus/property/structure events and enqueues incremental refresh jobs.
4. **Overlay/UI thread boundary**
   - Any overlay updates are marshaled to the required thread/context.

### Rules

1. **Single writer for session state**
   - One scheduler/actor owns mutable session state; workers return immutable results.
2. **Cancellation tokens everywhere**
   - Focus changes and new commands cancel stale jobs immediately.
3. **Bounded queues**
   - Prevent unbounded memory growth during event storms.
4. **Coalescing**
   - Collapse rapid duplicate refresh triggers into one refresh operation.
5. **Deadline propagation**
   - Each command carries a timeout budget consumed by each stage.

### Suggested defaults

- Worker threads: `min(4, max(2, cpu_count // 2))`
- Command timeout default: `500 ms`
- Background refresh timeout: `1500 ms`
- Event debounce/coalesce window: `30-75 ms`

---

## 8) Query and Labeling Strategy

### Query phases

1. Resolve scope to active window root.
2. Build cache request for only needed properties/patterns.
3. Traverse control/content view (not raw by default).
4. Apply adapter filters.
5. Rank and deduplicate targets.
6. Render labels from stable ordering key.

### Stable ranking keys (in order)

1. Visible and enabled first.
2. Interactive patterns (`Invoke`, `SelectionItem`, `Value`, `Toggle`).
3. On-screen area overlap with active window.
4. Spatial ordering (top-to-bottom, then left-to-right).
5. App-specific adapter boosts.

---

## 9) Fallback Orchestration

Fallback chain is configurable per command/app.

Example chain for "activate target":

1. UIA `Invoke` or pattern-native action.
2. UIA focus + keyboard confirm (`Space`/`Enter`) when adapter allows.
3. Mouse click at cached center point.
4. OCR/grid fallback when enabled.

Fallback execution requirements:

- Stop at first verified success.
- Record fallback stage in telemetry.
- If all fail, return structured failure with attempted stages.

---

## 10) Error Model and Diagnostics

Each failure emits:

1. `error_code` (stable enum)
2. `stage` (`query`, `rank`, `dispatch`, `fallback`)
3. `scope_info` (window/app identity)
4. `latency_breakdown_ms`
5. `adapter_id` (if any)

Diagnostics commands for users/contributors:

- `win ax status`
- `win ax last failure`
- `win ax dump session`
- `win ax benchmark active window`

---

## 11) Configuration Surface

Config must be safe to override per app and per workspace.

Suggested settings:

- `winaxkit.enabled`
- `winaxkit.default_scope` (`active_window` default)
- `winaxkit.timeouts.command_ms`
- `winaxkit.timeouts.refresh_ms`
- `winaxkit.threads.worker_count`
- `winaxkit.events.coalesce_ms`
- `winaxkit.fallback.enable_ocr`
- `winaxkit.fallback.enable_mouse`
- `winaxkit.adapters.disabled`
- `winaxkit.telemetry.level` (`off`, `error`, `info`, `debug`)

---

## 12) Security and Safety

1. Never execute adapter-provided arbitrary code outside declared hooks.
2. Redact sensitive element text in logs by policy.
3. Ensure injected input paths (keyboard/mouse) are explicit and user-visible in outcomes.
4. Require explicit opt-in for high-risk fallback behaviors.

---

## 13) Testing Strategy

### Test layers

1. **Unit tests**
   - Ranking, deduplication, timeout accounting, error mapping.
2. **Contract tests**
   - Adapter API compliance suite.
3. **Integration tests (mock UIA)**
   - Event storms, stale elements, focus churn, cancellation races.
4. **Live app matrix smoke tests**
   - VS Code, Notepad, Explorer, Office app, Chromium browser, one Electron app.

### Reliability gates

Release candidate requires meeting baseline SLOs from representative workloads:

- P50 `show_window_numbers` latency
- P95 `show_window_numbers` latency
- Action success rate
- Fallback success rate
- Unclassified failure rate

---

## 14) Delivery Plan

### Phase 0: Spike (2-3 weeks)

- Implement focused-window snapshot + labels prototype.
- Implement basic `show_window_numbers`, `click_label`.
- Add telemetry stubs and timing hooks.

Exit criteria:

- Works on at least 3 core apps.
- Emits structured outcomes and timings.

### Phase 1: MVP Library (4-7 weeks)

- Public API facade + package boundaries.
- Session manager, scheduler, cancellation tokens.
- Initial adapter registry + 2 adapters (Chromium/Electron).
- Basic fallback chain and diagnostics commands.

Exit criteria:

- Other Talon project can import and call public APIs only.
- Deterministic behavior across focus changes.

### Phase 2: Reliability Hardening (6-10 weeks)

- Event-driven refresh and cache invalidation.
- Stress testing and race-condition fixes.
- Expanded adapter set (Office/JetBrains/Explorer).
- SLO dashboards and failure triage tooling.

Exit criteria:

- Meets target SLOs on app matrix.
- No silent failures in core flows.

### Phase 3: Ecosystem Adoption (ongoing)

- Stable semver release process.
- Adapter SDK docs + template repo.
- Migration guide for existing Talon packages.

---

## 15) Minimal API Examples

### Example: command integration

```python
from winaxkit.api.public import api
from winaxkit.api.types import QueryScope, QuerySpec


def show_numbers_active_window() -> None:
    spec = QuerySpec(
        selector='[is_content_element=1][rect]:is([patterns*="Invoke"], [patterns*="Toggle"], [patterns*="SelectionItem"])',
        scope=QueryScope(mode="active_window"),
        max_results=300,
    )
    outcome = api.show_window_numbers(spec)
    if outcome.kind == "failure":
        # Map to user notification in Talon action layer
        pass
```

### Example: extension adapter

```python
from winaxkit.api.public import api


class MyEditorAdapter:
    adapter_id = "myeditor"
    priority = 50

    def matches(self, app_name, exe_path, window_title):
        return "MyEditor" in app_name

    def post_query(self, nodes):
        return [n for n in nodes if n.get("control_type") != "Pane"]


api.register_adapter(MyEditorAdapter())
```

---

## 16) Open Decisions

1. Runtime target for UIA backend (pure Python binding vs companion native helper).
2. Telemetry storage format and retention policy.
3. Whether OCR/grid fallback is bundled or plugin-only.
4. Versioning/compatibility policy with Talon core changes.

---

## 17) Summary

An AXKit-style Windows library for Talon is feasible if built as a scoped, event-driven, adapter-based platform with strict outcome contracts and thread-safe scheduling.
The shortest path to real user value is to ship focused-window labeling/actions first, then harden reliability via observability, adapter coverage, and deterministic fallbacks.
