# Window hints backlog

**Status:** Pane labelling accepted on 2026-11-05 and moved to
[window_hints/](../window_hints/README.md). Focus and scoped numbering remain
unimplemented. The original exploration plan and chronological evidence below
are retained; historical limitations may be superseded by later entries.
Follow the [project principles](README.md).

## Idea

Label the *panes* of the focused window (for example Outlook Mail: tools,
inboxes, mail, message) with a short hint at each pane's top-left corner,
optionally with a rule under the hint spanning the pane width. A pane name can
then be used as a scope or target:

| Command (working names) | Effect |
|---|---|
| `number <pane>` | Application numbers restricted to that pane's controls, e.g. `number tools` numbers only Mail, Calendar, Contacts, ..., OneDrive, More |
| `move to <pane>` | Move the mouse to the centre of the pane |
| `focus <pane>` | Give the pane keyboard focus so arrows/page keys navigate or scroll it |
| `show hints` / `hide hints` | Show or remove pane hints for the focused window |

Per-application configuration names and selects panes. Where an application
has no configuration, an opt-in automatic labelling heuristic is attempted.

## Relationship to existing work

- Builds on, and must not duplicate, **N4** (profile mechanisms), **N6**
  (named sections), **N8** (one grouped scope) and **N12/N12c** (subtree root
  and surface clip) in [numbers-and-menus.md](numbers-and-menus.md). Where an
  N-spike already answered a question, cite it and re-measure only on the
  window-hint fixtures. WH1/WH6 should be scheduled *after* N4/N6/N8 results
  are read; if N8 has been executed, WH6 reuses its method.
- Reuse [lib/labels.py](../lib/labels.py), the application label session
  ([application_session.py](../accessibility/application_session.py)) and
  `labels.mouse_move` before creating anything new.
- Hovered-window discovery is [M1](mouse-ax.md); this track is
  focused-window only.
- Known constraints that bind these spikes: `AXFocused` is unreliable, child
  index routes are not persistent IDs, `visible_only=True` is not visibility,
  childless groups are not controls, Slack's section headers expose no title
  text (N12d), no native AX callbacks, no hard-coded app names in core code
  (see lessons in the README).

## Method rules

1. Read-only until the spike says otherwise; spikes live in isolated,
   removable files (suggested `accessibility/window_hints_spike*.py` /
   `.talon`) that production code does not import.
2. Every claim cites a measurement on a **recorded fixture state** (app,
   version, window size, display, layout). Fixtures are labelled fixtures.
3. Each spike ends at a decision: *proceed*, *proceed with changes*, *drop*, or
   *unresolved*. A spike that cannot answer its question says so; it does not
   substitute a plausible explanation.
4. Never print private text. Record roles, names of structural panes, counts,
   frames, booleans, and timings. Redact window titles and message content.
5. Live tests save and restore the active app, mouse position, focus, scroll
   offsets and selection; clean up labels in `finally`; do not click, type,
   send, delete, or write `AXValue`.
6. Failures log the exception and notify the user; no success-shaped fallback.
7. **Approval gates** (principle 7). Stop and ask, with maintenance cost,
   before: a custom canvas/overlay (WH4), any persisted configuration format
   (WH7), fuzzy name matching, background polling or refresh timers.

## Fixture matrix (shared by all spikes)

| ID | Application / state | Expected panes (hand-recorded ground truth) |
|---|---|---|
| F1 | Outlook Mail, 3-pane, reading pane right | tools (sidebar), inboxes (folder list), mail (message list), message (reading pane) |
| F2 | Outlook Mail, reading pane bottom; and reading pane off | same, different geometry; `message` absent |
| F3 | Outlook Calendar | tools, calendar grid, date navigator (if present) |
| F4 | Slack (web-view based) | sidebar, conversation, thread/details pane when open |
| F5 | Word | ribbon, document, navigation pane when open |
| F6 | VS Code | activity bar, side bar, editor, panel, chat |
| F7 | Finder or Mail.app (native split views) | sidebar, list, preview |
| F8 | Unconfigured simple app (e.g. TextEdit/Notes) | whatever a human would name; may be one pane |

Ground truth is written by hand from a screenshot before running any probe,
as pane name plus approximate rectangle. Probes are scored against it, never
the reverse. Record: app version, window size, display scaling, window state
(full screen, other Space), and whether reading pane/sidebar is collapsed.

---

## WH0. Ground truth and scoring harness

**Effort:** S. **Depends on:** nothing. **Prerequisite for WH1, WH3, WH6, WH8.**

Create the fixture catalogue above as a small data file (in a test fixtures or
spike directory) and a pure scoring function: given hand rectangles and
candidate pane rectangles, compute matches (IoU >= 0.8 and the same rough
role), misses, and extras.

**Validation criteria**
- Unit tests: perfect match, one missing pane, one extra, split pane
  (one truth, two candidates), merged pane, rectangle order irrelevant,
  zero/negative/invalid frames rejected, tie-breaking deterministic.
- Scoring a hand-built candidate list equal to ground truth gives precision =
  recall = 1.0; removing one gives recall < 1 and names the missed pane.
- Ground truth for F1-F8 is committed (no private text) and reviewed by the user.

**Done when:** harness and fixtures exist and the user agrees the expected
pane lists are the intended UX. This also settles *what counts as a pane*.

## WH1. Read-only pane-candidate discovery

**Effort:** M. **Depends on:** WH0; N4/N6 results read first.

For each fixture, gather pane-like containers from the focused window using
the same root as production numbers (`AXFocusedWindow`) and Talon's supported
`axquery`/`ui` APIs. Candidate roles to measure, not assume: `AXSplitGroup`
children, `AXScrollArea`, `AXTabGroup`, `AXToolbar`, `AXOutline`, `AXTable`,
`AXList`, `AXWebArea`, landmark-like `AXGroup` with a subrole, identifier or
description. For each candidate record role, subrole, presence of
title/description/identifier/title UI element, frame, depth, child count,
actions, and whether it contains pressable controls.

Measure query time separately from filtering (as N2). Do not walk other
windows or apps. Repeat after relaunch, after resizing the window, and after
collapsing/expanding a pane to measure stability.

**Validation criteria**
- Per fixture, a table of precision/recall against WH0 for each *candidate
  rule* (role-only, role + has pressables, split-group children, named
  groups). Report every miss with the reason (no AX node, node exists but
  unnamed, frame invalid, etc.).
- Stability: same pane set (by role + semantic attributes, **not** child
  index) across 3 relaunches and 2 window sizes; any attribute that changes is
  listed. Index paths are never persisted.
- Query time p50/p95 over >= 10 runs per fixture; a run that hits the query
  timeout is reported as truncated, not as a result.
- Apps that need activation (Slack, VS Code, Outlook) are measured with the
  existing activation path; behavior when the tree is empty is an explicit
  error.
- A capability table says, per fixture, which attributes reliably identify a
  pane. Fixtures where Slack-like headers expose no title are recorded as
  gaps.

**Done when:** a rule (or set of rules) with measured recall >= 0.9 and
precision >= 0.8 on at least F1 plus two other fixtures exists, or the track
is reported as needing per-app configuration only (which then raises WH7's
priority). Anything unmeasured is "unresolved".

## WH2. Pane geometry: nesting, overlap, ordering, anchors (pure)

**Effort:** S. **Depends on:** nothing live; can run in parallel with WH1.

Pure functions, no Talon APIs: clip each candidate to the window frame,
discard zero/invalid/tiny frames (threshold is a measured, documented
constant), dedupe identical frames, resolve nesting (keep the outermost pane
or the innermost? decide from WH0 fixtures; expose children as optional
sub-panes), order panes deterministically (left-to-right then top-to-bottom,
tolerant to a few pixels), and compute the hint anchor (top-left, inset, kept
inside the visible clipped rectangle) and underline segment.

**Validation criteria (unit tests)**
- Side-by-side panes, stacked panes, nested panes, partially offscreen
  (negative origin), multi-display negative coordinates, pane taller than the
  screen, overlapping siblings, identical frames, 1-px panes, NaN/inf.
- Ordering is stable under input shuffling (property test over random
  shuffles).
- Anchors never leave the clipped pane; two anchors never overlap when panes
  are >= the hint size apart; overlapping hints are reported, not silently
  moved off their pane.
- Reading-pane right vs bottom (F1/F2 frames) yields the expected ordering
  and numbering of hints.

**Done when:** tests pass under `uv run python -m unittest` and `ruff check`/
`format --check` for the new files.

## WH3. Pane naming and spoken names

**Effort:** M. **Depends on:** WH1 attribute table.

Decide how a pane gets a speakable name: AX `AXTitle`, `AXDescription`,
`AXTitleUIElement`, `AXIdentifier`, a contained heading/first static text,
else a role-based default (`sidebar`, `list`, `content`) or an ordinal
(`pane one`). Explicit per-app aliases (e.g. Outlook's folder list called
`inboxes`) override derived names. Handle duplicates, localized titles,
empty names, names that collide with existing Talon commands, and names that
change with content (a message subject is not a pane name).

**Validation criteria**
- Unit tests: precedence order, duplicates get deterministic suffixes or are
  reported as ambiguous, normalization to speakable lowercase, empty/None
  rejected, volatile-title detection (name equal to window title or content
  text is not used).
- Live on F1/F3/F4/F6: the derived or aliased name for every ground-truth pane
  is unique within the window; list collisions with existing spoken commands
  using the repository command-inventory tooling
  ([test_command_inventory.py](../tests/test_command_inventory.py)).
- Naming is deterministic across two relaunches and a locale-neutral check
  (names come from config/aliases when AX titles are localized).
- `<pane>` capture can be a Talon list scoped to the matching context; a
  name that is absent or ambiguous produces an explicit notification, never a
  different pane.

**Done when:** a naming precedence is chosen with evidence, and ambiguity
behavior is .

## WH4. Rendering hints (approval-gated)

**Effort:** S-M. **Depends on:** WH2, WH3. **Approval gate:** custom canvas.

Compare, on F1 and F4:

1. Existing label wrapper ([lib/labels.py](../lib/labels.py) / Talon labels)
   anchored to pane top-left, text-only. Zero new overlay code.
2. The same plus the pane-width rule, which Talon labels probably cannot
   draw. If only a canvas can, report the extra code, lifecycle risks,
   z-order interaction with app labels (README "Do not raise group z-index"),
   and request approval before building it.
3. Text-only hints with no rule (acceptable fallback).

Hints are drawn only on explicit `show hints`; no polling. Refresh uses the
same supported `ui` events as application numbers.

**Validation criteria**
- Hints for each ground-truth pane appear at the top-left within the pane
  rectangle on F1, F2, F4, F6 (screenshot recorded; positions compared with
  WH2 anchors within 2 px).
- Hints do not obscure the first control of the pane in F1/F4 (compare with
  the control frames from a numbers query).
- Lifecycle: hide, window switch, app switch, resize, pane collapse, screen
  change, Talon reload each leave **zero** stale hints (assert tag/label
  ownership as in
  [test_application_session.py](../tests/test_application_session.py)).
- Coexistence: with hints visible, `show numbers` and menu labels either work
  or fail with an explicit, documented message; ownership tests prove neither
  steals the other's tag.
- Cost: time-to-hints p50/p95 (reuse the N18c phase breakdown) and a
  stated budget (proposal: < 300 ms after the pane query).
- Canvas decision is recorded: approved, or text-only chosen.

**Done when:** rendering option chosen, with measured latency and lifecycle
tests; otherwise stop at the approval question.

## WH5. `move to <pane>` and `focus <pane>`

**Effort:** M. **Depends on:** WH2, WH3 (names), WH4 only if invoked via hints.

**Move:** pointer to the centre of the clipped pane rectangle (a visible
point inside the pane; if the centre is covered by a popup or another pane,
hit-test via the pattern in [status/discovery.py](../status/discovery.py) and
report rather than pick a different point silently). Reuse
`labels.mouse_move` behavior for scaling and multi-display.

**Focus:** measure, per fixture, which supported mechanisms work: writing
`AXFocused` on the pane (known unreliable), focusing its first focusable
descendant, focusing a table/outline/web area directly, and (only if
approved, because it changes UI state) a click on an inert point. Success is
verified by *effect*, not by reading `AXFocused`: send a navigation key (e.g.
Down/Page Down) and observe scroll position or selected row change **only in
the targeted pane**, then restore. Use throwaway or read-only content (a
folder list, not message actions); never use keys that act on messages.

**Validation criteria**
- Move: pointer lands inside the pane rectangle for every ground-truth pane in
  F1, F2, F4, F6, on primary and secondary displays and with a scaled display;
  original pointer position is restorable.
- Focus: table of mechanism x fixture with pass/fail/unsupported. A mechanism
  is "pass" only if the key-effect test changes state in the target pane and
  not elsewhere, 5/5 runs.
- Negative cases: collapsed/absent pane, ambiguous name, pane covered by a
  popup, inaccessible window: each yields a notification and no mouse move or
  focus change.
- No application state is modified (selection/scroll restored; no messages
  opened or marked read). Document anything that cannot be restored.
- Applications where focus cannot be set reliably are listed as unsupported
  rather than given a click fallback.

**Done when:** `move to` and `focus` each have a verified mechanism or a
documented unsupported status per fixture.

## WH6. `number <pane>`: scoped application numbers

**Effort:** M. **Depends on:** WH3; N8 method and N12/N12c scope decisions.

Use the pane's AX element (or its frame as a surface clip, per N12c) as the
collection root, then reuse the production label session. Compare to the
full-window baseline from N2 on F1 (`number tools`, `number mail`) and F4.

**Validation criteria**
- Equivalence: the scoped set equals the full-window set filtered by
  containment in the pane rectangle (same frames, no extras; list differences).
  For `number tools` on F1 the labelled set contains Mail, Calendar,
  Contacts, ..., OneDrive, More (names recorded by hand) and nothing from other
  panes.
- Required controls: no control that a human sees in the pane is missing;
  every omission is classified (no AX node / hidden / zero frame / timeout).
- Cost: query + render time scoped vs full-window; if the pane lookup itself
  needs a full-window query, report both and total interaction cost
  (select pane, then control). No promise of a speed-up.
- Failure: unknown name, ambiguous name, pane no longer present, pane
  re-created after a refresh: explicit error, session stopped, no stale number
  activates an old control (extend the stale-window tests).
- Returning to full-window scope is a single, documented command; `hide
  numbers` clears everything.
- Handoff: number selection, back, hide and menu labels behave as in N7.
- No label cap that silently drops controls.

**Done when:** one app shows clutter reduction on the primary fixture without
losing required controls and failure cases are tested.

## WH7. Per-application configuration (approval-gated)

**Effort:** M. **Depends on:** WH1 (selectors), WH3 (names), N4 capability
table. **Approval gate:** persisted format / new extension mechanism.

First produce a capability/gap table (as N4): can Talon context settings,
AxKit overrides, or a Talon list expressed per-app solve this without new
code? Only if not, propose a minimal schema: pane name -> selector by role +
semantic attribute (title/description/identifier/subrole) + optional ordinal
among siblings, bound to a bundle ID in a **context or data file, not
branches in core code**. No child-index paths, no persisted AX identities,
no auto-learned profiles. Prototype one config for Outlook (F1-F3).

**Validation criteria**
- The Outlook config yields exactly the ground-truth pane set on F1, F2, F3
  (WH0 score = 1.0) across relaunch and resize; with the config deleted, the
  command falls back to WH8 behavior or errors visibly.
- A config for app A does not affect app B (tested with a second bundle).
- Malformed config (bad schema, unknown key, duplicate names, no match,
  multiple matches) produces a clear notification; nothing loads partially.
- App update resilience: document which selector attributes broke on the
  tested version change, or state that only one version was available.
- Maintenance cost is written down (lines of code, files, per-app effort) and
  approved before generalizing to a second application.
- Core traversal code contains no bundle IDs or app names (grep check in
  tests).

**Done when:** one configured app works end-to-end, and the maintenance cost
is approved or the mechanism is rejected in favor of existing settings.

## WH8. Automatic labelling fallback

**Effort:** M. **Depends on:** WH1, WH2, WH3. Independent of WH7.

For apps with no configuration, apply the best WH1 rule with ordinal/role
names (`pane one`, `sidebar`). Opt-in only, labelled as automatic in the
notification. Evaluate on F1-F8 with their configs hidden.

**Validation criteria**
- Precision/recall against WH0 per fixture, reported separately for configured
  apps with config ignored and for F8 (never configured). Acceptable bar to
  propose promotion: recall >= 0.8 and precision >= 0.8 on at least 5 of 8
  fixtures; otherwise record "needs configuration".
- Failure modes are explicit: single-pane window says so; > N panes (proposed
  12) reports "too many" instead of truncating silently; empty AX tree reports
  activation status.
- Auto names never collide within a window; collision handling tested.
- Never auto-selects a "best guess" pane for `move to`/`focus`/`number` when
  the name is ambiguous.

**Done when:** a go/no-go with numbers per fixture exists.

## WH9. Command grammar, overlap, and promotion decision

**Effort:** S. **Depends on:** WH3, WH5, WH6 (and WH7/WH8 outcome).

Draft `.talon` files with the gating tag (as in
[inventory_active.talon](../accessibility/inventory_active.talon)) and
check overlap with existing `move mouse`, `show numbers`, `focus`, Community
window and mouse commands.

**Validation criteria**
- Command-inventory/overlap tests report no unintended collisions; each new
  phrase is listed with the context where it is active.
- `node scripts/lint_talon.mjs` passes on the new `.talon` files; `uv run
  ruff check` and `ruff format --check` pass on new Python; relevant
  `unittest` modules pass.
- Live voice test: each command recognized 5/5 in a normal speaking cadence
  (including pane names like `tools`, `inboxes`), none misfired in the
  dictation mode.
- Reload and sleep/wake leave no hint or numbers session behind.
- Written decision per command: promote, keep as spike, or drop, with
  maintenance cost; promotion into production code is a separate approved task.

---

## Dependency order

```text
WH0 -> WH1 -> WH3 -> WH6 -> WH9
WH2 (parallel with WH1) -> WH4 -> WH5 -> WH9
WH1 + WH3 -> WH7 (approval gate) ; WH1 + WH2 + WH3 -> WH8
```

Suggested first spikes: **WH0 and WH2** (no live risk), then **WH1** on
Outlook F1.

## Open questions for the user

1. Nested panes: should `number tools` select the outermost container only, or
   should sub-panes (e.g. a toolbar inside the message pane) also be addressable?
2. Is the rule under each hint required, or is text-only acceptable if it needs
   a custom canvas?
3. Should hints stay visible after a command, or clear after one use (as
   application numbers do)?
4. Is pane focus by key-effect validation acceptable on your Outlook data, or
   should destructive-looking panes (message list) be tested only in a scratch
   mailbox?

---

## Experiment log

### 2026-11-05: first experiment (WH2 core, offline WH1, live WH4/WH5 stub)

**Built (all isolated, removable):**

| File | Role |
|---|---|
| [window_hints_spike_core.py](../window_hints/core.py) | Pure: rect validation/clipping, three candidate rules (`structural`, `named`, `sized`), ordering, hint anchor + underline, overlap check, IoU scoring (WH0/WH2) |
| [test_window_hints_spike.py](../tests/test_window_hints_core.py) | 25 tests: clipping, negative/multi-display coordinates, NaN/inf/zero frames, shuffled-order stability, duplicate frames, anchors, scoring (perfect/missing/extra/split) |
| [window_hints_probe.py](../scripts/window_hints_probe.py) | Offline WH1 on saved `ax-trees/*.json`; prints roles, frames and name presence only |
| [window_hints_spike.py](../window_hints/window_hints.py) / [.talon](../window_hints/window_hints.talon) | Live: walks the focused window with the existing `collect()` and `focused_surfaces()`, labels pane elements with the existing `labels.show` / `labels.show_names` |

**Reused:** `collect`/`Node` (walk), `focused_surfaces` (root), `labels.*`
actions and the `labels.controls_active` tag (so "move mouse to N" and
"hide labels" already work on pane labels with no new session code).
**Not built:** canvas, underline, refresh, config, focus, scoped numbers.

**Verification run:** ruff check/format, `lint_talon.mjs`, full suite
(444 OK), Talon loaded the new files without errors, no phrase collisions.

**Offline WH1 findings (saved snapshots, fixtures not hand-scored yet):**

- Slack (787 nodes): `named` and `structural` both find 7 panes: header
  toolbar, left rail (`AXTabGroup`), sidebar (`AXOutline`), two toolbars,
  composer toolbar. The conversation pane is **not** found: it is plain
  `AXGroup`s inside the single `AXWebArea`, so role rules cannot see it.
  Likely needs the "largest uncovered rectangle" or per-app config (WH7).
- Word (142 nodes): ribbon tab group, split group, scroll areas found; the
  split group's own `AXTitle` is empty but a nested one is named. `named`
  drops the unnamed toolbar. The document area is an `AXScrollArea`/
  `AXLayoutArea` under the split group.
- Pane roles alone are therefore useful for native split-view apps and
  insufficient for web-view apps. This supports configuring web apps and
  using automatic rules only as a fallback.
- Hint width matters: a 60 px sidebar next to its neighbour collides with an
  80 px hint (tested). WH4 should keep hints at or below about 50 px wide or
  place them per pane.

**Not yet verified (needs you):** the live commands were loaded but not
spoken. Protocol, per fixture F1 (Outlook), F4 (Slack), F5 (Word):

1. Say `window hints`. Expect labels on panes, no crash; the Talon log shows
   `Window hints: rule=... panes=N` and per-pane frames.
2. Say `window hint numbers`, then `move mouse to 2`. Pointer should land in
   pane 2's top-left area (note whether it is the pane's corner or centre).
3. Say `hide labels`. Confirm nothing remains. Then switch app and window
   while labels are shown, and record what stays behind (no refresh exists).
4. Hand-record the pane rectangles from a screenshot and score with
   `core.score` to close WH0 for that fixture.
5. Record: number of panes, missing panes, wrong panes, time to labels.

**Next decision:** after step 4 on Outlook, choose between (a) per-app config
for web-view apps (WH7) or (b) a heuristic for uncovered regions, then WH6
scoped `number <pane>`.

### 2026-11-05: declarative pane profiles (replaces the VS Code module)

**Correction.** The first VS Code attempt was a VS Code-specific Python module
with a hard-coded grid walk and marker table. That was an application adapter
added without asking (principles 2 and 7) and was **deleted**. It also switched
to numbered labels without saying so and was reported from a log line, not
from the screen.

**Replacement.** One generic matcher,
[window_hints_profile.py](../window_hints/profiles.py), driven by
data. The VS Code profile is
[window_hints_profiles/vscode.json](../window_hints/profiles/vscode.json),
selected by `user.window_hints_profile = "vscode"` in
[window_hints_vscode.talon](../window_hints/vscode.talon). Core
code contains no application names (a test greps for them).

Schema: `panes` (ordered; the number is the pane's position in this list),
each with `name`, `match` (role, subrole, dom_id, title, description exact;
`classes` all present; `class_suffix`), optional `scope` (`"self"` or
`{"ancestor": matcher}`, nearest ancestor wins, so a marker deep in a pane
resolves to the pane's cell), optional `max_depth` (ignores deeper nodes; it
filters, it does not yet shorten the walk), and `tiles` (report overlaps and
window coverage). Unknown keys, empty matchers, duplicate names, bad depths
and bad profile names are explicit errors (tested).

**Evidence (live, VS Code, explorer + editor + chat, no panel):**

- 6 panes, coverage 1.000, 0 overlaps; walk 0.36 s, matching 0.06 s.
- Screenshot after drawing: number badges 1-6 appear on the title bar,
  activity bar, sidebar, editor, chat and status bar. The badge sits at the
  pane **centre** (not the top-left), and the title bar badge lands in the macOS
  menu bar row, above the window.
- Names mode on the same elements shows "Group 3", "Group 4", ...: Talon's
  fallback for untitled elements.

**Limits found.**

- `labels.show` (numbers) accepts rectangles, `labels.show_names` accepts
  elements only, and no `labels` action accepts custom text. Profile names are
  therefore not drawn; they appear in a notification and the Talon log. Drawing
  them needs a custom canvas, which is a principle-7 decision (open question).
- The `panel` marker is still unverified live (no panel was open).

**Generic fallback bugs fixed:** `window hints all` could drop a pane that
`window hints` showed (an unnamed outer container beat a named inner one with
the same frame). Named now wins, then outermost; a regression test asserts
`structural` is a superset of `named`. The redundant `sized` rule and
`window hints large` command were removed.

**Tests:** [test_window_hints_profile.py](../tests/test_window_hints_profile.py)
(21: real sanitized [fixture](../tests/fixtures/vscode_grid.json), moved
sidebar, bottom panel, hidden/zero-size cells, shuffled nodes, unknown part not
guessed, tiling failure, generic matcher, scope, depth, schema rejection) and
[test_window_hints_spike.py](../tests/test_window_hints_core.py).

**Still needs you (durability on moving panes):** run `window hints` in VS Code
after (1) moving the sidebar right, (2) opening the bottom panel, (3) hiding
the activity bar, (4) dragging a sash, (5) relaunching. Read the Talon log line
`Window hints (profile vscode): panes=N coverage=... overlaps=[]`; coverage
should stay 1.000 and names should not change.

**Open decision:** how to show profile names: (a) numbers + notification
(current), (b) a small text-label canvas (about 30 lines, new lifecycle to
clean up, needs your approval), (c) give up custom names and use generic AX
names only.

### 2026-11-05: centred named Element proxies (supersedes names limitation above)

**Approved experiment:** retain Talon's labels, use small centre targets, and
route actions to the original group. No custom canvas or native AX writes.

An ordinary duck-typed object is rejected by `labels.show_names`, but a
`ui.Element` subclass is accepted. A live instrumented probe showed the
renderer requesting `AXTitle`, `AXPosition` and `AXSize`, not `AXFrame`.
Overriding these attributes drew custom text at a supplied 12x12 target.
`AXSize` must be a `Size2d`; `Rect.size` is a point, not that type.
The earlier claim that custom labels required a canvas was incorrect.

**Built:** isolated [window_hints_label_spike.py](../window_hints/labels.py).
It owns a copied original element, uses its private `_ref` to construct the
subclass, reports the profile name and current group-centre geometry, and
delegates `perform()` to the original. Other attributes, including role and
available actions, come from the original group. No fake `AXPress` support
is advertised. The private reference API is an explicit compatibility risk.

If custom geometry construction fails, log and notify once per proxy and use
the group's original geometry. If proxy construction or synchronous rendering
fails, log and notify, clear labels and retry with the original elements.
Failure of that retry is propagated to the command's error notification.
Errors occurring later inside Talon's renderer are not covered by this
synchronous fallback.

The active [named profile](../window_hints/profiles/vscode_named.json)
now targets activity bar, sidebar, editor tabs, editor, optional panel and
secondary sidebar (named `chat` for this layout). Layout cells are resolved
with the existing ancestor scope; tabs target themselves. This removes both
Active View Switcher matches and the Chat actions toolbar, labels the full
secondary sidebar, and permits custom names instead of Group/TabGroup.
The secondary sidebar can host views other than Chat; `chat` is a configured
name, not a content detector. Editor remains the whole editor part; split
editor groups have not been independently named or live-tested.

**Live validation, current VS Code layout:**

- Five labels visible together in a screenshot: activity bar, sidebar, tabs,
  editor, chat. No hidden label and no Active View Switcher 2.
- `labels.mouse_move(name)` reached all five group centres within one logical
  pixel. Waited 0.5s for mouse animation before reading position, then
  restored the pointer and hid labels.
- `proxy.perform("AXScrollToVisible")` succeeded on the real activity-bar
  group. Unit test also verifies exact original-reference action routing.
- **Selection is unsupported for this group:** `labels.select("activity bar")`
  raised `RuntimeError: The labeled element does not support AXPress.`
  The original layout group exposes AXScrollToVisible and AXShowMenu, not
  AXPress. This is not a custom-area failure; falling back to the same group
  cannot add AXPress. No click/focus fallback was added. WH5 focus validation
  is still outstanding; rendering must not be reported as successful focus.
- Coverage 0.951; tabs intentionally overlap the editor. This profile does
  not request tiling (title and status bars omitted).

**Automated:** six [proxy tests](../tests/test_window_hints_labels.py) cover
custom text/geometry without native mutation, real-reference actions, moving
and negative-coordinate frames, geometry fallback, renderer fallback and
fallback error propagation. Full suite: 471 tests passed.

### 2026-11-05: restore sections, split editors and spoken duplicate names

The centre-label change also replaced the earlier targets with whole layout
cells. That unnecessarily merged the two activity-bar sections and dropped
the top search target. This was a selector regression, not a requirement of
the proxy.

Updated the active named profile:

- `search`: the Open Quick Access button itself.
- `activity bar`: the Active View Switcher inside a vertical monaco-action-bar,
  resolving to that bar rather than the whole outer cell. The chat switcher
  has no matching ancestor, so is excluded.
- `manage`: the separate Manage toolbar itself.
- `files`: renamed sidebar; keeps the same layout-cell scope.
- `tabs`: each tabs-container itself.
- `editor`: each editor-instance itself, not workbench.parts.editor. This
  resolves both visible code editors in the user's split layout independently.
- `panel` and `chat`: unchanged. Non-code editor kinds (diffs, webviews,
  notebooks) still require live checks; do not assume editor-instance covers
  all of them.

**Recognition failure reproduced:** Talon's `labels.target` rule is
`<number> | {labels.names}`. A numeric suffix in its names list is literal text:
`tabs 2` does not match the words `tabs two` as one label. In a live
`actions.mimic("hover tabs two")` comparison, the numeric version failed with
`ValueError: Unknown label: 2`; spelling the suffix as `tabs two` moved to the
second tab strip. The proxy now spells numeric suffixes in its title and
description. Displayed and spoken names agree; pure profile diagnostics still
use numeric suffixes. No global capture or mouse command was modified.

**Verified:** screenshot shows all nine labels together (search, activity bar,
manage, files, tabs, tabs two, editor, editor two, chat). Replayed `hover` plus
each displayed name through Talon's actual command grammar: all nine mouse
destinations were within one logical pixel of their respective centres.
Pointer restored and labels hidden afterward. This validates recognition and
hover, not microphone accuracy or AXPress/focus on non-pressable groups.

**Tests:** named-profile regression covers separate rail sections, exclusion
of the chat switcher, search, files, two tab strips, two editors and translated
layout coordinates. Proxy tests cover spoken suffixes (two, twelve, twenty
one, one hundred, one hundred two, one thousand).
Full suite: 473 tests passed; changed Python files pass Ruff and formatting.

### 2026-11-05: number every member of repeated pane names

When a profile entry resolves to multiple distinct frames, all members now
get suffixes, including the first: `tabs one`, `tabs two`, `editor one`,
`editor two`. A single match stays `tabs` or `editor`. Duplicate markers for
the same frame still collapse before counting, so they do not cause a
singleton to acquire a suffix. Profile diagnostics retain digit suffixes;
the existing proxy converts them to spoken words for display and recognition.
Regression tests cover both multiple matches and duplicate-frame singletons.

### 2026-11-05: accepted feature and directory promotion

User accepted pane labelling and approved a top-level `window_hints/` directory.
Active Python modules, Talon files and profiles moved there; active code and
test names no longer use `spike`. Updated imports, the offline probe and
documentation links. Historical file names above describe the experiments;
their links point to current implementations.

Current behavior and compatibility limits are documented in
[window_hints/README.md](../window_hints/README.md). No other accessibility
subsystems were reorganized. A future split of the remaining directory should
be a separate change with its own import and live-reload checks.

Validation after the move: 473 tests passed, Ruff check/format passed, Talon
file lint passed. The real `window_hints_show` action hot-reloaded successfully
and rendered all seven expected names in the current single-editor VS Code
layout, with no suffix on the singleton tabs/editor. Labels were hidden after
the check. The prior split-layout command validation remains recorded above.
