# Live verification and remaining audit backlog

Follow the [project principles](README.md). The [audit](accessibility-audit.md)
fixes have automated regression coverage, but **not all correctness gaps are
closed** (especially same-window editable focus with unreliable AX reporting
and Unicode range units). Do not equate passing mocks with live-provider
validation. Run existing checks first, add missing regression tests, then
spend live-test time only on behaviour those tests cannot establish.
Record results in the spike's section; don't create a separate notes file.

## Coverage checkpoint (2026-10-29)

Automated checks live in
[test_application_session.py](../tests/test_application_session.py),
[test_highlight_runtime.py](../tests/test_highlight_runtime.py),
[test_accessibility_debug_runtime.py](../tests/test_accessibility_debug_runtime.py),
[test_accessibility_snapshots.py](../tests/test_accessibility_snapshots.py),
and the menu test suites:
[test_menu_back.py](../tests/test_menu_back.py),
[test_menu_hover.py](../tests/test_menu_hover.py),
[test_menu_navigation.py](../tests/test_menu_navigation.py),
[test_menu_session.py](../tests/test_menu_session.py), and
[test_menu_wiring.py](../tests/test_menu_wiring.py).

| Spike | Automated evidence | Still needs live/provider evidence |
|---|---|---|
| V1 | Tag publication, selection dispatch, hide cleanup | Real Talon context/voice precedence and escape grammar |
| V2 | Simulated native hide during selection, expansion survives, scheduled callback re-renders new targets; ordinary selection cleans up | Actual native labels hide/press behaviour and popup/menu integration |
| V3 | Same-app changed window rejects old target before native selection | Provider window equality and refresh/selection event ordering |
| V4 | Module re-execution stops old session and cancels pending job | Talon's actual reload namespaces, registrations, and visible overlay cleanup |
| V5 | Unsupported AX attributes; inventory errors; snapshot permission failure logs/notifies; partial warning; capture/dump errors retained; full/redacted share one dump | Optional UI smoke test of notification visibility, not failure reinjection |
| V6 | App/window/text/reliable-focus/offset changes, invalid numbers, write failures; navigation wrap; close preserves selection | Word/Slack AX semantics and unreliable same-window focus |
| V7 | Python matching/offset helpers, **not** AX range-unit conversion | Non-BMP range round-trip in each supported provider |
| V8 | Existing frame filters and mocked selection dispatch | Covered report webviews confirmed live; generic occlusion handling and spoken selection remain unverified |

New tests extend rather than duplicate the existing mocked cases. V5's former
instruction to change the real snapshot directory's permissions is removed:
injected `PermissionError` verifies that branch without modifying user state.

**Latest execution:** the six focused unittest modules ran **70 tests, all
passing** before the UTF-16 fix. The latest run after the fix ran **73 tests,
all passing**; Ruff lint and formatting passed. The added converter tests and
runtime range regression were specifically prompted by V7's live Word failure.

**Live-test safety:** the user prepared an expendable Word document and unsent
Slack draft, and confirmed they were ready. The checked Word text contained
repeated words and a non-BMP character before the target. The Slack draft
contained repeated words but no emoji. The Slack checks changed selection only;
the draft was not submitted. Never replace working text or restart Talon as
part of these checks. Record live outcomes separately from automated passes.

## Already verified live (Talon REPL, read-only, 2026-10-29)

| Assumption the fixes rely on | Result |
|---|---|
| Two reads of `AXFocusedWindow` compare equal (A4 numbers check) | `True` in VS Code |
| `ui.active_window().id` is a stable identity (A4 highlight check) | `int`, stable across reads |
| Error type when a Talon action is missing (A3 homophones) | `KeyError`, **not** `ui.ActionFailed`; now handled |
| Community `homophones_get` is installed locally | Returns `['their', 'there', "they're"]` for "there" |

## Live checks for the audit fixes

### V1. Application-number tag and grammar (A1)

**Status:** direct live show/hide and active-tag propagation passed in Slack.
The attempted phrase simulation ran while Talon was in sleep mode and matched
the generic `<phrase>: skip()` rule, so it did **not** verify the spoken grammar.
Manual voice check: the Talon log shows the spoken `show application numbers` activating
application labels in Slack and VS Code (`enabled AX interfaces …` entries).
Whether `hide numbers` and `key escape` cleaned up still needs confirming by eye; it is not logged.
The previously repeated `debug: rejection path failed` /
`KeyError: 'sys.speech.speaker_verification_path'` errors came from Talon's
built-in verify plugin, not this repo. On the local Talon 1.0.0 build 116
installation, the verification path was initially absent. After the user
recorded a clip in Talon Settings > Speech Recognition, the path was present,
the model and speaker embedding were loaded, and the missing-path error did not
recur in the observed log. Talon subsequently logged speaker mismatches; whether
those were expected is unknown, and the user requested no further investigation.

The user confirms `show application numbers` produces different results from
`show numbers`, but reports unclear/broken target correspondence in VS Code.
This is not a successful visual-navigation check. See
[N3](numbers-and-menus.md#n3-compare-one-reversible-label-filter-at-a-time)
for the frame filter and the confirmed covered-report/depth-limit problem.

**Effort:** XS. In VS Code and Slack: `show application numbers`, then say a
number, `hide numbers`, and press escape in separate runs. Run `show application
numbers` again, then switch to menu labels (`show menu numbers`).

**Done when:** `hide numbers`/escape work only while labels are visible, no
`user.application_labels_active` tag remains after hiding (use Community's
`talon debug tags` to inspect active tags; a declared-tag registry alone does
not prove activation), and the Talon log has no
exceptions. If the grammar does not activate, the mocked tag-resolution model
in [accessibility_support.py](../tests/accessibility_support.py) is
wrong and must be corrected first.

**Observed by direct action:** `accessibility_show_application_numbers`
activated the tag; `actions.labels.hide()` cleared it. This verifies runtime
tag publication and native hide dispatch, but not voice recognition or
escape-phrase resolution.

### V2. Expandable controls keep their session (A1)

**Status:** native-hide simulation and refresh callback covered by tests;
actual provider/native-label behaviour pending.

**Effort:** XS. Select a popup button / combo box by number (e.g. a VS Code
dropdown or a Slack menu button). **Done when:** the refreshed labels appear
on the expanded surface, and a non-expanding button selection ends the
session. Overlaps [N7](numbers-and-menus.md#n7-verify-application-numbermenu-session-handoff);
do both together.

### V3. Stale-window rejection for numbers (A4)

**Status:** deterministic stale-window rejection covered by a test.
**Effort:** XS for provider smoke testing. Open two windows of one app, show
numbers, switch windows, and observe whether labels refresh or close.

**Done when:** only freshly rendered numbers can select controls in the new
window. Rejection, cleanup, or a valid refresh is acceptable; do not require a
human to beat the scheduled refresh to reproduce a race already tested
deterministically. Confirm a normal unchanged-window selection still works.

### V4. Reload cleanup (A2)

**Status:** re-execution and pending-job cancellation covered; actual Talon
module reload/event registration semantics pending.

**Effort:** XS. With application numbers visible and with a highlight popup
open, save [inventory.py](../application_controls/inventory.py) and
[text_highlight_spike.py](../experiments/text_highlight/text_highlight_spike.py) separately.

**Done when:** labels/popup close, the active tag is cleared, and the log
shows no duplicate refreshes after several later UI events.

### V5. Error notifications reach the user (A3, A5)

**Status:** automated action-boundary, logging, notification, and snapshot
metadata tests cover the requested failure paths. No live permission changes
or assumed Finder/System Settings failure are needed.

**Optional remaining UI check (XS):** confirm one notification is visible with
the current Talon/macOS notification settings. A live provider partial capture
can be checked if encountered naturally; don't capture private app data merely
to repeat injected error-path tests.

### V6. Highlight staleness in Word and Slack (A4)

**Status:** in the prepared disposable fixtures, Word passed start/next/
previous/first/last on repeated occurrences, and Slack passed start/next/
previous in the unsent draft. Both were closed with selection preserved.
Stale-focus/window and edits remain automated-only / unverified live.

**Effort:** S. Prerequisite for [H1](highlighting.md#h1-validate-editable-highlighting-by-voice).

1. Word: highlight a word, scroll so Word changes `AXSharedCharacterRange`,
   then say `next`: expect rejection rather than a wrong selection.
2. Highlight, switch to another window, then say a number: expect rejection.
3. Known remaining gap: when `AXFocused` is unreliable, moving focus to another
   editable control *within the same window* can go undetected. The stored
   element's text can stay unchanged even when the new control has different
   text, so text comparison is not an identity check. Record provider behaviour.

**Done when:** each case is recorded per app. Case 3 is a safety gate before
promotion, not something passing mocks close; investigate supported editable
element identity before changing behaviour. No new polling.

### V7. Unicode range units

**Status:** Word confirmed AX ranges count UTF-16 code units. The first live
check selected a leading space plus `"targe"` for the expected target, using
range `(15, 21)` instead of `(16, 22)`. Added Python-codepoint↔UTF-16 conversion
in [text_highlight_spike_core.py](../experiments/text_highlight/text_highlight_spike_core.py)
and regression tests. Retest then selected `"target"` with range `(16, 22)`.
The Slack draft fixture did not contain the emoji, so Slack's range units
remain untested.

**Done when:** Word's post-fix check passed; Slack still requires a prepared
disposable composer fixture containing a non-BMP character before the target.

### V8. VS Code application-number target mapping and activation

**Corrected status (2026-10-30):** AX ancestry identifies the unexpected targets
as HTML buttons in the covered Slack report webview, not invalid VS Code
buttons. The report's click handler updates its inspector. The depth-13 cutoff
retains these shallow targets while omitting deeper workbench controls.
`AXHidden=False` and `visible_only=True` do not establish that the view is
unobscured.

Read-only hit tests at five points on each of the two currently exposed report
webviews never matched the view being tested or its descendants; a report
button's center instead hit the visible workbench. A known workbench control
hit itself or a descendant.
The workbench matched only three of five view-level sample points, so an
all-points-must-match visibility rule would be wrong. See
[N9](numbers-and-menus.md#n9-validate-vs-code-target-identity-and-activation)
for the generic visibility spike and
[N2](numbers-and-menus.md#n2-measure-query-filtering-and-rendering-separately)
for query/child-access/filter/signature timings.

**Still unverified:** whether the user's spoken 69 dispatched successfully.
Directly pressing a report button does not verify spoken number dispatch.
Mocked tests likewise establish dispatch calls, not the live provider effect.
The initial read-only probes did not activate controls, draw labels, change
settings, or read editor values.

**Subsequent approved N10 checks:** in mokuro, actual application-number
selection opened Accounts/Manage/Agent/editor-overflow menus, focused editor
and chat text areas, toggled panels/session visibility, and created a disposable
terminal. The test terminal and clean test file were removed; original terminals
and unsaved files were preserved. These verify action dispatch, not speech
recognition or the historical spoken 69. VS Code now has unlimited depth and a
3-second query budget, validated against longer-budget reference counts.
Covered-report visibility and Explorer/terminal/session-row coverage remain
unresolved; see the N10 findings before claiming the feature is fixed.

**Next check / done when:** validate generic branch visibility including
partial coverage, then use a known harmless visible control to verify the
spoken number and expected reversible action. Do not mark the feature fixed
from query counts, valid geometry, or a direct AX action alone.

## Remaining audit (code not covered by the original audit)

### U1. Menu labels and the shared label wrapper

**Effort:** S. Audit [menu_labels.py](../menus/menu_labels.py),
[menu_session.py](../menus/menu_session.py), and [labels.py](../lib/labels.py)
against the principles. In particular:

- `LabelSession.start_updates` uses a 100 ms `cron.interval` while waiting for
  menus. Confirm it is always bounded and cancelled (principle 7: no unbounded
  polling).
- Check reload cleanup ordering (the A2 defect pattern).

**Done when:** findings are fixed with tests in
[test_menu_back.py](../tests/test_menu_back.py),
[test_menu_hover.py](../tests/test_menu_hover.py),
[test_menu_navigation.py](../tests/test_menu_navigation.py),
[test_menu_session.py](../tests/test_menu_session.py), or
[test_menu_wiring.py](../tests/test_menu_wiring.py), or recorded as accepted.

### U2. Status-bar discovery and labels

**2026-11-02:** A live Slack window reproduced the "tree is too large" error
with 277 nodes and depth 26: the previous depth-12 cutoff rejected it after only
16 nodes. Panel traversal now accepts deep trees within its 600-node budget,
with regression coverage for deep panels, exact limits, and cycles. The original
19:22 error did not record its root or which limit was reached, so its exact
cause remains unconfirmed. Future node-limit failures log the provider and root
role rather than conflating node count with depth.

**Effort:** S. Audit [status/](../status/) for focused-scope (principle 3: a
menu-bar scan is an intentional exception and should be documented as one),
error surfacing, and reload cleanup. **Done when:** findings are fixed or
documented.

### U3. Element-event refresh cost

**Effort:** S. Both [inventory.py](../application_controls/inventory.py) and the
highlight spike register a global `ui.register("element", ...)` handler. With
numbers visible in VS Code, type for 10 seconds and count refreshes and query
time in the log. **Done when:** the refresh rate and the cost of each refresh
are recorded. If refreshes repeat the 1-second query back to back, propose a
debounce (with the user's approval) instead of adding polling.

### U4. Snapshot redaction completeness

**Effort:** XS. Compare the attribute names in a real full snapshot against
`REDACTED_ATTRIBUTES` in [snapshots.py](../diagnostics/snapshots.py). Look for
text-bearing attributes such as `AXSelectedText`, `AXValueDescription`,
`AXLabelValue`, and `AXDOMClassList`. **Done when:** the list is updated with a
test, or the omissions are justified. Redacted files stay local regardless.

### U5. Reports and generated HTML privacy

**Effort:** XS. Confirm that [ax_tree_report.py](../scripts/ax_tree_report.py)
and [reports/](../reports/) write generated output only to Git-ignored paths,
and that the HTML views do not embed full-snapshot text when given a redacted
input. **Done when:** confirmed with `git status` after generation and a test
if needed.

### U6. Repository baseline failures

Already tracked in the [README](README.md#resolve-unrelated-repository-baseline-failures-separately)
(format differences and nine dictation/sleep test failures). Fix those
separately before adopting a full-suite CI gate.
