# Accessibility principle audit

**Date:** 2026-10-29. **Scope:** all six Python and six Talon source files in
[accessibility](../accessibility/), their focused tests, the shared
[label wrapper](../lib/labels.py), and the adjacent
[menu implementation](../menus/menu_labels.py). This is a source/behavior audit with
fixes, not a security review or a live application certification.

## Conclusion

The audit found six gaps (A1-A6) between the code and the
[project principles](README.md). Corrective changes and regression tests exist for
the reported paths, with the remaining A4 limitations described below.
Coverage is in
regression tests in
[test_accessibility_runtime.py](../tests/test_accessibility_runtime.py) and
[test_accessibility_snapshots.py](../tests/test_accessibility_snapshots.py).
All seven original application-label regression tests failed against the pre-fix `HEAD` version
of [inventory.py](../accessibility/inventory.py) and pass now.

This is not blanket certification: mocks verify specific paths, not all Talon
or provider semantics. Remaining work includes **live** verification (context resolution, real AX
providers, voice), split into small spikes in [verification.md](verification.md).
That file also lists the assumptions already confirmed in the live Talon REPL
and audit spikes for code outside this audit's scope (menus, status, reports).

## Principle-by-principle assessment

| Principle | Assessment | Evidence / qualification |
|---|---|---|
| Own little code | Follows, with bounded root discovery | Production uses native `axquery`, `actions.labels`, and the shared label wrapper; highlighting reuses AxKit's dictation element and Community homophones. Staged numbering adds a bounded native-node walk that stops at web areas; native queries still enumerate their controls. |
| Application-independent behavior | Follows | No bundle-name branches in core traversal. Depth, staged web-area collection and surface clipping are generic settings enabled by app contexts. Cross-app filter comparisons remain open in N12d. Editable role/shared-range handling is generic. |
| Focused application/window | Partially verified (A4) | Window/offset rejection has tests. Same-window editable identity with unreliable `AXFocused` remains an open safety limitation. |
| Diagnostics isolated | Follows | Debug imports production's focused-surface helper, not the reverse. |
| Supported Talon APIs, no native callbacks | Follows | `ui.register`, native queries, AX attribute writes, cron one-shot refresh, imgui, labels, `ui.active_window`. No ctypes/CFFI observer. |
| Surface errors | Follows (after A3/A5) | Activation, toggle, selection, homophone, stale-element, and debug I/O failures are logged with `logging.exception` and notified. Partial snapshots are flagged. |
| Ask before scope expansion | Follows | No fuzzy matching, adapter framework, custom canvas, polling loop, or command override added. Mouse/profiles have decision gates. |
| Removable experiments | Follows | Highlighting remains isolated in its own files; its fixes touch only those files. |

### Live numbering follow-up (2026-10-30)

[N12c](numbers-and-menus.md#n12c-replace-talons-visibility-pruning-with-a-surface-clip)
records successful staged action-path checks and the Settings/long-list
comparison. No microphone recognition was tested. Surface clipping retained
all Talon-filtered controls in those sampled Settings states, but exposed
additional More Actions popups whose visibility/usability needs validation.
The real application-number command also reset the filtered/scrolled
Settings view to Commonly Used; this is **not** a passed state-preservation
check. Isolation and remediation are tracked in
[N12e](numbers-and-menus.md#n12e-preserve-the-settings-view-while-showing-numbers).

The filter is generic, not a VS Code Python branch. Its global default remains
off pending native-app, browser and other Electron-app comparisons in
[N12d](numbers-and-menus.md#n12d-compare-both-visibility-filters-across-applications).

## Findings and fixes

### A1. Application-label tag was self-gated — fixed

`ApplicationLabelSession` published `user.application_labels_active` on
`labels_ctx`, which itself required that tag, so the tag (and the select/hide
overrides plus [inventory_active.talon](../accessibility/inventory_active.talon)
grammar) could never activate. The session now publishes on the unconditional
`os: mac` context, mirroring [menu_labels.py](../menus/menu_labels.py);
`labels_ctx` keeps the overrides. `LabelOverrides.hide` now calls
`actions.next()` before stopping the session, matching the menu override.

**Tests:** the mock models tag-gated contexts; it does not establish Talon's
actual context resolution or native action dispatch semantics. Show → override active →
select dispatches natively → hide clears the tag; expansion keeps the session.
**Open:** confirm in live Talon that "hide numbers"/escape grammar activates.

### A2. Reload did not stop the previous session — fixed

[inventory.py](../accessibility/inventory.py) assigned `_session = None` before
reading `globals().get("_session")`. The prior session is now captured first,
as highlighting already did. **Tests:** re-executing the module in the same
namespace stops the old session and cancels its pending refresh job.

### A3. Error-reporting gaps — fixed

- AX activation in `_show_application_numbers` and
  `accessibility_set_interfaces` is now inside a `RuntimeError`/`UIErr`
  boundary that logs and notifies (and handles no active app).
- `ApplicationLabelSession.select` reads the target inside its `try`, so a
  stale element reports "Unable to activate the selected control."
- [debug_snapshots.py](../accessibility/debug_snapshots.py) actions log and
  notify AX and file I/O failures.
- Highlighting logs and notifies a failed homophone lookup (then matches the
  exact word), and an element that disappears (`UIErr`) ends the session with
  a notification instead of silently.
- The supported per-attribute `UIErr` skip during activation was kept.

A live REPL check showed that Talon raises `KeyError` (not `ActionFailed`) for
a missing action, so a missing homophones action is now handled and notified
separately.

### A4. Stale session identity — window/offset checks added; identity gaps remain

- Numbers: the session records `AXFocusedWindow` at render time; `select`
  rejects a label if the focused window changed before the scheduled refresh.
  A window change also forces a re-render even if the control signature matches.
- Highlighting: `validate` rejects a changed `ui.active_window().id` (an identity
  check that does not depend on Word's unreliable `AXFocused`) and a changed
  `AXSharedCharacterRange` offset with unchanged text.

**Open (live):** same-app focus moves *within one window* when `AXFocused` is
unreliable; Word/Slack normal selection regression; Python-index versus AX
UTF-16 range units for non-BMP text (emoji). Word exposed a UTF-16 mismatch;
conversion and automated coverage were added, and the post-fix Word check
passed. Slack's non-BMP behavior remains untested. Same-window editable
identity with unreliable `AXFocused` remains an open safety limitation.

### A5. Snapshots discarded incomplete-inventory evidence — fixed

[snapshots.py](../accessibility/snapshots.py) now writes a `surfaces` list with
per-surface node counts, collection errors, and `truncated`. The full and
redacted files derive from a **single** capture (same `captured_at`), and
`write_snapshots` returns whether the capture was partial; the debug action
notifies "Saved PARTIAL snapshots" in that case. Per-file atomic writes are
kept; pair-level atomicity is not promised. Redaction remains a finite
attribute list; keep all trees local and ignored by Git.

### A6. Runtime-module tests — added

[test_accessibility_runtime.py](../tests/test_accessibility_runtime.py) loads
the real [inventory.py](../accessibility/inventory.py) and
[text_highlight_spike.py](../accessibility/text_highlight_spike.py) against a
small Talon double (in the style of
[test_menu_labels.py](../tests/test_menu_labels.py)) and covers A1-A4. Mocked
tests do not replace the live voice matrix.

## Preliminary feasibility notes for the new tracks

- **Mouse AX:** [status discovery](../status/discovery.py) provides prior art for
  supported `ui.element_at(x, y)` and parent traversal. That is a useful local
  starting point, not proof of background-window enumeration or AXPress behavior.
  Reuse the supported pattern, not the menu-bar scan or an all-app scan.
  [M1-M5](mouse-ax.md) separate ownership, radius/nearest-N geometry, discovery,
  activation, and grammar decisions. No visible circle was requested.
- **App profiles:** the existing VS Code context demonstrates per-app depth
  tuning today. Arbitrary query/scope profiles and section labels are not
  implemented in application numbers. Menu title labels are existing prior art
  for names, but a structural Slack group is not automatically actionable.
  [N4-N6](numbers-and-menus.md#n4-inventory-application-profile-mechanisms-before-designing-new-ones)
  require a gap inventory before building another adapter layer.
- **Platform portability:** the production query/attributes are macOS AX
  specific even though the debug traversal shape is generic. Nothing in these
  macOS tests establishes Windows UIA parity; [P1-P2](cross-platform.md) require
  Windows evidence before extracting a common contract.
- **Matching policy:** exact and homophone terms are currently searched together,
  with nearest-caret selection; the code does not perform an exact-only pass
  before considering homophones. Keep documentation accurate and decide any
  ranking change explicitly rather than smuggling it into a cleanup.

## Validation performed

All commands used the existing local environment; no dependencies were installed.

- `uv run ruff check accessibility tests lib` and `ruff format`: passed.
- `node scripts/lint_talon.mjs accessibility/*.talon`: passed (no Talon edits).
- `uv run python -m unittest tests.test_accessibility_runtime
  tests.test_accessibility_snapshots tests.test_accessibility_inventory
  tests.test_text_highlight_spike tests.test_menu_labels
  tests.test_ax_tree_report`: **70 tests passed** on the latest run.
  This includes 15 added checks for native-hide simulation/refresh, lifecycle
  and selection failures, debug notification/logging boundaries, and capture
  consistency. See the [coverage checkpoint](verification.md#coverage-checkpoint-2026-10-29).
- Regression proof: with `HEAD`'s `inventory.py` temporarily restored, all 7
  application-label runtime tests failed (5 failures, 2 errors).

Read-only Talon REPL inspection checked API assumptions and installed lifecycle
command/action names. No focus changes, document selection writes, restart,
or Windows runtime tests were performed. The unrelated full-suite baseline
was not rerun.
