# Application numbers and menu navigation backlog

Follow the [project principles and handoff](README.md). Keep generic behavior
as the default; mouse-centered discovery has a [separate backlog](mouse-ax.md).

**Current priority:** speed **and grouping** for show numbers. Existing
Community Slack commands complement grouping; opening a channel is not the
same task as restricting labels to a pane. N8 makes that distinction explicit.

## N1. Validate the existing VS Code depth-13 setting

**Priority:** High.

The override is in
[inventory_vscode.talon](../accessibility/inventory_vscode.talon).
Earlier measurements:

| Maximum depth | Median query time | Result count | Notes |
|---:|---:|---:|---|
| 12 | about 21 ms | 6 | Too shallow |
| 13 | about 130 ms | 377 | Large AX boundary |
| 16 | about 746 ms | 385 | Only eight more results |
| Unlimited, 1-second timeout | about 1.05 s | 437-438 | Production-equivalent timeout |
| Unlimited, 3-second timeout | about 2.04 s | about 502 | More role variety |

**Correction (2026-10-30):** these historical counts did not identify which
webview owned the matches and do not justify depth 13. Live inspection now
finds separate AX webviews for the VS Code workbench and the Slack report
page. Report buttons are close to their web root; real workbench controls are
inside many more nested groups. A shallow cutoff therefore retains report
buttons while omitting important application controls. Depth is not a measure
of a control's importance or whether it belongs to application chrome.

The historical 377 matches could be consistent with 374 report buttons plus
three native window buttons, but the original screen state is not established.
Do not present that historical attribution as proven. After the approved N10
checks below, VS Code now uses unlimited depth and a 3-second query budget.
Other applications retain the generic unlimited depth and 1-second budget.

Test editor tabs, activity bar, tree rows, terminal, command palette, dialogs,
settings, and source control. Record missing important controls and perceived
latency; determine whether particular surfaces justify another depth.

**Done when:** normal voice-navigation controls and known omissions are
documented. Keep overrides in Talon context settings, not Python bundle branches.

## N2. Measure query, filtering, and rendering separately

**Priority:** High after N1.

An earlier full show action took about 1.7 seconds for roughly 377 labels.
A dynamic depth-13 VS Code sample had 382 results: none explicitly hidden,
259 usable frames inside the focused window/screen, 123 missing/invalid/
non-positive frames, 213 unique valid frames, and 76 nodes in duplicate-frame
groups. Those unclassified historical results do not establish the performance
of useful VS Code controls. `visible_only=True` is not strict visual visibility.

### Read-only measurements, 2026-10-30

The focused window currently exposes three distinct AX webviews: two instances
of the same Slack report URL and the VS Code workbench. A shallow walk found
them after 16 nodes in 2.64 ms. This is the current layout, not a reconstruction
of yesterday's exact tree.

| Query scope | Visibility pruning | Matches | Wall time |
|---|---|---:|---:|
| Focused window, unlimited depth | On | 989 | 2.879 s, 2.894 s |
| Focused window, unlimited depth | Off | 994 | 1.047 s, 1.050 s |
| Workbench webview only, unlimited depth | On | 238 | 1.207 s |
| Workbench webview only, unlimited depth | Off | 243 | 0.430 s |
| Each report webview, unlimited depth | Off | 374 each | 0.311 s, 0.307 s |
| Focused window, depth 13 | On | 756 | 0.780-0.787 s |

Full-window queries used a five-second timeout and were not at that limit.
Disabling pruning is a diagnostic comparison, not a proposed production change:
it saves about 1.84 seconds here, but leaves visibility to be checked another
way. Both full-window modes include the hidden reports.

A separate bounded manual traversal, without visibility pruning or production
filters, measured the public API operations explicitly:

| Subtree | Visited nodes / child-list reads | Matching elements | Child-list retrieval | Action retrieval | Position reads | Total |
|---|---:|---:|---:|---:|---:|---:|
| One report | 994 | 374 | 116 ms | 94 ms | 15 ms | 228 ms |
| Workbench | 1,421 | 243 | 171 ms | 131 ms | 11 ms | 317 ms |

The two report subtrees plus the workbench contain 3,409 nodes, not merely the
991 matching elements; the three native window buttons bring the whole-window
match count to 994. The manual walk reads `AXChildren` once per visited node,
actions once per node, and `AXPosition` only on pressable nodes. These are counts
of public API accesses, **not proven counts of macOS IPC round trips**. The
manual walk is an experiment, not a replacement implementation.

For the then-current depth-13 production filtering, an instrumented pass measured:

| Stage | Time / count |
|---|---|
| Read focused window | 0.32 ms |
| Query | 780 ms / 756 matches |
| Read roles | 26 ms / 756 reads |
| Read enabled state | 23 ms / 751 reads |
| Read hidden state | 24 ms / 751 reads |
| Validate frames | 30 ms / 751 checks |
| Equality deduplication | 67 ms / 183,921 comparisons |
| Build refresh signature | 101 ms / 607 retained targets |
| Iterate the already-returned Python list only | 0.018 ms |

Instrumentation adds overhead. A separate direct `_controls()` call took
902 ms including its query/filtering, followed by 102 ms for `_signature()`;
do not add the query row to that inclusive collection time. Activation writes
and overlay drawing were not timed in these read-only probes. None of these
depth-limited timings establishes correct control coverage.

The installed Talon query implementation is not readable source. Runtime
profiling exposes attribute access, action retrieval, decoding and visibility
pruning, but does not separate application processing, IPC/waiting, and Talon's
bridge overhead. Exact internal attribute/IPC counts and render cost remain
unmeasured; do not claim the entire delay is VS Code returning a single tree.

**What `visible_only` pruning does (profiled 2026-10-30, workbench subtree):**
`prune_visible` never calls `ui.element_at`; it is not hit-testing. Compared
with the same query unpruned, it adds about 20,000 Python-level element
attribute reads (23,366 vs 3,331) and 18,042 `skia.Rect.intersect` calls for
about 1,070 visited nodes. Child-list reads (1,035 vs 1,111) and action reads
(1,072 vs 1,110) are similar in both modes. Measured: in this profile the extra
cost is attribute reads plus rectangle intersections, and no hit-testing ran.
Measured separately: with pruning on, the covered report webviews were still
returned (374 matches each).

*Hypothesis, not proven:* that pruning decides visibility only from frame
geometry, and that this is why a covered webview survives. The profile counts
calls; it does not show which attributes were read or what decided each
exclusion. Pruning could also use attributes such as `AXHidden`,
`AXVisibleChildren` or scroll-area clipping. Also unproven: whether ancestor
frames are re-read for each node. `sys.setprofile` raises `RuntimeError` inside
Talon, so per-attribute logging failed. N11 must settle these before any spike
relies on them.

**Done when:** repeatable query/filter/render timings, counts, and user-visible
omissions are recorded for Slack, Firefox, VS Code, Word, and one native macOS
app. Do not conclude that rendering dominates from total time alone.

## N3. Compare one reversible label filter at a time

**Depends on:** N2.

Independently test unusable-frame exclusion, exact-frame deduplication (which
semantic control survives?), and element-equality deduplication. Retest the N2
app matrix and compare required controls as well as time.

**Corrected finding:** the labels over editor text belong to an occluded
embedded HTML report, not fake Slack controls or ordinary editor text being
misclassified as buttons. Its diagram is deliberately built from HTML buttons;
the click handler updates the report inspector. Titles such as `message pane`
name the Slack element depicted by a report button. Small/clipped frames alone
do not establish that these are semantically invalid buttons.

Production rejects missing/non-finite/non-positive frames and explicitly
hidden controls. That does not reject the covered report: its webview reports
`AXHidden=False`, its button is included in `AXVisibleChildren`, and Talon's
visibility-pruned query still returns its 374 matches. Positive geometry and
provider visibility flags do not establish that a target is unobscured.

Regression tests cover the existing frame filter and preservation of distinct
overlapping controls; exact-frame deduplication remains unimplemented because
shared coordinates do not prove semantic duplication. See
[N9](#n9-validate-vs-code-target-identity-and-activation) for hit-test evidence.
Do not blacklist report titles or app bundle IDs to hide this scope/visibility
problem.

**Done when:** retain/reject evidence exists for each filter. Do not ship a
speed improvement that drops needed controls or import debug traversal into
production labeling.

## N9. Validate VS Code target identity and activation

**Priority:** High. **Depends on:** N2 baseline; do alongside N3.
**Effort:** S-M for generic visibility validation and implementation; spoken
selection still needs its own small live check.

**Established:** the unexpected targets belong to the Slack HTML report inside
VS Code. Its shallow button branch survives the depth-13 limit while deeper
workbench controls are omitted. Current read-only inspection identifies the
report URL in the targets' AX ancestry. Both report webviews say
`AXHidden=False`; a report button also appears in its parent's
`AXVisibleChildren`.

At five points per report webview (center plus four inset corners), global
`ui.element_at()` matched that webview or its descendants **0/5** times for
each report. At a report button center it instead resolved to the workbench.
A known visible workbench button resolved to itself or a descendant. The
workbench webview matched **3/5** sampled points, so requiring every point to
match would incorrectly reject even that visible branch. Fifteen hit tests
plus ancestry checks took about 72 ms in total.

**Next:** validate a generic branch-level occlusion check before descending
into embedded content. Reuse the hit-test/ancestor pattern already present in
[the status-label visibility helper](../status/status_labels.py); do not copy
it blindly because a sampled
center can be covered while another part of a view remains visible. Cover
partially visible views, overlays/dialogs, multiple webviews, scrolling, and
native controls. Five misses support this case but do not prove arbitrary
subtrees are entirely invisible. Compare correctness and cost against
per-target checks and the native query before choosing an implementation.

**Still unverified:** the user's spoken 69 dispatch. A direct `AXPress` test
reported in the earlier investigation is not proof that the voice grammar
selected the label. Retest a clearly identified harmless visible control
through the spoken command; do not use an ambiguous covered target.

**Done when:** covered branches are excluded without losing visible controls,
the depth cap no longer silently determines coverage, a known safe control is
clearly labeled and activated by its spoken number, and timings include
query/filter/signature/render. Preserve generic traversal; no app-specific
Python branches or title blacklist.

## N4. Inventory application-profile mechanisms before designing new ones

**Priority:** Exploration requested; no adapter framework yet.

Compare existing Talon context settings, AxKit overrides, menu title labels,
and generic number traversal. Use Slack as the first bounded example.
Identify which needs are already expressible: depth, query scope, exclusions,
ordering, and meaningful section names.

**Done when:** a small capability/gap table identifies supported extension
points and the maintenance cost of missing ones. App-specific profiles should
override generic defaults only in a matching context; core traversal stays
application-independent. Snapshot child-index routes are not persistent IDs.

## N5. Prototype one Slack traversal-profile override

**Depends on:** N4; approve any new extension mechanism before implementation.

Choose one measured traversal problem, not a whole-app model. Apply the smallest
existing setting/override that fixes it; if none exists, propose a minimal seam
before adding it. Record generic/profile result differences, timing, omissions,
and behavior when the profile is disabled or encounters an unfamiliar surface.

**Done when:** one isolated, removable override has evidence of improvement,
explicit unsupported/error behavior, and no effect on other apps. No automatic
profile learning or persisted AX node identities.

## N6. Probe named section labels separately from traversal tuning

**Depends on:** N4; N5 is not a prerequisite.

Try naming one Slack section through existing title-label/action mechanisms.
Establish whether the section is actionable, a navigation scope, or only a
structural group. Evaluate stable semantic attributes, duplicate names, app
updates, missing sections, and interaction with number/menu selection.

**Done when:** one name maps unambiguously to a validated live section, or the
limitations are documented. Do not invent a persistent snapshot-path selector
or silently select a different node. Generalizing to more apps is a new spike.

## N7. Verify application-number/menu session handoff

**Depends on:** no new feature.

Check expanded controls, native menus, back/hide, switching between application
and menu labels, and command precedence against generic `show numbers`.
Use [menu navigation](../menus/menu_labels.py) and the existing shared
[label wrapper](../lib/labels.py) before creating another session abstraction.

**Done when:** ownership of tags/labels and cleanup are tested, command overlap
is documented, and no stale number can activate an old control after a surface
change. Mocked coverage for tag ownership, reload, and stale-window rejection exists in
[test_accessibility_runtime.py](../tests/test_accessibility_runtime.py); see the
[audit](accessibility-audit.md) for what still needs live checks.

## N8. Compare one grouped-number scope with the full-window result

**Priority:** High alongside N1/N2. **Depends on:** N4 for available scope
mechanisms; capture the N2 full-window baseline first. **Effort:** S-M.

Choose one pane in one app (e.g. Slack sidebar versus conversation).
Compare full-window labels with labels restricted to that pane, recording
query time, render time, count, missing controls, and the total interaction
cost of selecting the group then a control. Evaluate existing semantic
attributes; do not persist child-index paths from snapshots.

**Done when:** one removable grouped scope demonstrably reduces clutter
without losing required controls; group-not-found and multiple-match cases
fail explicitly; returning to full-window scope is clear. If selecting a pane
requires a full tree query first, report that cost rather than promising a
speed-up. Choosing between named panes and a generic group picker requires a
separate UX decision; no arbitrary label cap that silently drops controls.

## Scoped-collection and deduplication plan (N10-N16)

**Goal:** fewer, correct labels, collected faster, while this repository owns
as little code as possible. Each spike is read-only unless stated, records its
measurements in its own section, and stops at a decision. Nothing is
implemented until its spike proves both correctness and a benefit.

**Method rules.** Every claim is backed by a measurement on a recorded screen
state. Fixtures are labelled as fixtures, not as general results. A spike that
cannot establish its question reports that it is unresolved; it does not
fall back to a plausible explanation.

**Dependency order:** N10 → (N11, N12, N13 in any order) → N14 → N15 → N16.

### N10. Ground-truth fixture states and a repeatable probe

**Status:** N10a and approved N10b layouts executed 2026-10-30. Selected N10c
functional checks executed; remaining activation/voice gaps are listed below.
**Effort:** S for N10a; layout and activation checks are separate small spikes.
**Prerequisite for later optimization spikes:** the applicable control/state
baseline, not merely a raw count.

#### Required-control catalogue

These are coverage requirements, not a requirement to show every control in
every layout. Exact accessible names and availability must be discovered.

| Surface | User-required controls |
|---|---|
| Activity bar | Explorer, Source Control, Extensions, Accounts, Manage |
| Explorer | Expand/collapse a directory such as `notebook`; open a file such as `uv.lock` |
| Editor | Tabs, editable text area, overflow menu |
| Bottom panel | Current terminal input, new terminal, terminal-instance switching, hide panel |
| Chat | Show/hide sessions, input area, agent picker, conversation area, scroll to bottom when available, new session, existing sessions |

`notebook` and `uv.lock` are examples to verify in the target project, not
assumed existing fixtures. Conditional controls such as scroll-to-bottom are
recorded as unavailable when their prerequisite state is absent; that is not
proof that traversal missed them.

#### N10a. Read-only baseline in the existing mokuro layout

**Goal:** establish the available required controls, their owning AX branches,
and collection costs in one real layout before changing that layout.

**Scope:** only the other VS Code window whose project is `mokuro`. Inspect its
current layout; do not configure panes, activate controls, type, draw labels,
change settings, create terminals/sessions, or open files. The only proposed
UI changes are focusing that window for the capture and returning to the
original window afterward. No production changes.

**Steps:**

1. Enumerate VS Code windows and identify one unambiguous `mokuro` target.
   Record the original window and target window identities. If identification
   is absent or ambiguous, stop rather than choose by application alone.
2. Focus the target and verify its stable UI window identity and AX focused
   window. Check both before every capture/batch. Stop and discard an affected
   capture if focus or window identity changes; never continue on this chat's
   window or repeatedly take focus back from the user.
3. Keep one temporary probe and private outputs in the session workspace.
   Record the current pane/focus state without reading editor contents,
   terminal output, chat messages, or `AXValue`.
4. Capture unlimited-depth unpruned candidates, the visibility-pruned
   comparison, and the current production-filtered result. Record query
   budgets, wall times, counts and errors. Compare longer-budget captures
   and a bounded manual walk as completeness checks; agreement supports this
   fixture but is not a universal proof of completeness.
5. Map required controls currently expected to be visible to their role,
   accessible name, frame, owning webview and diagnostic path/depth. Validate
   visible expectations with the user. Record unique, ambiguous, missing,
   hidden-by-layout, conditional-unavailable and not-yet-tested separately.
   Treat center hit-tests as evidence, not definitive visibility truth.
6. Repeat the unchanged state twice. Compare control records and candidate
   counts, preserving identity ambiguities and any UI drift rather than
   silently treating names/frames/paths as persistent IDs.
7. Record results here and present a completed checklist plus findings.
   Restore the original focus only if the probe still owns the target focus;
   do not override a subsequent user focus change.

**Success criteria and evidence:**

| Criterion | Required evidence |
|---|---|
| No capture or activation in the current chat window | Target UI/AX window identities checked before and after each capture; guarded probe source |
| Required controls in this layout are accounted for | One row per catalogue item, exact state, match metadata and explicit status; user's confirmation of visible expectations |
| Repeated observations can be compared honestly | Two capture records, timings, differences, errors and unresolved identity matches |
| Query truncation is not mistaken for completeness | Budget/time records, larger-budget comparison and bounded manual-walk comparison; unresolved if they disagree |
| UI/content/settings are not modified by the probe | Read-only probe source and focus-change record; no mutating action calls |
| Production code remains untouched | Before/after repository status/diff; only approved documentation results added |

**Risks and mitigations:**

- Wrong VS Code window: exact window guards, not just bundle/PID checks.
- Long queries block speech: one bounded query at a time, no background
  refresh loop; pause between batches and stop/report incomplete evidence.
- Dynamic terminal/chat content changes counts: no content reads; record
  instability and compare known controls rather than inventing stability.
- AX names/frames are ambiguous or a center is covered: preserve ambiguity;
  no automatic activation, guessed match, or inference that a miss is hidden.
- Private metadata: outputs stay in the session workspace; summarize control
  metadata without editor text, terminal output or conversation content.

**Rollback plan:** stop the probe; return original focus only if appropriate;
remove only the specifically named temporary probe/output files if requested.
There are no pane, session, terminal, file-content or production changes to
undo. Findings may remain as documentation even if no code is adopted.

#### N10a results, 2026-10-30

**Fixture:** VS Code window id 7048 (`.gitmodules — mokuro`); the chat window
is 8919. Layout: Explorer sidebar, editor groups 1 and 2, Terminal panel with
5 terminal tabs, Chat in the secondary sidebar with Agent Sessions shown, and a
"Screen reader usage detected" notification toast. Focus guards (UI window id
and AX focused-window title) passed before and after both captures, and focus
was returned to 8919. Probe and raw JSON are kept in the session workspace,
not the repository.

| Measure | Run 1 | Run 2 |
|---|---:|---:|
| Manual walk: nodes / `AXPress`+`AXPosition` matches | 1,352 / 317 | 1,353 / 317 |
| `query_all` unpruned, unlimited depth, 10 s budget | 317 in 0.396 s | 317 in 0.399 s |
| `query_all` pruned, unlimited depth, 10 s budget | 292 in 1.349 s | 292 in 1.334 s |
| `query_all` pruned, depth 13, 1 s budget | 9 in 0.015 s | 9 in 0.016 s |
| Production `_controls(owner)` | **3** in 0.016 s | **3** in 0.016 s |

- The unpruned query and the manual walk agree exactly: every unpruned
  match was in the walk, and the counts are equal. The candidate sets of the
  two runs are identical (role, title, description, frame). The one-node
  difference in the walk did not change the matches.
- **Production is unusable in this window.** Its 3 controls are the window's
  close, minimize and full-screen buttons. Depth 13 reaches only 6 web elements
  (5 wrapper groups and the notification list) plus those 3 buttons. All 314
  workbench matches sit 8–36 levels below the
  window (15–36 for every catalogue control). This differs from the
  `talon_navigation` window, where the shallow buttons came from a covered
  report webview (N1/N9). The depth cap fails in both windows.
- Only one `AXWebArea` exists in this window: the workbench. There are no
  report webviews here.
- Pruning removed exactly 25 matches, all with a zero width or height. These
  were 18 off-screen tab close buttons and 7 collapsed chat links/checkboxes.
  It **kept** 17 other zero-size matches, including 16 zero-width tab buttons.
  So pruning is not simply "drop zero-size frames". Why it treats these
  differently is unresolved and moves to N11.
- Centre hit tests on the 292 pruned matches: 217 resolved to the element
  itself or a descendant, 58 to something else and 17 had no frame. Among the
  58: 1 px squeezed tabs, chat transcript items collapsed to 1 px height,
  splitter sashes, and chat input controls under the notification toast.
  Pruning keeps all of these.

Catalogue mapping in this layout. "Prod" is production inclusion; ✗ means
excluded by depth 13.

| Surface | Control | AX evidence (role, depth, centre hit) | Status | Prod |
|---|---|---|---|---|
| Activity bar | Explorer, Source Control, Extensions | `AXRadioButton`/`AXTabButton`, depth 20, self | unique | ✗ |
| Activity bar | Accounts, Manage | `AXPopUpButton`, depth 20, self | unique | ✗ |
| Explorer | `notebooks` directory (the user's "notebook") | `AXGroup` row with `AXPress`, depth 25, `AXExpanded=False`, self | unique | ✗ |
| Explorer | `uv.lock` | `AXGroup` row, depth 25, self | unique | ✗ |
| Editor | Visible tabs | `AXTabButton`, depth 28, self | unique per tab | ✗ |
| Editor | Scrolled-out tabs | 9 tabs at 1 px wide (hit other), 16 at 0 px; all kept by pruning | noise | ✗ |
| Editor | Text area | `AXTextArea` "`.gitmodules`, preview, Editor Group 1", depth 28, self | unique | ✗ |
| Editor | Overflow menu | `AXPopUpButton` "More Actions...", depth 30, once per editor group | ambiguous by name (2 groups) | ✗ |
| Panel | Current terminal | xterm `AXGroup`, depth 34, self; its 7×14 `AXTextField` hits other | conditional on target choice | ✗ |
| Panel | New terminal | Two nested buttons (depths 21 and 22) with the same frame | duplicate | ✗ |
| Panel | Terminal instances | 5 `AXGroup` rows in the "Terminal tabs" list, depth 32; 4 self, 1 other (unexplained) | unique | ✗ |
| Panel | Hide panel | `AXButton` "Hide Panel (⌘J)", depth 22, self | unique | ✗ |
| Chat | Hide sessions | `AXButton` "Hide Agent Sessions Sidebar", depth 22, self | unique | ✗ |
| Chat | Input | `AXTextArea` "Chat Input (Agent)…", depth 27, self | unique | ✗ |
| Chat | Agent picker | `AXPopUpButton` "Agent", depth 29, self | unique | ✗ |
| Chat | Conversation area | `AXList` "Chat", depth 23, self | unique | ✗ |
| Chat | Scroll to bottom | `AXButton` "Scroll to Bottom", depth 23, self | present (conditional) | ✗ |
| Chat | New session | "New Session" (depth 21) and "New Chat (⌘N)" (depth 19) | two controls; which one the user means is unconfirmed | ✗ |
| Chat | Existing sessions | `AXRow`/`AXOutlineRow` with only `AXScrollToVisible` and `AXShowMenu` | **missing by query definition** | ✗ |

**Findings:**

1. Production depth 13 drops every required control in an ordinary VS Code
   window. Removing or replacing the cap is necessary, not merely an
   optimisation.
2. Chat session rows cannot be found by `[AXPosition]:action(AXPress)` at any
   depth or pruning setting, because they don't advertise `AXPress`. Native
   `show numbers` uses the same query, so it misses them too. Activating a row
   would need a different mechanism (for example, a click or setting
   `AXSelected`). That is unproven and belongs to N10c.
3. Pruning is 3.4× slower than the unpruned query (1.34 s vs 0.40 s) and
   removes 25 of 317 matches. Centre hit tests flag 58 further covered or
   squeezed matches that pruning keeps. Whether hit tests are a cheaper and
   better filter is an N11/N14 question; the hit-test cost was not measured.
4. Same-frame duplicates (New Terminal; status-bar group/button pairs) and
   wrapper `AXGroup`s with `AXPress` (115 of 317 matches are `AXGroup`) inflate
   the label count. This is evidence for N14/N15, not yet a decision.

**N10a checklist:**

- [x] Identified the target window unambiguously (7048) and recorded the
      original window (8919).
- [x] Guarded both captures before and after; focus returned.
- [x] Recorded unpruned, pruned, depth-13, production and manual-walk results
      twice; all identical apart from one non-matching walk node.
- [x] Mapped every catalogue control with status and production inclusion.
- [x] Proved why session rows are absent: no `AXPress` advertised.
- [x] No activations, typing, label drawing, settings changes or production
      edits.
- [x] User confirmed "New Session" in the sessions list, the `notebooks`
      directory, notification dismissal, and the proposed layout batches.
- [ ] Unexplained items: why pruning keeps some zero-size frames; why one
      terminal row's centre hit test resolves elsewhere.

#### N10b. Layout variants, approved one small batch at a time

After N10a, propose the exact setup and restoration steps for each batch:

- Explorer versus Source Control versus Extensions active.
- Editor with surrounding panes shown versus hidden.
- Terminal/bottom panel shown versus hidden.
- Chat focused, with sessions shown versus hidden.
- Settings open and focused versus an ordinary editor tab.

Reuse N10a's evidence format. Measure only relevant controls per state, not the
Cartesian product of every panel combination. HTML preview foreground versus
background remains a separate visibility fixture for N11/N12. Settings values
must not be changed. Do not treat layout-changing permission as permission to
invoke the controls being evaluated.

#### N10c. Activation checks, separately approved after identification

Discovery does not prove that a spoken number activates a control. Propose
small functional batches after targets are unambiguous. Each plan states its
expected reversible effect, evidence and restoration steps. File opening,
directory expansion, terminal creation/switching, new chat sessions, agent
changes and session switching are not authorized by the read-only baseline.
Never close existing terminals, delete existing sessions, run shell commands,
submit prompts, or edit files as cleanup.

**Approval update:** the user approved opening/closing clean files and test
terminals; unsaved files must remain untouched. Existing terminals must still
not be closed. This does not authorize clicking Update or submitting chat.

**After each executed spike:** present a completed/pending/blocked checklist,
findings tied to capture records, and explicit limits. "No production change"
is a valid outcome; no commit is required.

**Future regression gate:** this baseline is VS Code only. Before promoting a
generic collector/filter optimization, agree on and run pre/post checks in
other affected applications. VS Code-only success is not evidence that Slack,
Firefox, Word or native macOS applications are unaffected.

#### N10b/N10c executed plan and evidence, 2026-10-30

**Goal:** validate the approved layouts and selected reversible actions in
mokuro, distinguish depth/timeout defects from other coverage gaps, and test
whether a cheap size filter can replace native pruning.

**Scope:** window 7048 only, never the chat window 8919. User-approved sidebar,
panel, chat and Settings layout changes; clean `uv.lock`, `notebooks`, and one
new test terminal. No unsaved editor, setting value, existing terminal or
session content may be changed. Update is inventory-only, not activated.

**Steps completed:** enable supported AX interfaces; capture each layout with
unpruned/pruned 10-second reference budgets and a 1-second comparison; apply
the production filters; compare element sets; verify the VS Code depth and
timeout overrides through the real collector; exercise selected controls via
the actual application-number dispatch; restore layouts, files, terminals and
focus. Diagnostic scripts and raw JSON remain in the session's `files/n10/`
directory, not production imports.

**Success criteria and evidence:**

| Criterion | Evidence / outcome |
|---|---|
| Correct target window | Every batch ended with its window guard true and returned focus to 8919 |
| Approved layout matrix captured | Explorer, Source Control, Extensions twice, terminal hidden, sessions hidden, surrounding panes hidden, Settings focused; raw captures retained |
| Production budget does not truncate the final tested states | With depth 0 / timeout 3, production matched the complete pruned-and-filtered reference counts below |
| Cheap-filter equivalence tested, not assumed | Identical filtered sets in settled ordinary layouts, but 6 additional positive-size menus in Settings without pruning |
| Reversible functions exercised | Numbered menus, editor/chat focus, panel toggle and terminal creation; direct AX directory/file actions; cleanup records. Session-sidebar restore failed to be asserted; corrected in the follow-up |
| Unsaved files and original terminals preserved | Final Explorer still reports 10 unsaved files; only probe-opened `uv.lock` closed; original terminal names 1, 2, 3, 4, 6 retained; created terminal 7 removed |
| No content read or changed | Probe reads metadata, not `AXValue`; no editor/terminal/chat text entry; no chat submission |

Final reference/production comparisons, after the VS Code override reloaded.
Times are query-only for the two reference queries, and query plus filtering
for production. Counts in the middle columns are after the existing
role/enabled/hidden/usable-frame filters.

| Layout | Unpruned query | Unpruned filtered | Pruned query | Pruned filtered | Production (3 s budget) |
|---|---:|---:|---:|---:|---:|
| Explorer, restored | 0.387 s | 142 | 1.348 s | 142 | 142 / 1.336 s |
| Source Control | 0.488 s | 162 | 1.682 s | 162 | 162 / 1.714 s |
| Extensions, run A | 0.404 s | 156 | 1.392 s | 156 | 156 / 1.425 s |
| Extensions, run B | 0.423 s | 156 | 1.404 s | 156 | 156 / 1.417 s |
| Terminal hidden | 0.356 s | 130 | 1.189 s | 130 | 130 / 1.218 s |
| Sessions hidden | 0.472 s | 145 | 1.320 s | 145 | 145 / 1.349 s |
| Settings modal focused | 0.100 s | 28 | 0.278 s | 22 | 22 / 0.288 s |

With surrounding panes hidden, the earlier 1-second production query returned
77 controls in 0.499 s, equal to the full reference result for that state.
The final ordinary layout returned 143 controls in 1.344 s (both filtered
reference sets also 143). Small differences between successive restored
fixtures are retained, not treated as persistent element identities.

**Findings:**

- **AX activation and traversal are separate.** The show action already calls
  the AX-enabling helper before collection. Live reads were
  `AXEnhancedUserInterface=True` and `AXManualAccessibility=False` before and
  after preparation. The helper's `True` result does not prove both attributes
  became true; do not make that claim. The deeper tree was available.
- **Depth was broken, and the timeout was independently incomplete.** After
  changing depth to 0, the old 1-second budget returned 133 controls versus
  142 in the restored Explorer reference. A 3-second VS Code-only budget
  returned all 142. Generic defaults are unchanged. This improves the tested
  window; it does not fix covered webviews in the other VS Code window.
- **A usable-frame check already exists.** On a 309-match Explorer capture it
  took 10.4 ms; the unpruned query took 387 ms. Native pruning alone took
  1,348 ms. The two filtered sets agreed. However, Settings exposes six
  positive-size `More Actions...` buttons (22 by 23 pixels) which native
  pruning excludes and centre hits resolve elsewhere. This repeated in the
  final Settings capture. Zero-size filtering alone cannot reproduce those
  exclusions. Native pruning remains enabled; no generic filter was relaxed.
  Their exact clipping/hidden ancestor mechanism remains N11 work.
- **Not all discovered controls are production targets.** `notebooks` and
  `uv.lock` have pressable `AXGroup` children excluded by `CONTROL_ROLES`.
  Direct AXPress expanded/collapsed `notebooks` and opened clean `uv.lock`;
  that does not prove either can be selected by an application number.
  Terminal tabs have the same group-role gap. Session rows lack `AXPress`
  altogether. Increasing depth cannot fix either class of omission.
- **Actual numbered dispatch was exercised, not just direct AXPress:**
  Accounts and Manage opened menus; Agent opened its picker; the identified
  editor-actions overflow opened a menu; editor and chat text areas gained
  focus; panel hide/show changed the layout. The sessions-sidebar hide
  was selected, but its restore was not asserted (see the follow-up below).
  New Terminal created terminal 7. These are action-dispatch checks, not
  spoken-phrase recognition tests.
- **Top controls:** superseded by the reachability follow-up below, which
  verifies the search bar, session search and notification clearing by
  number.
- **Settings is a modal editor in this installation, not an ordinary tab.**
  Its focused Search settings textarea was numbered. The identified
  `Close Modal Editor (Escape)` button closed it through numbered dispatch.
- **Terminal cleanup:** direct AXPress on the terminal context menu's Kill
  Terminal item did not remove the test terminal. After explicitly focusing
  terminal 7's input and verifying its AXTextField description, the existing
  Community `workbench.action.terminal.kill` action removed only terminal 7.
  Community terminal.focus restored terminal 4. No terminal command text was
  entered, and no existing terminal was killed.

**Risks and mitigations observed:** early probes stopped on changing accessible
names, extra same-name menus, a Settings modal instead of a tab, and terminal
groups instead of assumed rows. Those runs are retained as incomplete rather
than counted as passes. Selectors were then constrained to the observed
Explorer outline/editor toolbar/terminal list. One native pruning query also
raised `AttributeError: AXRole` during a layout transition; later settled
captures passed. This remains a collector-reliability audit item, not evidence
that all transient-tree failures are handled. No fallback query was silently
substituted.

**Rollback:** restore the previous VS Code settings (`max_depth=13`,
`timeout=1.0`) only if reverting this experiment is needed; that intentionally
restores the known coverage defect. The new timeout's generic default is 1.0.
No pruning implementation changed. The sessions sidebar was left hidden by
this run and restored in the follow-up. Notifications were cleared with
approval. No test-created file/tab or terminal remains.

**Automated validation:** 38 focused runtime/inventory tests passed under
Python 3.12. Ruff lint and formatting checks passed for the collector and
runtime tests; `git diff --check` passed. All 69 local links in the four updated
backlog documents resolved. Added tests cover configured depth forwarding,
configured timeout forwarding and invalid query-budget rejection.

**Completed/pending checklist:**

- [x] Approved layouts captured; Settings modal identified and dismissed.
- [x] Per-app depth 0 and timeout 3 verified live, with reference counts.
- [x] Size-filter speed measured; Settings counterexample preserved.
- [x] Selected numbered menu/focus/layout actions and terminal creation tested.
- [x] `notebooks` expanded/collapsed; clean `uv.lock` opened/closed.
- [x] Original five terminals and 10 unsaved files preserved; focus returned.
- [x] Search-bar activation asserted (follow-up below).
- [x] Notification centre opened and cleared by application number.
- [x] Sessions-list controls numbered; session search opened by number.
- [ ] Spoken-command recognition and full native-versus-custom comparison.
- [ ] Numbering/action policy for pressable groups and non-pressable rows.
- [ ] Existing chat-session selection, New Session creation, scroll-to-bottom,
      and agent switching (picker opening alone is not switching).
- [ ] Controlled pruning fixtures, covered-webview roots and generic regression
      checks in other applications before changing visibility policy.
- [x] Handle transient `AttributeError: AXRole` with cleanup, logging and
      notification (N12a). Its provider-side trigger remains unproven.
- [ ] Fix or document why the sessions sidebar cannot be shown below a width
      threshold (threshold itself not measured).

#### N10 reachability follow-up, 2026-10-30

**Goal:** close the open reachability items using the real
application-number dispatch (`show application numbers`, then
`labels.select(n)`), not direct `AXPress`, and correct earlier unverified
claims.

**Scope:** window 7048 only. User-approved: dismissing notifications and
showing/hiding panes. Update and New Session are checked for presence only and
never pressed. No text entry, settings, files or terminals touched. Each probe
records named `AXButton`/`AXTextField`/`AXList`/group metadata before and after
selection, plus the focused-element ancestor chain; never `AXValue`.

| Check | Number | Evidence after selection | Result |
|---|---:|---|---|
| Top search bar (Open Quick Access) | 25 | `AXTextField` and `AXList` "Search files by name…" appeared; focus inside that list. Escape removed them | pass |
| Notifications (status bar) | 10 | "Notifications Center" list opened containing a git "too many active changes" warning, Clear All, Clear Notification, Hide Notifications | pass |
| Clear All Notifications | 4 | Whole centre and warning disappeared; focus returned to the `.gitmodules` editor | pass |
| Find Agent Session (session search) | 62 | `AXTextField` "Type to search" appeared and was focused; after Escape, no "Type to search" field remained | pass |
| Sessions-list presence | — | Update 20, New Session 56, Refresh 61, Hide sidebar 63, Filter 69, Open Quick Access 25 | numbered; Update and New Session not activated |

**Corrections to the run above:**

- The earlier run's "Show Agent Sessions Sidebar" selection (#65) was logged
  but its effect was never asserted. Here the sidebar stayed hidden. Numbered
  selection, direct `AXPress` and a mouse click on that button all left only
  "Show Agent Sessions Sidebar" visible. The secondary sidebar had narrowed:
  the Chat tab was at x=1134 instead of the baseline 1113. After the sash was
  dragged back so the Chat tab returned to x=1113, the sidebar reappeared with
  no further press. Proven: in this state the button had no visible effect,
  and restoring the width restored the sidebar. Not separated: whether the
  earlier `AXPress` contributed. Not measured: the exact width threshold or
  what narrowed the sidebar.
- The earlier notification dismissal used direct `AXPress`; numbered
  dismissal is now verified above.

**Additional findings:**

- **Intermittent collector crash.** The first `show application numbers` in
  this follow-up raised `AttributeError: AXRole` from Talon's
  `prune_visible`. `ApplicationLabelSession.refresh` catches only
  `RuntimeError` and `ui.UIErr`, so the user sees no labels and no
  notification. It did not reproduce in 8 later attempts: 2 focus delays
  (0.7 s and 3 s) × (collector only, show, show again, collector only); every
  attempt returned 143 targets. Its trigger is unproven. After approval, N12a
  added the logged notification and explicit initial-failure session cleanup.
- **The AX-enabling write does not persist.** Every show logs "enabled AX
  interfaces … `AXManualAccessibility`". Reads before and after each of those
  8 attempts were `AXManualAccessibility=False` and
  `AXEnhancedUserInterface=True`. So VS Code accepts the write but reports
  `False`, and preparation repeats on every call. The deep tree was available
  regardless.

**Final state check:** no quick-input or session-search field open, no
notification toast, sessions sidebar shown, terminal rows 1, 2, 3, 4, 6
unchanged, Explorer still reports 10 unsaved files, and focus returned to 8919.

### N11. What Talon's visibility pruning decides, and what it reads

**Effort:** S. **Answers:** your question. Decides whether pruning can be
dropped, replaced, or must stay.

The current claim that pruning is "geometry only" is a **hypothesis**. Prove or
disprove it in two parts.

**Part A: what it excludes (behaviour).**

1. In each N10 state, diff the pruned and unpruned result sets by element
   equality. On 2026-10-30 the full window gave 989 pruned and 994 unpruned,
   so five elements were excluded, but nobody has inspected them.
2. For every excluded element, record its frame, its relation to the window,
   screen and nearest scroll-area frames, `AXHidden`, whether it appears in
   its parent's `AXVisibleChildren`, and a centre hit test.
3. Build controlled cases in a disposable HTML page in VS Code's browser, one
   factor at a time:
   - off-screen;
   - zero-size;
   - clipped by a scrolling parent;
   - `visibility:hidden` or `display:none`;
   - covered by another element;
   - in a background tab.

   Record whether pruning keeps or drops each case.

**Part B: what it reads (cost).**

`sys.setprofile` fails inside Talon. Use a method that changes no global
state: compare `cProfile` attribute-read counts while varying one factor at a
time. Use the same subtree at different depths, and wide versus deep subtrees
with known node counts. Fit reads per node against depth.

- If reads grow with depth, ancestor frames are probably being re-read for each
  node; confirm this before treating it as an N14 duplicated-work candidate.
- If reads stay constant, they are not.

**Done when:**

- Every Part A case has a recorded keep/drop result.
- The "geometry only" claim is either confirmed by those cases, refuted, or
  recorded as unresolved.
- Reads per node are expressed as a measured function of depth, or recorded as
  unresolved.

Do not reimplement or remove pruning in this spike.

### N12. Choose the subtree root: focused workbench, and the focused tab's webview

**Effort:** S. **Your proposal:** walk the workbench, plus the focused tab's
webview only when that tab is focused.

Prove each link instead of assuming it:

1. **Identify the workbench webview** without its URL string, which is
   VS Code-specific and violates the no-app-branch principle. Candidates:
   - It is the webview whose AX title equals the window title (observed
     once).
   - It contains `AXFocusedUIElement`.
   - It covers the largest area under hit-testing.

   Measure each candidate across the N10 states and keep only one that is
   correct in all of them.
2. **Map a tab to its webview.** Establish whether the AX tree exposes the
   link at all (for example tab title vs webview title or URL, or the
   focused element's ancestry when the preview has focus). If no attribute
   links them, record that, and fall back to the hit-test visibility from
   N9.
3. **Background tab with an open preview** must exclude the preview, and the
   foreground preview must include it.

**Done when:** a generic rule chooses the right root(s) in every N10 state,
with the measured time to choose them. A rule that needs a bundle ID or URL
check is escalated for discussion rather than adopted.

#### N12a. Covered-webview correctness fix, 2026-10-30

**Goal:** stop labeling covered report/browser controls in the actual
`talon_navigation` project window, while retaining workbench controls and
restoring browser controls when that tab is visible.

**Scope:** generic web-area ownership validation, enabled only by a VS Code
Talon setting. No app-name, URL, title or tab-name branches in production.
Root selection/traversal optimization itself remains pending. No new observer,
polling loop, persistent cache, custom overlay or file-row numbering.

**Steps completed:**

1. Capture the current project window (8919), not just mokuro (7048).
2. Compare two hit-test policies before editing production. Requiring a hit
   on the control itself rejected 37 workbench targets, including chat input.
   Requiring the hit to belong to the same nearest `AXWebArea` instead kept
   all 133 workbench controls and rejected all 604 browser controls in that
   fixture. The three native window buttons remained eligible.
3. Implement `user.accessibility_check_web_area` (default false; VS Code
   true). Cache ancestor-to-web-area relationships only within a collection.
   An empirical dictionary-key test raised `TypeError`: Talon elements are
   unhashable. Use equality rather than speculative hash-based caching.
4. Revalidate the chosen target's web-area ownership at number selection.
   A covered target is rejected with a notification; other query failures
   log the exception, stop the session and notify, including the observed
   native `AttributeError: AXRole`. Tests also exposed an initial-failure
   session leak: the labels override tag is not yet active, so native hide
   alone cannot stop it. Empty/error paths now stop the session explicitly.
5. Test the real show action with the existing browser tab covered,
   foreground, then covered again. Only the clean selected
   `inventory_vscode.talon` preview tab was switched/restored. Unsaved files
   were not selected, edited or closed.
6. Compare against longer-budget reference queries in both project windows.

**Success criteria and evidence:**

| Criterion | Observed evidence |
|---|---|
| Covered browser pages contribute no numbers | Real show: 0 browser targets before and after foreground test |
| Visible browser remains usable | Foreground: 272 browser targets; 116 workbench and 3 native targets |
| Workbench controls survive | Background restored: 133 workbench + 3 native; chat input numbered in all three states |
| Not specific to a URL/application Python branch | Ownership compares `AXWebArea` elements; only the `.talon` setting selects VS Code |
| Initial and refresh failures notify and clean up | Mocked `AttributeError("AXRole")` tests for both paths; no active session/tag remains |
| No silent catch of arbitrary hit-test errors | Only exact `No element found.` is an empty hit; other errors reach logged notification |
| Reference comparison | Settled current project: 136 reference and 136 production; settled mokuro: 141 and 141; no missing/extra |

**Measured cost:** the first equality-cached ownership probe cost 1.072 s
over 740 candidates. End-to-end show captures took 4.47 s (covered), 6.92 s
(browser foreground), 4.43 s (covered again), including preparation,
collection, label rendering and diagnostic classification. This is a
correctness improvement, not a latency improvement. N17 is the dedicated
latency follow-up.

Final repeat with the persistent 3-second query budget: covered 136 targets
(133 workbench, 3 native), foreground 377 (272 browser, 102 workbench, 3 native),
restored 136 (133 workbench, 3 native). Chat input remained numbered throughout.
Show plus diagnostic classification took 4.66 / 6.96 / 4.51 seconds. Different
foreground workbench counts between captures are retained rather than asserted
to be identical.

**Risks and mitigations:**

- A center test is not a whole-control visibility proof. Partly visible web
  controls can be excluded when their centers are covered; hidden items in the
  same web area can remain. Do not describe this as complete visibility pruning.
- A reference/production mismatch was initially suspected to be timeout
  truncation, so a 5-second budget was tried temporarily. Further investigation
  proved actual macOS Notification Center occlusion: hit-test ancestry for
  missing mokuro Update/session-search controls belonged to the system
  Notification Center, not mokuro. They returned when that overlay disappeared.
  One run excluded 14 top/right controls; the next retained all 141. Preserve
  this state difference, not a claim that those controls are permanently lost.
- Raw query budgets 10, 3, 5, 3, 10 seconds all returned exactly 1,007 candidates
  (761 after role/frame checks), in 2.60-2.73 s. The earlier mismatch cannot
  prove a new 3-second timeout defect. The temporary 5-second override was
  reverted; VS Code remains at 3 seconds. A timeout is still not a completeness
  guarantee.
- Other applications keep their existing behavior because the setting defaults
  off. Cross-app checks remain required before enabling it more broadly.

**Rollback:** set `user.accessibility_check_web_area = false` in the VS Code
context to restore previous visibility behavior (including the known covered
browser labels). The per-collection cache has no invalidation or cleanup state
after a collection. No browser tabs/files were created or closed.

**Independent re-verification, 2026-10-30 (window 8919).** Raw outputs are
in the session workspace `files/n10/`: `editor_numbering.json`,
`missing_hits*.json`, `budget_*.json`, `rejection_reason.json`,
`rejection_hits.json`. The probe selects tabs from the editor tab group that
contains the browser tab, and restored the original selected tab
(`inventory_vscode.talon, preview`; `AXSelected=True` afterwards).

| State | Shown | Browser | Workbench | Native | Same filters without the web check |
|---|---:|---:|---:|---:|---:|
| Browser tab covered | 136 (4.42 s) | 0 | 133 | 3 | 761 (625 browser) |
| Browser tab in front | 391 (6.34 s) | 272 | 116 | 3 | 744 (625 browser) |
| Covered again | 122 (4.72 s) | 0 | 119 | 3 | 761 (625 browser) |

- The browser tab has two web areas (625 controls total). In front, only the
  front one's 272 controls were numbered.
- The 14 controls missing from "covered again" were the title-bar layout
  toggles and the chat/sessions header buttons. A same-pass instrumented
  run showed only the web-area check rejected them. Their centre hit chain
  ended in `AXApplication "Notification Center"`, in a banner group titled
  "Talon, Talon sleep warnings, …". Repeated within seconds, all 14 returned
  (136 three times in a row). So this is real temporary occlusion by this
  repository's own sleep-warning notifications, not a traversal defect.
- Budget 3 s vs 10 s, steady and immediately after a tab switch: 1,007
  candidates each time, 2.60–2.70 s. No truncation observed.
- While the browser was in front, editor-only workbench controls (Find widget,
  language/line status items, the editor text area and 7 tab close buttons)
  were absent and browser toolbar controls appeared. That tab-strip change
  was not investigated further.
- Clutter that remains in the covered state: 14 `Close (⌘W)` tab buttons,
  2 `New Terminal` buttons, 2 `Toggle Chat` buttons. This is N14/N15 work.

**Checklist:**

- [x] Actual current project reproduced, not inferred from mokuro.
- [x] Re-verified with retained outputs; notification occlusion traced to
      Talon sleep-warning banners.
- [x] Covered / foreground / covered browser tested through real show action.
- [x] Workbench chat input retained; native controls unaffected.
- [x] Generic opt-in implementation and stale-selection check.
- [x] Failure notification plus initial-session cleanup tests.
- [x] Raw budget comparison and external notification-occlusion diagnosis.
- [x] 47 focused runtime/inventory tests pass with Python 3.12.13; Ruff
      lint/format, VS Code Talon syntax/format and whitespace checks pass.
- [x] Faster root selection before querying: superseded by N12b.
- [ ] Full grouping/clutter reduction, spoken recognition, and all N10 actions.

### N12b. Workbench first, then visible secondary web areas

**Status:** implemented 2026-10-30; replaces `user.accessibility_check_web_area`
with `user.accessibility_defer_web_areas` (default false, VS Code true).

**Goal:** number the VS Code workbench without walking hidden browser pages,
then append the visible browser page's controls without renumbering.

**Scope:** `accessibility/inventory.py`, the VS Code `.talon` setting, runtime
tests. No app-specific Python.

**Evidence that shaped the design (window 8919, `files/n10/tab_*.json`):**

- Under the window, the workbench and each embedded browser page are sibling
  `AXWebArea`s. The workbench's `AXTitle` equals the window's `AXTitle`.
- A browser tab's `AXDescription` is `"<page AXTitle> (<URL path>)"`, so name
  matching works, but two identical "Slack controls" tabs produce two web areas
  with identical titles and URLs. A name cannot choose between them.
- The covered page keeps a stale frame overlapping the editor, with
  `AXHidden=False`. A single hit test at the page's centre resolved the
  visible page correctly in every state. Name matching was therefore not
  added: the hit test alone is sufficient and needs no tab lookup.

**Implementation:**

1. Walk native children of the focused window, stopping at every `AXWebArea`
   (about 4 ms). Native pressable controls are collected on the way.
2. The web area titled like the window is primary. If not exactly one matches,
   the whole window is queried as before (no behaviour change).
3. Render native + primary controls immediately.
4. `cron.after("0ms")`: one centre hit test per other web area; query only those
   whose hit belongs to them, and append. Cancelled on stop/refresh; a changed
   focused window triggers a full refresh instead.
5. Event refreshes collect both stages synchronously so numbers stay stable.
6. Selection keeps the per-target ownership recheck.

**Success criteria and evidence:**

| Criterion | Evidence |
|---|---|
| Same targets as the previous collector | Prototype vs production `_controls`, 3 states: identical role/name multisets (136 / 475 / 136) |
| Hidden pages not walked | Editor in front: 0 secondary queries; 136 targets |
| First labels sooner | 1.21–1.34 s vs 4.2–5.1 s previously |
| Visible page appended, numbers stable | Browser in front: render 122 at ~1.2 s, then 475 at ~2.2 s (4 runs); first 122 unchanged |
| Errors surfaced | Tests: hit-test provider error and query errors stop the session and notify |
| Opt-in only | Tests: setting off performs no hit tests and no deferred job |

Tests: 50 runtime/inventory tests pass; Ruff check passes.

**Risks:** a page whose centre is covered but which is partly visible is not
walked (same centre-point policy as N12a). Split editor groups showing two
pages side by side were not tested.

**Rollback:** set `user.accessibility_defer_web_areas = false` in
`inventory_vscode.talon` (whole-window query; covered pages return).

**Open — intermittent `AttributeError: AXRole`:** raised inside Talon's
`axquery` `prune_visible` (`talon/mac/ui.py __getattr__`). Seen on the first
show of 2 of 2 live batches and 1 of 8 idle-then-query probes (workbench root
after 60 s idle; the same query succeeded moments later).

**Cause — node destroyed during the walk (reproduced):**

- Talon's `.py4` modules are compiled; `dis` and `inspect` cannot read
  `MacExecutor.prune_visible`, so the cause was found by wrapping it.
- Five wrapped one-minute idle queries in window 8919 did not fail, so idle
  time alone does not reproduce it.
- In mokuro (7048), `Toggle Panel` was pressed while workbench queries ran:
  - 2 of 6 queries raised `AttributeError: AXRole`: the one running across the
    toggle and the one started just after it.
  - The 4 later queries and 3 quiet queries returned 253 controls.
- In both captures, the node passed to `prune_visible` was a `RichElement`
  with `attrs == []`. `get("AXRole")` returned `None` and `.AXRole` raised
  `AttributeError: AXRole`: a node removed from the DOM after it was
  enumerated. Talon's pruning reads `.AXRole` without handling that case.
- The idle and first-show failures in 8919 fit the same mechanism, because
  that window's chat DOM changes while it streams. Which mutation caused each
  of those failures was not captured.
- The probe left mokuro's panel hidden (the toggle re-rendered, and later
  presses raised `ActionFailed`); it was restored and checked (`AXValue` 0 → 1).

Evidence: `files/n10/mutation_probe.py` / `.json` in the session folder.
Remedy chosen: filter frames ourselves (N12c).

**Checklist:**

- [x] Tab-name vs web-area relationship proven; duplicate-tab ambiguity found.
- [x] Staged collection implemented behind a `.talon` setting.
- [x] Equivalence with previous collector shown in three states.
- [x] Live staged rendering and timing measured, tab restored.
- [ ] Split editor groups.
- [x] Root cause of `AttributeError: AXRole`: DOM mutation during the walk.
- [x] Choose and verify a remedy: N12c.

### N12c. Replace Talon's visibility pruning with a surface clip

**Status:** implemented 2026-10-30 as `user.accessibility_clip_to_surface`
(default false, VS Code true). Live action-path checks passed; microphone
recognition remains untested. Settings/scrolled-list checks ran and found
an unresolved view-reset failure (see follow-up and N12e).

**Goal:** stop `AttributeError: AXRole` (N12b) without losing visible
controls or numbering hidden ones, and without being slower.

**Scope:** `_query_controls` in `accessibility/inventory.py`, the VS Code
`.talon` setting, runtime tests. Other apps keep Talon's pruning.

**What Talon's pruning does (black box):** `MacExecutor.prune_visible(self,
relement) -> bool` is compiled, but can be called directly with a
`RichElement`. For the two controls it pruned in window 8919, it returned
`False` for the element alone and `True` once ancestors were supplied.
The pruned `AXToolbar` (y 833–855) has no positive overlap with its
grandparent `interactive-input-part` (y 855–989). Across every state below,
no control Talon kept had an ancestor without overlap, and every control it
dropped had one. The hypothesis "keep a node only if it overlaps every
ancestor frame" is consistent with all observations. It is not proven
beyond them.

**Rule tested (R0):** `visible_only=False`, existing role, enabled, hidden,
and frame filters, plus positive overlap with the queried window or menu
frame. Elements removed mid-query read `None` for every attribute through
`get()` and are skipped.

**Evidence** (`files/n10/own_filter_*.py` / `.json`):

| State | Talon | R0 | Only R0 | Only Talon | Talon s | R0 s |
|---|---:|---:|---:|---:|---:|---:|
| 8919 editor in front | 134 | 136 | 2 | 0 | 1.18–1.20 | 0.41–0.42 |
| 8919 browser in front (workbench + page) | 473 | 475 | 2 | 0 | 1.72 | 0.80–0.89 |
| mokuro panel shown | 138 | 138 | 0 | 0 | — | — |
| mokuro panel hidden | 126 | 126 | 0 | 0 | — | — |
| `_controls` production code, 8919 (×3) | 137 | 139 | 2 | 0 | 1.30–2.02 | 0.45–0.50 |
| `_controls` production code, mokuro (×3) | 141 | 141 | 0 | 0 | 1.17–2.23 | 0.45–0.47 |

- The 2 extra controls are the chat's **15 Files +3139 −273** and **2
  Artifacts** buttons. A Talon screen capture of that strip shows both are
  drawn on screen at those frames, so Talon's pruning was hiding visible
  controls.
- A centre hit test is not a reliable visibility check here: **2 Artifacts**
  hit the chat `AXList` overlay all 3 times, and **Session Changes** missed
  once while the chat was streaming.
- Mutation stress in mokuro: 30 `Toggle Panel` presses (the button is looked
  up again before each press, because the old element goes stale), with
  pruned and R0 queries alternating.

  | Query path | Runs | `AXRole` errors | Mean s |
  |---|---:|---:|---:|
  | Talon pruning | 19 | 19 | 0.53 |
  | R0 | 18 | 0 | 0.49 |

  R0 skipped 74 removed elements. The panel ended in its original state
  (`AXValue` 1).
- The `_controls` rows ran the committed code in the background with probe
  settings, because Talon applies `.talon` settings only for the active app.

**Risks and mitigations:**

- Native apps clip scroll views, which a window-frame overlap does not
  detect. The setting stays off by default and is enabled only for VS Code.
  Compare per app before enabling it elsewhere.
- Web content scrolled inside an inner container would not be clipped. None
  appeared in the tested VS Code states (Only R0 = 2 visible controls).
  Settings editor and long-list states remain untested.

**Rollback:** set `user.accessibility_clip_to_surface = false` in
`inventory_vscode.talon`, or revert the commit.

**Checklist:**

- [x] Talon pruning rule characterised by calling `prune_visible` directly.
- [x] R0 vs Talon equivalence in 4 layouts; differences shown visible on screen.
- [x] Mutation stress: 0 of 18 R0 queries failed vs 19 of 19 pruned.
  This holds for VS Code panel toggles only; R0 failed 4 of 5 runs in
  Firefox (N12d), so it is not a general mutation fix.
- [x] Setting, VS Code enablement, and unit tests (53 pass, ruff clean).
- [x] Production `_controls` verified in both VS Code windows.
- [x] Live `accessibility_show_application_numbers` action with VS Code in
  front; hidden pages excluded, both duplicate browser tabs tested, original
  tab restored. This invokes the command's action, not microphone recognition.
- [x] Run Settings and long-list comparisons, including a real numbered
  activation of the search field; findings below.
- [ ] Pass Settings state-preservation and extra-control visibility gates (N12e).

**Live follow-up (2026-10-30):**

| Selected editor tab | First numbers | First render returned (s) | Final numbers | Initial number prefix stable |
|---|---:|---:|---:|---|
| Editor | 138 | 0.951 | 138 | yes |
| Browser tab 0 | 116 | 0.707 | 388 | yes |
| Browser tab 1 | 120 | 0.778 | 473 | yes |
| Editor restored | 138 | 0.908 | 138 | yes |

Both settings were enabled through the real VS Code context. Final inventories
contained only the workbench when the browser tabs were hidden, and the
workbench plus one browser web area when either browser tab was selected.
Deferred work was complete in every final sample. The render instrumentation
captured the first render but not the append render, so these results do not
establish time to final paint or time to final numbers. No microphone input was
used. Evidence: session `files/n10/verify_n12c.py` and
`verify_n12c_results.json`.

An attempt stopped at its focus guard while the screen was locked
(`loginwindow`, window -1). After the user unlocked and approved resuming,
the remaining tests ran in mokuro (7048), not this conversation's window.

**Settings and scrolled-list follow-up (2026-10-30):**

Settings opens as a modal editor in this build. The test did not assume it
was a regular editor tab. No preference value or file content was edited.

| State, workbench query only | Talon | Surface | Only surface | Only Talon | Talon s | Surface s |
|---|---:|---:|---:|---:|---:|---:|
| Commonly Used, initial | 19 | 25 | 6 | 0 | 0.241 | 0.100 |
| Commonly Used, later comparison | 19 | 25 | 6 | 0 | 0.228 | 0.096 |
| Search `editor`, 558 results, top | 19 | 26 | 7 | 0 | 0.405 | 0.154 |
| Search `editor`, after confirmed forward scroll | 19 | 27 | 8 | 0 | 0.381 | 0.152 |
| After invoking application numbers again | 19 | 25 | 6 | 0 | 0.226 | 0.096 |

- These queries used the same root, unlimited depth and 10-second budget.
  Their observed times were well below that budget.
- Selecting **Search settings** by its real number (11) focused the expected
  `AXTextArea`; focus identity was verified before entering the search query.
- Forward scrolling was verified by screenshots: the viewport changed from
  Font Size/Format On Save to Mouse Wheel Zoom/Format On Paste/Accessibility
  Support. The AX inventory also changed: seven unique role/name entries
  were added, seven removed, and three shared entries changed frames.
  Earlier positive-direction scroll requests did not establish this
  forward-scroll state; do not infer successful scrolling from a request alone.
- Every surface-only difference was a **More Actions** popup. Ancestor trails
  were saved, but whether these hover-style controls should be numbered is
  unresolved. Absence of a zero-sized ancestor does not prove visibility.
  The new collector also retained partially visible 1-pixel-high controls;
  positive overlap permits these, and Talon retained the corresponding
  checkbox too. Usability is not established by set inclusion.
- The live command produced 28 labels in the Settings modal (including
  native window controls), with render-return timings of 0.133–0.155 s.
  **It did not preserve the view:** after the filtered, scrolled state,
  invoking `accessibility_show_application_numbers` returned Settings to
  blank search / Commonly Used. The screenshot and subsequent AX inventory
  agree on that reset. The particular step causing it is not isolated;
  do not attribute it to activation writes, querying, rendering, or pruning
  without an intervention test.
- An earlier screenshot/AX mismatch was observed during this sequence.
  Stale provider geometry was initially suspected, but the verified
  view-reset behavior means that suspicion is not an established cause.
- The modal was closed via its unique **Close Modal Editor (Escape)**
  control. Focus returned to window 8919; instrumentation was removed.
  The probe's regular-tab selector returned an empty list in mokuro, so its
  empty-list comparison is not independent proof of editor-tab identity.
- Focused automated regression suite: **53 tests and 30 subtests passed**.
  These mocks do not cover the modal-reset behavior.

Evidence: session `files/n10/verify_n12c_results.json`,
`compare-settings-top.png`, `compare-settings-long-forward.png`,
`settings-numbered.png`, and the ancestor trails in the comparison records.
The comparison data supports faster collection without losses relative to
Talon in these states, **not** blanket visibility correctness or Settings
state-preservation certification.

### N12d. Compare both visibility filters across applications

**Status:** native and browser spikes done; Electron (Slack) not run.
**Decision so far:** keep Talon's pruning as the global default and keep
surface clipping enabled only for VS Code. **Effort:** S per application.
The filter implementation is generic; only its enablement is app-specific.

**Goal:** determine empirically whether surface clipping can replace Talon's
visibility pruning generally, or which applications require which policy.

**Scope:** separate bounded read-only spikes for one native app with nested
scroll views, one browser using a non-sensitive local fixture, and one other
Electron app (for example Slack with a user-approved test channel). Compare
both query paths under identical roots, roles, depth and timeout. No message
sending, document edits, account actions or blanket application overrides.

**Steps:**

1. Select the app, safe fixture and important controls with the user; record
   starting focus, selected view, scroll position and panes for restoration.
2. Compare Talon pruning and surface clipping at the top, middle and bottom
   of a long list/document; repeat with a nested scroll area and one obscured
   or collapsed pane. Exercise menus separately with their own clip frame.
3. Record per-stage query/filter/render times, errors, counts and element-set
   differences. Use three quiet repetitions, plus a bounded mutation run.
   Check for timeout truncation rather than treating a returned list as complete.
4. Inspect every difference against a screenshot and the AX ancestor chain.
   Hit tests and count equality alone are not visibility ground truth.
5. Test numbered activation of approved controls, including stale targets.
   Record a per-app decision; decide on a global default only after the matrix.

**Success criteria and evidence:**

- No lost user-designated visible controls and no numbered controls clipped
  out of their viewport in any sampled state; all differences classified.
- No wrong-target activation; errors surfaced explicitly during mutation.
- Measured timings and complete-set evidence show whether the simpler filter
  is acceptably fast and reliable. A result that retains Talon's policy is valid.
- Persist a state-by-state table, screenshots/AX evidence for differences,
  restoration checks, and a decision with explicitly untested cases.

**Risks and mitigations:** native scroll clipping, web overflow, overlays and
  virtualized rows differ across providers. Test them directly; retain the
  existing default until evidence supports changing it. Avoid private pages
  and real message content by using fixtures and approved views.

**Rollback plan:** probes must not persist settings. Restore selected view,
scroll position, pane state, original focus and hide labels; remove temporary
instrumentation. Revert any later per-app enablement independently.

**Results** (same root, all roles, unlimited depth, 10 s budget; Talon =
`visible_only=True`, clip = `visible_only=False` plus window-frame overlap):

| App / state | Talon | Clip | Only Talon | Only clip | Talon s | Clip s |
|---|---:|---:|---:|---:|---:|---:|
| Finder `/Applications` icon view, top/mid/bottom | 12/12/11 | 12/12/11 | 0 | 0 | 0.09–0.18 | 0.38–0.48 |
| Finder list view, 80-folder fixture, top/mid/bottom | 33/37/34 | 34/40/37 | 0 | 1–3 | 0.23–0.31 | **8.5–9.0** |
| Firefox local fixture, spatial view (fits window) | 397 | 397 | 0 | 0 | 1.2–1.3 | 0.69–0.72 |
| Firefox fixture hierarchy, top | 31 | 31 | 0 | 0 | 0.23–0.30 | 1.45 |
| Firefox fixture hierarchy, middle | 42 | 28 | 14 | 0 | 0.56–0.61 | 1.44 |
| Firefox fixture hierarchy, bottom | 36 | 25 | 11 | 0 | 0.28–0.34 | 1.41–1.52 |

Classification of every difference:

- **Finder list, clip-only (1–3 per state): wrong.** They are
  `AXDisclosureTriangle`s of rows scrolled under the toolbar (y 152–192) or
  path bar (y 611–622), outside the scroll area (y 219–603). The screenshot
  shows them hidden. Clip checks only the window frame, not the native
  scroll-view clip, so it numbers hidden controls here.
- **Firefox hierarchy, Talon-only (14 and 11): Talon is wrong.** Every one
  has a frame far above the viewport (for example the filter field at
  y −15,679 and −32,624; window y 33–1032). The screenshot shows none of
  them. They are the page header and nested section headers (x indent steps
  by 12 px) enclosing the scrolled-in section. This matches Talon's rule,
  measured in N12c: it compares a node's frame with its ancestors', not with
  the window. Clip correctly drops them.
- **Speed:** clip walks every unpruned node. That is acceptable in VS Code,
  but it took 9 s in the Finder list (truncated under the default 1 s
  timeout) and about 5× longer than Talon on the long Firefox page.
- **Mutation** (Firefox fixture, 10 Spatial/Hierarchy toggles while
  alternating queries): Talon failed 5 of 6 runs, clip **4 of 5**, both with
  `AttributeError: AXRole`. The clip traceback is in Talon's selector
  matching (`axquery/mac.py match_element`), not in `prune_visible`. The
  VS Code result in N12c therefore does not generalise.

Neither filter is correct everywhere. Talon over-includes ancestors of
scrolled web content; clip over-includes native scroll-view content and is
slow on large native lists. A general fix would need the nearest scroll
area's frame as the clip (a follow-up spike, not started), not a different
global default.

Restoration: the Finder scroll position was restored and the window closed;
`/tmp/xapp_fixture` was deleted; the Firefox test window was closed, leaving
the original Mokuro window as the only window of that instance. Incident:
in the first Firefox attempt a new window focused the page, so the typed
fixture URL went to a link-hint extension as keystrokes. Escape was pressed,
the window closed, and the original window's title verified unchanged. Later
attempts verified URL-bar focus before typing.

Untested: Slack (not running), a bounded run of numbered activation per app,
menus with their own clip frame, and obscured/collapsed panes outside VS Code.

Evidence: session `files/n10/xapp_<state>.json` and `.png`
(`finder_*`, `finder_list_*`, `firefox_*`, `firefox_h_*`),
`xapp_firefox_mutation.json`, `xapp_firefox_mutation2.json`, probes
`xapp.py`, `ff_fixture.py`, `ff_mutation.py`.

**Checklist:**

- [x] Native app spike and decision: keep Talon pruning (clip numbers hidden
  rows and is about 30× slower in list view).
- [x] Browser/local-fixture spike and decision: keep Talon pruning by default.
  Clip is more correct on scrolled pages but about 5× slower, and it does not
  avoid mutation errors.
- [ ] Other Electron app spike and decision (Slack not running).
- [x] Compare results and choose: per-app policy; global default unchanged.
- [ ] Follow-up spike: clip to the nearest scroll area instead of the window.

### N12e. Preserve the Settings view while showing numbers

**Status:** open; reproduced during N12c verification. **Effort:** S for
isolation; remediation effort unknown until the resetting step is identified.

**Goal:** invoking application numbers must not clear a Settings search,
change its selected category, or reset its scroll position.

**Scope:** mokuro's Settings modal and the existing action path only.
Keep this separate from N12d's cross-application default decision.

**Steps:**

1. Recreate a non-empty Settings query and a visibly scrolled viewport.
   Record query, viewport anchors, focused element and screenshot.
2. In at most two bounded diagnostic rounds, run activation preparation,
   collection, and native label rendering as separate interventions.
   Recreate and verify the initial state before each intervention.
   Compare both pruning modes only after isolating the responsible step.
3. If the resetting step is identified, choose the smallest supported
   remedy and add focused regression coverage. If not, report the evidence
   to the user before further investigation.
4. Repeat the real command from the filtered/scrolled view; check numbered
   targets against visible controls. Separately test a More Actions popup
   and dismiss its menu without changing a preference.

**Success criteria and evidence:** search text, viewport anchors and focus
remain unchanged except for explicitly selected controls; correct labels
appear without reintroducing hidden browser pages or the AXRole failure.
Save before/after screenshots, AX identities/frames, intervention results,
and a completed checklist. Classify hover-only and partial-control behavior
explicitly rather than treating Talon's result as a visibility oracle.

**Risks and mitigations:** AX activation or rendering could affect provider
state, but neither is established as the cause. Isolate rather than guess.
Do not toggle a preference or touch unsaved editors.

**Rollback plan:** remove instrumentation, hide labels, close only the
test-opened Settings modal, and restore the original focus. Keep any later
production remedy independently revertible.

**Checklist:**

- [x] Capture the command-level reset and restore the test UI.
- [ ] Isolate the resetting intervention within two bounded rounds.
- [ ] Implement and verify a supported remedy, or report a blocked finding.
- [ ] Verify hover-only More Actions and partially visible controls.
- [ ] Pass the filtered/scrolled real-command check.

### N13. Depth caps, measured against the ground truth

**Effort:** S. **Depends on:** N10, N12.

From the workbench root (not the window), for each cap from 4 up to
unlimited, record:

- time;
- how many candidates are returned;
- which **user-marked important controls** are dropped, by name.

Repeat for each N10 state. A cap is acceptable only if it drops **no**
important control in **any** state and saves measurable time. If no cap
qualifies, record that and remove the depth cap from consideration. The
existing depth-13 window-root setting is re-evaluated here, not
grandfathered.

**Done when:** a table per state, plus a keep, change or remove decision for
`inventory_vscode.talon`.

### N14. Remove duplicated work in our own collection

**Effort:** S-M. **Depends on:** N10. **Highest-confidence savings;** each
item is measured alone.

| Duplicate work (measured in N2) | Candidate fix | What must be proven first |
|---|---|---|
| `_signature` re-reads role/title/description/identifier/frame/actions already read by the filter: 101 ms | Read each attribute once per refresh and reuse | Values read once are still the values the signature must compare |
| Equality deduplication is O(n²): 183,921 comparisons, 67 ms | Hash-based set | Talon `Element.__hash__` exists and is consistent with `__eq__` across separate queries |
| Role filtering after the query: 756 role reads | Put roles into the query selector | The selector syntax supports role alternatives, and the result set is identical |
| Talon pruning and our frame filter may both derive geometry (unproven; N11) | Keep one source, if N11 shows they overlap | Removing one changes no N10 result |
| Every UI event re-queries the whole tree | Refresh only the changed branch | Talon `element` events identify a usable subtree root; if not, record that |

**Done when:** each adopted change shows an identical label set on all N10
states and a measured time saving. A change with no measurable saving is
dropped, not kept for tidiness.

### N15. Wrapper-group compression (your mid-1..mid-3 example)

**Effort:** S. **Depends on:** N10; feeds N8 grouping.

Two separate questions:

1. **Does it save traversal time?** With the public API, reaching `mid-3`
   requires reading the children of `mid-1` and `mid-2`, so compression
   alone does not skip those reads. Only search for a shortcut if the AX tree
   offers one. Check whether Chromium exposes any attribute that returns
   descendants or a flattened set directly; if no such attribute exists,
   record "no traversal saving".
2. **Is a wrapper meaningful?** For grouping and label clutter, measure:
   - how many chains of single-child `AXGroup`s exist;
   - how often a wrapper carries a title, description, identifier, or its
     own clipping frame (it differs from its child's frame).

   Wrappers without those are safe to collapse **for presentation**. Wrappers
   with them are candidate group names for N8.

**Done when:** a count of collapsible versus meaningful wrappers per N10
state, and whether compression helps speed (expected: no, unless a shortcut is
proven), grouping, or neither.

### N16. Parallel traversal (only if N14 leaves a real gap)

**Effort:** M. **Depends on:** N14; deferred if N12-N14 make collection fast
enough.

Preconditions to **prove**, not assume:

- **The tree has no shared nodes:** no element is reachable from two
  branches, checked by element equality over a full N10 capture.
- **Talon's AX calls are safe from several Python threads.** Talon runs
  free-threaded Python (3.14t), but that does not establish thread-safety of
  its UI bridge. Run a bounded stress probe, and stop immediately on any
  error. A Talon crash here would violate the stability principle that led
  to removing the AX observer.
- **The application serves concurrent AX requests in parallel at all.** Test
  this with 1, 2, and 4 threads on disjoint top-level branches, comparing
  wall time and an identical result set.

**Done when:** a speedup with identical results and no errors across repeated
runs, or a recorded reason to drop the idea. The default outcome is to drop
it, because this repository would own threading code.

### Too many labels

Not a separate spike. N10 records label counts per state, N13 and N14 only
remove work, and clutter reduction belongs to N8 grouping. The usability bar:
a user-marked important control must never disappear to cut clutter. N15's
meaningful wrappers are the first candidate grouping names.

### N17. VS Code latency: scoped work, caching and tree differences

**Priority:** High. **Status:** proposed small spikes, not implemented.
**Effort:** S for N17a; M for each conditional caching experiment. Estimates,
not commitments: the public event capabilities must be established first.
Build on N2/N12/N14, not a second collector or application adapter.

#### N17a. Remove work before introducing persistent caches

**Goal:** lower time-to-labels without stale results or missing required controls.
**Scope:** query/root selection and per-collection duplicated reads only.

**Steps:**

1. Measure cold and warm show timings separately: preparation, tree query,
   ownership checks, signature and rendering. Repeat fixed current-project
   and mokuro fixtures, including visible/covered browser, Settings and menus.
2. Test whether generic workbench/visible-webview roots can be established
   before the expensive query (N12), with native window controls retained.
3. Reuse ancestor/attribute reads within one refresh where N14 demonstrates
   duplicate work; do not cache UI state across refreshes in this spike.
4. Compare exact control sets and required-control coverage with a complete
   reference, recording timeout truncation and layout drift separately.

**Success criteria/evidence:** report repeated cold/warm p50/p95 and phase
timings, identical required-control coverage and no hidden-browser labels.
Proposed usability targets to validate with the user: warm show below 500 ms,
cold show below 1 s. If not achieved, quantify the gap, not just a relative
speedup. An optimization with no measured improvement is dropped.

**Risks/mitigations:** root heuristics can omit active embedded pages; require
foreground/background and partial-visibility fixtures. No app-URL branches.
Budget changes are not presented as speed improvements.

**Rollback:** revert only the adopted optimization, retaining N12a visibility
and failure notifications; reference collector remains the comparison.

#### N17b. Prove a safe cache-invalidation signal

**Goal:** determine whether cached targets can be reused without stale numbers.
**Scope:** investigate supported Talon events, not native AX callbacks or polling.

**Steps:** record event payloads for opening/closing/switching files, folder
expansion, scrolling, pane resizing, notifications, terminal/session switching,
window changes and embedded browser navigation. Check whether each event
identifies an element/subtree and whether changes ever arrive without a usable
event. Check focus/window/process identity and element lifetime across captures.

**Success criteria/evidence:** event matrix with a reliable invalidation path
for every tested change, or an explicit no-go. Reading the whole tree and
diffing it afterwards does not save AX enumeration; separate provider time
from Python comparison/render savings. Existing session targets are already
held in memory; merely adding another list is not an optimization.

**Risks/mitigations:** missing/coalesced events, stale or recycled elements,
and moved label numbers. If invalidation cannot be proven, reject persistent
caching rather than add a guessed TTL. Revalidate before selection.

**Rollback:** read-only probe; no production cache to remove.

#### N17c. One dirty-branch refresh experiment (only if N17b passes)

**Goal:** re-query only a changed branch while preserving full-refresh behavior.
**Scope:** one supported event/branch type, bounded cache owned by the active
label session only. No global AX inventory.

**Steps:** key state by process lifetime and focused window; compare an
incremental refresh with the full reference after every fixture change;
invalidate on window/process/root change and discard dead elements. Measure
whether selection guards also need fresh role/action/frame reads.

**Success criteria/evidence:** identical target/action sets, zero stale or
wrong-target selections, reduced AX work and the N17a latency measurements.
Include a missed-event simulation: either detect it and explicitly refresh,
or reject the design. Stable label numbering is a separate UX decision.

**Risks/mitigations:** a change can affect ancestors, clipping or sibling
geometry, so a dirty branch may not be a sufficient invalidation boundary.
Do not silently serve stale results or call an unverified diff API.

**Rollback:** remove the session cache and use the validated full refresh.
