# Backlog assessment: feasibility, holes, and effort

This is a critical review of every backlog idea. It challenges each idea's
premise, checks for overlap with code already installed (Community, Rango,
AxKit, and this repository), and estimates effort. It is opinion backed by
local evidence, not a commitment.

**Effort scale:** XS < 1 hour · S ≈ half a day · M ≈ 1-2 days · L ≈ 3-5 days ·
XL > 1 week. Estimates assume the user is available for voice testing.

bb Summary

| Idea | Verdict | Effort | Key reason |
|---|---|---|---|
| [Verification](verification.md) V1-V8 | **Test gaps first** | S-M remaining live work | Reuse passing automated checks; provider visibility and voice gaps remain |
| [Numbers speed and grouping](numbers-and-menus.md) N1-N3/N8/N9 | **Current priority** | M, plus S-M grouping/VS Code validation | Measure latency, clutter, target identity, and activation; grouping is a distinct requirement |
| Mouse-centered numbers | **Pursue spatial filtering** | M | Radius or nearest-N; no visible circle was requested; background support unverified |
| App profiles (traversal settings) | **Pursue, settings only** | S-M | Talon context settings already provide override semantics |
| Slack named sections | **Pursue grouping spike** | S-M discovery; M+ if new selectors needed | Channel switching does not replace pane-scoped numbers; selector stability is unverified |
| Firefox instance names | **Investigate identity first** | S discovery; implementation TBD | Must work after launch from Firefox's profile switcher; argv is not an established identity source |
| HUD transparency/collapse | **Clarify first** | XS to L | Depends entirely on which component "hug" is |
| `search [<text>]` → Ctrl+F | **Custom work withdrawn** | XS learning | Learn Community's `hunt this` commands instead |
| Command overlap inventory (W5) | **Pursue early** | S | Prevents building things that already exist |
| Rango-style aliases elsewhere | **Pursue narrowly** | XS-S | Mostly already exists; only `upper`/`downer` are missing |
| Windows `command c` / `command l` | **Custom work withdrawn** | XS learning | Community maps "command" → Ctrl on Windows |
| Generic AX/UIA walker | **Do not pursue now** | L-XL | Little shared code, high cost, unclear Windows usage |
| Highlight H1-H2 | **Pursue** | S | Close to a promote/remove decision |
| Highlight static text (H3) | **Time-box or drop** | M | Rango/Cursorless cover browser and VS Code |
| Substring bounds (H4) | **Park** | M-L | Cosmetic; the popup works |
| Fuzzy matching (H5) | **Park** | S (collect data) | Risk of selecting the wrong word |

**Suggested order:** correct numbers visibility/coverage (N1/N9/V8), then the
scoped-collection plan (N10 ground truth → N11-N13 → N14 deduplication → N15 →
N16 only if needed), then grouping (N4/N8); fill remaining verification gaps and learn
Community commands (W5/W7/W8/P3) →
Firefox identity discovery → mouse radius/nearest-N comparison → H1/H2.
No custom search or Windows modifier aliases.

**Verification update (2026-10-29):** the prepared Word fixture revealed a
real codepoint-versus-UTF-16 range bug after a non-BMP character. The code now
converts indices in both directions; Word selected the target correctly after
the fix. Slack passed basic highlight navigation in the unsent draft; it had no
emoji, so provider-specific Unicode behavior remains unknown. The direct
application-label show/hide test propagated and cleared the runtime tag.
Phrase simulation was inconclusive because Talon matched sleep mode's generic
`<phrase>: skip()` rule, not the requested voice command.

## Highlighting track

**H1/H2 (validate, promote).** Worth finishing; the spike is small, isolated,
and now has runtime tests. *Hole:* VS Code is in the H1 matrix, but you already
have Cursorless there, which is strictly better for selecting words. Treat VS
Code as a smoke test only; the real targets are Word and Slack. Effort: S.

**H3 (static text).** *Holes:* static text (`AXStaticText`) in Slack messages
and web pages rarely accepts range writes, and readable selection attributes do
not prove writability. The main use for selecting static text is copying it,
which Rango already does in the browser. Likely outcome: "unsupported" in most
apps. Recommend a 2-hour time box for Slack messages only, or drop it. Effort: M.

**H4 (substring bounds for on-word labels).** Purely cosmetic over the popup.
The one data point (`Rect(0, 1117, 0, 0)`) is already unusable, and Electron
apps often return junk bounds. Park. Effort: M-L, plus canvas maintenance.

**H5 (fuzzy).** Dictation errors are usually whole-word substitutions that
homophones already address; fuzzy edit distance on short words matches the
wrong word. Collecting failed examples is cheap. Implementation is not
justified yet.

## Numbers and menus track

**N1-N3 (depth, measurement, filters).** Highest-value numbers work: latency
and label clutter affect every use. *Hole:* "visible_only" is not strict
visibility, so filtering may hide needed controls. N3 already requires
per-filter evidence. **Corrected finding (2026-10-30):** the unexpected
`message pane` target is a real HTML button depicting a Slack element in the
covered report, not a fake editor control. The depth-13 cutoff preserves
report buttons while omitting deeper workbench controls. No title/bundle
blacklist is justified.

Read-only measurements returned 989 matches in about 2.89 s with native
visibility pruning versus 994 in about 1.05 s without it; both include the
hidden reports. Querying only the actual workbench returned 243 matches in
0.43 s without pruning. This supports investigating cheap branch-level
visibility before traversal, not simply removing visibility checks. Hit tests
distinguish the covered reports here, but partial visibility still needs
validation. Spoken 69 dispatch remains unverified; a direct button press does
not prove voice dispatch. See N2/N9 for measurements and limits. Effort: N1 S,
N2 S-M, N3 M, N9 S-M; implementation is not complete.

**N10 execution update (2026-10-30):** approved mokuro layouts and selected
numbered actions were exercised. VS Code now uses depth 0 and a 3-second budget;
the original 1-second budget independently truncated deeper traversal.
Cheap usable-frame filtering matched native-pruned results in settled ordinary
layouts but retained six extra positive-size Settings menus. Do not remove
native pruning on this evidence. Explorer/terminal group-role exclusions and
chat rows without AXPress remain genuine coverage gaps; see the N10 results and
checklist. No cross-application visibility change was adopted.

**Application profiles.** Your goal: per-app profiles that override the generic
one. *What already exists:* Talon context settings (`app: slack` + `settings()`)
already provide "app profile overrides generic default". VS Code depth uses
this today. *Recommendation:* prefer existing settings where sufficient.
Settings alone do not yet express named pane roots: N4 must establish the
gap before adding an extension point. Avoid arbitrary maximum-label counts,
which can hide needed controls. No Python bundle branches or adapter framework.
Effort: S for a settings-only adjustment; M+ if scoped-query support is needed.

**Named Slack sections / scoped walking.** *Holes:*

- Community offers `channel <text>`, `channel up/down`, `unread next`, and
  `go search`. The installed `channel` action opens Cmd+K's picker and types
  text without submitting; `go search` opens Cmd+F. This does not replace
  restricting number labels to a pane.
- Slack's AX identifiers, DOM classes, and titles are candidate selector
  attributes, not proven stable names. Content, unread counts, and app updates
  can change them; validate their uniqueness and stability before using them.
- A section is usually a structural group, not a pressable control.

*Better framing:* "show numbers in <section>", meaning restrict the query root
to one pane (sidebar, message list, thread). That reduces clutter and query time,
which is the real benefit. It must fail clearly ("section not found") when the
selector misses, rather than silently labeling everything. Scope selection may
itself require traversal: measure before promising a speed-up. Effort: S-M for
N8; implementation and ongoing upkeep depend on the selector evidence.

**N7 (session handoff).** Required; do it with V2. Effort: XS-S.

## Mouse AX track

**Feasibility:** plausible, not established for background windows. Talon's
`ui.element_at(x, y)` (already used in [status discovery](../status/discovery.py))
is prior art for hit-testing, not proof of correct ownership or label selection
in every app. M1/M3/M4 must verify discovery, querying, rendering, and pressing
separately. Hover scrolling does not establish AX support.

*Holes and simplifications:*

1. **Activation is the real unknown.** `AXPress` on a background window may
   work without focus, raise the window, or do nothing (common in
   Electron/Chromium). That is M4, and it decides whether the feature is useful.
2. **Lazy AX providers.** Background Electron/Firefox apps may not expose a
   tree until `AXManualAccessibility`/`AXEnhancedUserInterface` is set. The
   current activation code targets `ui.active_app()` only; it must target the
   hovered app instead.
3. **No drawn circle.** The user meant a conceptual search radius, not an
   overlay. Remove the canvas work entirely; native labels are the only output.
4. **The radius is a tuning burden.** An alternative is to label the
   **N nearest controls** to the pointer (for example, 10) in the hovered
   window. Nearest-N is an acceptable alternative to compare, not an approved
   replacement. It can reach surprisingly distant controls in sparse windows;
   define distance to bounds, ties, directional eligibility, and whether a
   maximum distance is needed. A nearest-N cap can also omit nearby controls.
5. **Grammar collision.** `show numbers` is Talon's built-in labels command;
   adding `[left|right|up|down]` changes a core phrase. Use a distinct phrase
   during the experiment (for example `hover numbers [<direction>]`). This repo
   already has `hover <label>` and `mouse left <number>`, so choose words that
   do not collide with those.

Effort: M1 XS-S, M2 S, M3 S-M, M4 S, M5 XS-S. Overall M as an exploratory
estimate, potentially more if background ownership/activation is unsupported.

## Workflow and discovery track

**HUD ("hug") transparency/collapse.** *Hole:* no "HUD" is installed in your
Talon user directory. Candidates: the third-party Talon HUD (`talon_hud`, not
installed), Community subtitles (`plugin/subtitles`, which already has
min/max/per-character timeout settings), and the Community mode indicator.
If it is subtitles, timed hiding already exists (XS). Talon `imgui` has no
transparency API, so fading an imgui panel means rewriting it as a canvas (L).
W1 is a 15-minute identification step; do it before estimating further.

**Firefox instance names.** Real and worth investigating. The confirmed
workflow launches profiles from Firefox's profile switcher. Do not base the
design on `-P`/`--profile` arguments or assume a profile always maps to one
process. W3 must establish a supported, restart-stable profile-to-window/app
identity from that exact workflow without collecting browsing content.
Alternate launchers/channels would change the workflow and need approval.
Effort: W3 S; W4 cannot be estimated reliably until identity is established.

**Command overlap inventory (W5).** Do this early. This review already found
three overlaps (Windows `command`, Slack `user.messaging`, `hunt this`). The repo
has [command inventory tooling](../reports/) to build on. Effort: S.

**Rango-style consistency (W6).** *Findings:* `upper`/`downer` are Rango-only
(browser). Community's `user.tabs` tag already provides `tab next/last/close`
in many apps, so tab consistency mostly exists. The missing piece is `upper`/
`downer` outside the browser: a few lines mapped to scroll actions in a context
that excludes the browser. *Hole:* a page-scroll alias in apps with several
scroll panes scrolls whichever pane the pointer is over, which differs from
Rango's "main" scroll. Effort: XS-S.

**Find commands (W7).** Custom `search` alias withdrawn by the user. Learn
Community's `hunt this`, `hunt this <text>`, `hunt next`, and `hunt previous`
in contexts with `user.find`. No replacement grammar. Effort: XS.

## Cross-platform track

**Windows `command c` / `command l` (P3/P4).** Custom aliases withdrawn.
Community's
[Windows modifier list](../../community/core/keys/win/modifier_key.talon-list)
already maps `command: ctrl`, so `command c` → Ctrl+C and `command l` →
Ctrl+L likely already work on Windows. *Remaining risk:* another repo or local
override on your Windows machine. Effort: XS to verify; probably no code.

**Generic AX/Windows tree walking (P1/P2).** *Holes:*

- `axquery` and the AX attribute model are macOS-specific. Windows UI
  Automation (UIA) uses patterns (Invoke, Value, Text) instead of AX actions.
  The shared part is limited to geometry/filter helpers, roughly 50 lines.
- It is not established that Talon's `actions.labels` (numbers) works on
  Windows; P1 must check this first, or the payoff disappears.
- Value depends on how much you use Windows. If you mostly switch between the
  two for shortcuts, the Windows command mapping above captures most of the
  benefit.

Recommend: do not pursue until you have a concrete Windows workflow that needs
labels. Effort if pursued: P1 M (needs a Windows machine), P2 L.
