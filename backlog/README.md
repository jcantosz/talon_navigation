# Navigation Backlogs and Accessibility Agent Handoff

This document is the index for navigation work and the handoff for current macOS
accessibility code in `talon_navigation`. It gives a new agent enough
context to select and complete a backlog item without rediscovering the
architecture, measurements, design constraints, or failed approaches.

Start with the [backlog index](#backlog-index) for track selection and the
[accessibility audit](accessibility-audit.md) for principle adherence and
remaining live-verification items.
The architecture below describes the implementation, not a guarantee that every
lifecycle claim has automated or current live-test coverage.

## Project principles

These principles are requirements, not suggestions:

1. **Own as little code as possible.** Prefer Talon, AxKit, and existing
   community actions over custom accessibility infrastructure.
2. **Keep behavior application-independent.** Application-specific Talon
   settings and AxKit overrides are acceptable when an application exposes a
   materially different AX model. Do not build application-name branches into
   the core traversal.
3. **Use only the focused application and focused window by default.** Do not
   label every window owned by an application. The proposed mouse-centered
   track is an explicit opt-in exception to investigate, not permission to
   broaden existing commands.
4. **Keep diagnostic code isolated.** Snapshots, inventories, HTML reports, and
   experiments should not be imported by production labeling code.
5. **Do not add native AX callbacks.** Use Talon's supported `ui`, `axquery`,
   event, label, and attribute APIs.
6. **Surface errors.** Log the underlying exception and notify the user rather
   than silently falling back to success-shaped behavior.
7. **Ask before expanding feature scope.** In particular, do not add fuzzy
   matching, custom overlays, background polling, or application adapters
   without first explaining the maintenance cost.
8. **Make experiments removable.** A spike should live in isolated files and
   avoid changing established behavior until it is validated.

## Current architecture

### Application control numbers

- [`accessibility/inventory.py`](../accessibility/inventory.py)
  - Labels pressable controls in the focused AX window.
  - Uses Talon's native `axquery.query_all`.
  - Enables lazy accessibility interfaces through Talon AX attribute writes.
  - Maintains the activation disallow list and per-process explicit on/off
    override.
  - Refreshes through supported Talon UI events.
- [`accessibility/inventory.talon`](../accessibility/inventory.talon)
  - Production commands for application numbers and AX interface toggles.
- [`accessibility/inventory_active.talon`](../accessibility/inventory_active.talon)
  - Commands active while application labels are visible.
- [`accessibility/inventory_vscode.talon`](../accessibility/inventory_vscode.talon)
  - Sets VS Code's maximum AX query depth to unlimited (`0`) and query timeout
    to 3 seconds, following the mokuro layout checks in [N10](numbers-and-menus.md).
  - Replaces the proven-broken depth-13 limit and enables the generic web-area
    ownership check to exclude covered browser pages.
  - Non-button row support and latency remain unresolved; this is not a complete
    VS Code navigation implementation.
- [`lib/labels.py`](../lib/labels.py)
  - Shared thin wrapper around Talon's `actions.labels`.

The production query is:

```text
[AXPosition]:action(AXPress)
```

It is executed with:

- The application's `AXFocusedWindow` as root.
- `visible_only=True`.
- A query timeout read from `user.accessibility_query_timeout` (default 1 second;
  VS Code overrides it to 3 seconds).
- `max_depth` read from
  `user.accessibility_query_max_depth`.

Results exclude disabled or explicitly hidden controls and controls with missing,
non-finite, or non-positive frames. `visible_only=True` alone still returns
zero-sized controls in VS Code. Distinct controls sharing a frame are retained;
valid geometry does not establish that a control is unobscured.

`user.accessibility_defer_web_areas` defaults to `false` and is enabled only in
the VS Code context (N12b). Native controls and the one `AXWebArea` whose title
equals the window title are numbered first. Every other web area gets one
centre hit test afterwards; only those that own the hit are queried, and their
controls are appended without renumbering. If no unique primary web area
exists, the whole window is queried. Selection rechecks that the target's web
area still owns its centre. This is a centre-point policy, not a proof of
whole-control visibility: a partly visible page whose centre is covered is not
numbered, and hidden items within the same web area remain.

Query failures, including Talon's observed `AttributeError: AXRole`, log the
exception, stop the label session and notify the user. Empty or failed initial
queries explicitly stop the session even before its override tag is active.

The generic depth setting is `0`, meaning unlimited. The implementation maps
zero to Talon's native `-1`. Negative configured values are rejected.
The query timeout must be finite and greater than zero. A larger timeout is a
budget, not a mandatory wait or a universal completeness guarantee. In the
tested mokuro layouts, the original one-second budget truncated results even
after removing the depth cap.

### Accessibility activation

Some applications do not build their AX tree until accessibility is requested.
The generic activation handshake:

1. Reads the application `AXRole`.
2. Attempts `AXEnhancedUserInterface = True`.
3. Attempts `AXManualAccessibility = True`.
4. Ignores only Talon's `ui.UIErr` for unsupported attributes.

Relevant setting:

```text
user.accessibility_activation_disallowed_bundles
```

It is a comma-separated list of exact bundle IDs. Normal activation respects
the list; explicit force-on bypasses it. Explicit off is tracked per process so
another command does not immediately turn the interfaces back on.

The action `user.accessibility_prepare_active_app()` exposes the same activation
path to other read-only/accessibility features without duplicating the
handshake.

### Debug snapshots and reports

- [`accessibility/debug_snapshots.py`](../accessibility/debug_snapshots.py)
  - Explicit inventory and snapshot actions.
- [`accessibility/debug_snapshots.talon`](../accessibility/debug_snapshots.talon)
  - `accessibility inventory`, `accessibility inventory all`, and
    `accessibility snapshot`.
- [`accessibility/inventory_core.py`](../accessibility/inventory_core.py)
  - Debug-only iterative AX traversal.
- [`accessibility/snapshots.py`](../accessibility/snapshots.py)
  - Atomic full and redacted JSON serialization.
- [`scripts/ax_tree_report.py`](../scripts/ax_tree_report.py)
  - Converts a snapshot into hierarchy and spatial HTML views.
- [`tests/test_accessibility_inventory.py`](../tests/test_accessibility_inventory.py)
- [`tests/test_accessibility_snapshots.py`](../tests/test_accessibility_snapshots.py)
- [`tests/test_ax_tree_report.py`](../tests/test_ax_tree_report.py)

Generated snapshots and reports are written under `ax-trees/`, which is ignored
by Git. Full snapshots may contain private text and should not be committed.

### Editable word highlight spike

The spike is deliberately isolated and is retained for further refinement:

- [`accessibility/text_highlight_spike.py`](../accessibility/text_highlight_spike.py)
- [`accessibility/text_highlight_spike_core.py`](../accessibility/text_highlight_spike_core.py)
- [`accessibility/text_highlight_spike.talon`](../accessibility/text_highlight_spike.talon)
- [`accessibility/text_highlight_spike_active.talon`](../accessibility/text_highlight_spike_active.talon)
- [`tests/test_text_highlight_spike.py`](../tests/test_text_highlight_spike.py)

Current behavior:

- Searches only the focused editable AX element.
- Uses exact, case-insensitive matches and the existing community homophone
  action.
- Selects the occurrence nearest the caret initially.
- Keeps matches in document order.
- Displays a numbered Talon imgui popup with surrounding context.
- Supports number selection and next/previous/first/last navigation.
- Keeps the popup open after selection.
- Stops on application or active-window changes, reliable focus loss, text
  changes, or a changed shared-buffer offset (see
  [audit A4](accessibility-audit.md#a4-stale-session-identity--windowoffset-checks-added-identity-gaps-remain)).
- Preserves the selected word when the popup closes.
- Handles Word's `AXSharedCharacterRange` offset.

Commands:

```text
highlight word <word>

highlight next
next
highlight previous
previous
highlight first
first
highlight last
last
highlight <number>
<number>

hide highlights
close highlights
cancel highlights
```

Escape also closes the popup.

## Backlog index

Each file breaks work into bounded spikes with evidence and exit criteria.
An exploration is not authorization to promote a feature or add infrastructure.
Dependencies are stated per spike; unrelated tracks can proceed independently.
Existing measurements below and in the track files are historical, not freshly
verified performance claims.

| Track | Scope | Suggested first spike |
|---|---|---|
| [Highlighting](highlighting.md) | Editable validation, static text, substring bounds, matching | H1 voice validation; H2 lifecycle safety before promotion |
| [Numbers and menus](numbers-and-menus.md) | Speed and grouping, app profiles, named sections, label handoff | N1/N2 timing baseline; N4/N8 grouping |
| [Mouse AX controls](mouse-ax.md) | Hovered window, radius/directional numbers, background activation | M1 supported hit-testing and M2 geometry |
| [Window hints](window-hints.md) | Pane hints, `number/move to/focus <pane>`, per-app pane config, auto-labelling | WH0 ground truth and WH2 pure geometry, then WH1 on Outlook |
| [Workflow and command discovery](workflow-and-discovery.md) | HUD/"hug", profile-switcher Firefox aliases, Rango aliases, Community command learning | W5/W7/W8 existing-command learning; W3 profile identity |
| [Cross-platform](cross-platform.md) | AX/UIA overlap; learn existing Windows commands (custom aliases cancelled) | P3 Community shortcut learning |
| [Accessibility audit](accessibility-audit.md) | Fix evidence and remaining correctness limitations | See verification |
| [Verification](verification.md) | Automated coverage versus remaining live/provider checks; further audit | Reuse tests first; live checks only for uncovered behaviour |
| [Assessment](assessment.md) | Critique, overlap findings, and effort for every idea | Read before picking a spike |

### Resolve unrelated repository baseline failures separately

**Priority:** Separate maintenance task

The previous handoff recorded passing focused checks, but the full command:

```bash
uv run python scripts/check.py
```

reported unrelated pre-existing issues (not revalidated by a backlog edit):

- Python formatting differences in:
  - `general/sleep_captions.py`
  - `general/targeted_sleep.py`
  - `tests/test_targeted_sleep.py`
- Talon formatting differences in:
  - `dictation/dictation.talon`
  - `general/sleep_warning.talon`
  - `menus/menu_labels.talon`
  - `menus/menu_labels_active.talon`
- Nine failures in dictation and sleep-related tests.

Do not mix those fixes into an accessibility backlog change unless explicitly
requested.

## Important failed approaches and lessons

### Do not restore the native AX observer

An earlier implementation used `ctypes` and a custom macOS AX observer.
It caused repeated Talon crashes:

- `EXC_BAD_ACCESS` / `SIGSEGV`
- Crashes inside `ffi_closure_SYSV_inner`
- Triggered while macOS delivered AX notifications

The native observer implementation was deleted. Talon remained stable after
moving to supported `ui.register(...)` events and Talon AX attribute setters.

Do not reintroduce:

- `ctypes` AX bindings
- CFFI callbacks
- Native callback trampolines
- Custom AX observer lifecycle management

### Do not query only `ui.active_window().element`

Firefox exposed only native traffic-light controls from that root while the
application AX tree contained hundreds of controls. The working root is the
active application's `AXFocusedWindow`, with an active menu added separately.

### Do not hard-code Slack, Firefox, or Electron in core traversal

The AX activation handshake is generic. Unsupported attributes raise
`ui.UIErr` and are skipped. Application-specific behavior should be expressed
through Talon settings or existing AxKit overrides.

### `AXManualAccessibility` is not universally supported

Firefox rejected `AXManualAccessibility` but responded to
`AXEnhancedUserInterface` and role access. Both attributes are attempted
independently.

### Turning AX interfaces off may not remove an existing tree

Applications such as Firefox may retain an already-created AX tree until the
process restarts. The off command controls subsequent activation behavior but
cannot guarantee immediate destruction of application-owned AX state.

### `visible_only=True` is not strict screen visibility

It may include:

- Elements without usable frames.
- Several AX nodes sharing one frame.
- Virtual or wrapper nodes.
- Nodes the application considers visible even when their visual meaning is
  unclear.

Always measure frames and actual label behavior before treating the result as a
visible-control set.

**Confirmed 2026-10-30:** covered Slack-report webviews in VS Code retain
`AXHidden=False` and are returned by visibility-pruned queries. Their HTML
buttons are legitimate controls on an invisible page, not live Slack controls
leaking into VS Code. Global hit tests resolve to the visible workbench instead.
See [N2/N9](numbers-and-menus.md) for timings and the bounded generic-visibility
spike. Sampling does not by itself prove an arbitrary view is fully covered.

### Do not raise group z-index on hover/focus

The spatial report originally promoted a full-size group above all descendants
on hover. Entering the diagram then made only the outer group selectable.

Related fixes in [`scripts/ax_tree_report.py`](../scripts/ax_tree_report.py):

- Hover/focus no longer changes spatial stacking.
- Structural AX roles remain on the group-outline layer even when pruning
  leaves them childless.
- Controls remain above structural groups according to tree depth.

### Childless `AXGroup` is not automatically a control

Slack's full-window `p-theme_background` group had `AXShowMenu`, no retained
children, and a full-window frame. Treating every leaf as a filled control
caused it to cover real controls. Spatial classification now uses structural
AX roles rather than only `node.children`.

### Do not depend solely on `ui.focused_element()` in lazy Electron apps

Slack can report `RuntimeError: No element found` and expose no editable roles
until AX interfaces are enabled. The highlight spike now retries through
`user.accessibility_prepare_active_app()`.

### `AXFocused` is not reliable across applications

Word may return a valid document `AXTextArea` through AxKit while reporting
`AXFocused = false`. The highlight session only enforces focus loss after an
application has demonstrated reliable focused-state reporting.

### `AXSelectedText` may lag or be empty

Slack sometimes reports stale selected text immediately after a range write.
The highlight spike now treats a matching read-back `AXSelectedTextRange` as
authoritative, waits briefly, and retries once.

### The active tag must be published by an unconditional context

The first highlight spike assigned its active tag using a context whose own
match required that tag. The popup appeared, but follow-up voice commands never
activated. The tag is now published from a normal macOS context; the separate
`.talon` file consumes it.

### Avoid custom per-word overlays until range bounds are proven

The numbered context popup is intentionally preferred over a custom canvas.
Range geometry is currently unproven across the target applications.

## Validation and diagnostic workflow

### Focused checks

Use the smallest relevant checks:

```bash
uv run ruff check \
  accessibility/inventory.py \
  accessibility/activation.py \
  accessibility/controls.py \
  accessibility/application_session.py \
  accessibility/text_highlight_spike.py \
  accessibility/text_highlight_spike_core.py \
  tests/test_text_highlight_spike.py

uv run ruff format --check \
  accessibility/inventory.py \
  accessibility/activation.py \
  accessibility/controls.py \
  accessibility/application_session.py \
  accessibility/text_highlight_spike.py \
  accessibility/text_highlight_spike_core.py \
  tests/test_text_highlight_spike.py

node scripts/lint_talon.mjs \
  accessibility/inventory.talon \
  accessibility/inventory_active.talon \
  accessibility/inventory_vscode.talon \
  accessibility/text_highlight_spike.talon \
  accessibility/text_highlight_spike_active.talon

uv run python -m unittest discover -s tests -p 'test_application_*.py'

uv run python -m unittest \
  tests.test_highlight_runtime \
  tests.test_accessibility_debug_runtime \
  tests.test_text_highlight_spike \
  tests.test_accessibility_inventory \
  tests.test_accessibility_snapshots \
  tests.test_ax_tree_report
```

### Talon logs

Normal log:

```text
~/.talon/talon.log
```

The log currently also contains an unrelated recurring rejection-path error:

```text
KeyError: 'sys.speech.speaker_verification_path'
```

Do not attribute that error to accessibility code without matching timestamps
and a relevant traceback.

### Talon REPL

The standalone launcher has intermittently printed:

```text
Python environment not set up correctly. Try relaunching Talon.
```

The reliable invocation used during this work is:

```bash
/Applications/Talon.app/Contents/Resources/venv_bin/python \
  /Applications/Talon.app/Contents/Resources/repl.py
```

The REPL compiles one statement at a time. For multiline diagnostics, pipe one
`exec(<repr of source>)` expression rather than raw multiple statements.

### Live-test safety

When testing selection:

1. Save the original active application.
2. Save the original `AXSelectedTextRange`.
3. Do not write `AXValue`.
4. Restore the original range in `finally`.
5. Close any active popup/session in `finally`.
6. Restore the original application.
7. Never print unrelated document text; report roles, lengths, ranges, and
   booleans unless the user supplied the exact test text.

## Useful measurements and confirmed AX examples

### Slack text classification

Confirmed examples:

- Sent message text was exposed as `AXStaticText` under an AX document/message
  group.
- Composer draft was exposed as `AXTextArea` with an editable ancestor and
  `AXValue`.
- Channel/direct-message entries were exposed as row/outline-row or group
  elements under the sidebar.

The Slack composer accepted a reversible `AXSelectedTextRange` write after it
was focused. The test selected the expected word and restored the original
range.

### Word editable context

AxKit's Office override in
[`talon_axkit/dictation/app_overrides/office.py`](../../talon_axkit/dictation/app_overrides/office.py)
finds the appropriate Office text area. Word may expose only part of a document
through `AXValue`; `AXSharedCharacterRange` maps local buffer offsets back to
document selection offsets.

Related AxKit context:

- [`talon_axkit/dictation/dictation_context.py`](../../talon_axkit/dictation/dictation_context.py)

### Accessibility tree reports

Snapshot paths are child-index routes used only to reconstruct a hierarchy.
They are unstable and must not become persistent identifiers.

Group-name fallback order in the HTML report:

1. `AXTitle`
2. `AXDescription`
3. `AXPlaceholderValue`
4. `AXValue`
5. `AXDOMIdentifier`
6. `AXIdentifier`
7. `AXHelp`
8. Meaningful `AXRoleDescription`
9. Cleaned first `AXDOMClassList` entry
10. `AXRole`

The spatial view normalizes each node's `AXFrame` against the focused-window
frame. It is a debugging visualization, not production navigation logic.
