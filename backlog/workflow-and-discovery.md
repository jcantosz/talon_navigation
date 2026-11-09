# Workflow and command-discovery backlog

These are independent of the highlighting and AX-number experiments.
Follow the [project principles](README.md); prefer existing actions and settings.

## W1. Identify the built-in "hug" / HUD surface and its existing options

The requested name was "built in hug"; confirm the actual UI/package before
assuming it means Talon's HUD, native captions, or Community subtitles.
Inspect its supported settings/actions and ownership.

**Done when:** the exact component, current commands, and supported opacity/
collapse APIs are documented. Do not modify Talon internals based on the name.

## W2. Test timed transparency or collapse on that one surface

**Depends on:** W1.

Try existing configuration first. If unsupported, document the gap and cost
before a custom implementation. Test one behavior at a time: transparency,
then collapse, including restoration on interaction, timer cancellation,
application_controls/readability, and reload cleanup.

**Done when:** a reversible proof or a supported-API limitation is recorded.
Choose delay/restoration behavior with the user before promotion; no new
background polling or caption behavior changes hidden in this spike.

## W3. Identify separately running Firefox profiles

Inspect existing application switching/alias actions first. With three
user-provided Firefox instances, compare process/window metadata and supported
profile identifiers without collecting browsing content. Distinguish processes
from windows and profiles; display name alone is not unique.

**Confirmed workflow:** instances are normally launched from Firefox's profile
switcher. Reproduce that exact launch path; do not assume `-P`/`--profile` is
present or require a new launcher workflow. Time-box investigation of supported
profile-to-process/window metadata; report an unsupported result if there is
no reliable mapping. Launcher apps or alternate Firefox channels would be a
workflow change requiring user approval, not a transparent fallback.
**Effort:** S discovery; implementation estimate waits for an identity source.

**Done when:** a reproducible identity strategy or explicit platform limitation
is recorded, including instance restart, PID reuse, and ambiguous/missing matches.
No dependence on ephemeral AX tree paths.

## W4. Prototype one user-defined application-instance alias

**Depends on:** W3.

Map one spoken custom name to one verified Firefox profile/instance using
existing switching actions where possible. Require explicit ambiguity errors;
do not select the first app called Firefox. Keep the mapping opt-in and separate
from AX traversal.

**Done when:** selection works with all three instances, after restart, and
fails clearly when absent/ambiguous. Add more aliases only after that result.

## W5. Build an existing-command overlap inventory

Inspect installed Community, Rango, AxKit, and repository commands/actions
without changing external packages. Use local command-report tooling described
in the [project README](../README.md); do not assume advertised defaults are
active locally.

Bound the first pass to numbers/menus, app switching, scrolling (`downer`/
`upper`), tab navigation, and copy/address-bar shortcuts.

**Done when:** a table lists desired task, existing spoken form/action,
application/OS scope, collision, and recommendation (reuse/document/alias/new
spike). This is discovery, not a global grammar rewrite.

## W6. Try one cross-application scrolling or tab alias

**Depends on:** W5.

Pick one task with the user (scrolling or tab navigation). Determine what
Rango's command means in the browser and whether a shared Community action
expresses that intent elsewhere. Separate web-page structure navigation from
generic scrolling; don't promise identical semantics where they differ.

**Done when:** one opt-in alias is tested in a browser and one non-browser app,
with scope/precedence and unsupported behavior recorded. Broader aliases and
additional tasks remain TBD; no automatic overriding of app-specific commands.

## W7. Learn Community find commands (custom alias withdrawn)

**Status:** custom `search` alias cancelled by the user, 2026-10-29.
**Effort:** XS, learning/documentation only.

Community's `hunt this [<text>]` already calls `edit.find(text)` (Cmd+F on
macOS, Ctrl+F on Windows), but only in apps with the `user.find` tag.
Learn `hunt this`, `hunt this <text>`, `hunt next`, and `hunt previous`.
Do not add replacement grammar.

**Done when:** the user has tried these forms in the desired apps; inactive
contexts are recorded for W5 rather than assumed to be missing commands.

## W8. Distinguish Slack channel switching from message search

**Effort:** XS. Installed Community grammar in
[messaging.talon](../../community/tags/messaging/messaging.talon) maps
`channel <text>` to the channel picker followed by lowercase text insertion.
The [macOS action](../../community/apps/slack/slack_mac.py) sends Cmd+K; it
does **not** send Enter. `go search`/`go find` instead sends Cmd+F.

**Done when:** in Slack, `channel <name>` presents the conversation/channel
picker with the name entered, then Enter opens the intended result.
The search-like picker is expected; a message-results search instead needs
inspection of active action overrides or Slack keyboard behaviour before any
new alias is considered. Do not equate this with pane grouping for numbers.

## W9. Talon restart/reload command discovery

**Status:** local discovery complete, 2026-10-29. No custom restart requested.

Read-only inspection of installed Community/default grammar and the running
Talon registry found no Talon-specific restart/reload/relaunch command and no
registered `app.restart`, `app.reload`, or `app.relaunch` action.
`app.quit` exists, but is a generic focused-application quit action, not an
automatic Talon restart.

For ordinary user-file edits, use Talon's automatic reload on save.
For a full process restart, quit via Talon's macOS menu and reopen Talon
manually; do not rely on voice to relaunch after its speech engine has exited.
Community provides `talon open log`, `talon open rebel` (REPL), and
`talon debug tags` in [talon_helpers.talon](../../community/plugin/talon_helpers/talon_helpers.talon).
`window reload` in VS Code reloads VS Code, not Talon.

**Evidence:** registry command values (`CommandImpl.rule`), not just opaque
registry keys, were inspected; no lifecycle actions were invoked.

## W10. Identify and scroll a selected application pane

**Status:** proposed spike, requested 2026-11-04; not implemented or validated.
**Effort:** S discovery, then a separately approved bounded live prototype.
**Related:** W5/W6 command reuse; [N8 grouping](numbers-and-menus.md) for
presentation only. Discovery does not depend on implementing general grouping.

**Goal:** target a visible scrollable pane, such as a channel list or message
history, without moving keyboard focus or accidentally scrolling its neighbor.
Use app-independent discovery and supported Talon/Community actions; no
application-name branches, native AX callbacks, or production background polling.

### Questions and prior-art check

1. What installed Community, AxKit, and repository actions already support
   scroll-area discovery, AX scrolling, or pointer-directed scrolling? Inspect
   their actual contracts and active grammar before adding an action or alias.
2. Which visible panes expose `AXScrollArea`, `AXScrollBar`, directional
   actions, or another reliable scrollability signal? A large group/frame or
   a scroll-to-visible action alone does not establish that it is scrollable.
3. Can native/web wrapper duplicates be collapsed without merging independently
   scrollable nested regions? Can offscreen, covered and collapsed panes be
   excluded without dropping real regions?
4. Can a safe pointer point be verified inside the intended pane, accounting
   for overlays and nested children? A rectangle center alone is insufficient.

### B1. Read-only region inventory

Use an isolated REPL probe outside the production import tree. Scope discovery
to the focused application's focused window; inspect supported roles, actions,
frames, parent/child relationships and scrollbar metadata. Bound traversal by
time and node count; report truncation and errors explicitly, never as a
complete empty inventory.

Capture only sanitized structural metadata and timings; do not persist message,
mail or contact content, window titles, or account details. Establish an
in-memory expected region list with the user for each fixture:

| App / fixture | Required independently targeted regions |
|---|---|
| Slack, channel with enough content | Channel/sidebar list; conversation history |
| Teams, chat with enough content | Chat/channel list; conversation history |
| Outlook, Mail | Folder list; message list; reading pane where independently scrollable |
| Outlook, People | Contact list; details pane where independently scrollable |
| Finder, long list | Native list scroll area (non-messaging regression fixture) |
| A fixture above with nesting/overlay | Nested scroll container and a covered or partially visible pane |

Record absent/short/non-scrollable regions as such; do not invent a successful
test where the fixture cannot move. Cold/warm discovery timings: three repeats
per fixture, counts and required-region coverage. Initial usability target:
discovery under 1 second; report overruns rather than cutting coverage to pass.

### B2. Bounded scrolling prototype (approval required before movement)

First present B1's inventory and the proposed command/selection behavior.
Candidate grammar, not registered commands: `show scroll areas`, then
`scroll area <number> up/down`. Persistent selection, semantic pane aliases,
horizontal scrolling and continuous scrolling are out of scope unless
separately approved. Check collisions with existing numbers/scroll commands.

Prototype one bounded vertical step using an exposed directional AX action
only if its behavior is verified. Otherwise evaluate an existing supported
pointer-scroll action at a verified hit-tested point inside the target.
Never click to focus, drag a scrollbar, select an item, or send a key to an
unverified focus target as a fallback. Reject ambiguous/covered/unreachable
regions with a visible explanation rather than scrolling a guessed pane.

For pointer scrolling, preserve the original pointer and restore it in
`finally`; abort on app/window changes. If the user moves the pointer during
the operation, do not fight that movement with an unconditional restoration.
Revalidate the selected region immediately before the action; do not reuse an
old numbered element after refresh/window changes.

### Validation matrix and measurable gates

For each independently scrollable required region in B1:

- Test both directions from the middle and at the top/bottom boundaries, three
  repetitions per direction. Record requested action, actual target movement,
  neighboring-pane movement, latency, and errors.
- Verify movement with before/after scroll values or visible-child geometry;
  if these are unavailable, use user-confirmed visual evidence. An action
  returning successfully does not prove that the correct pane scrolled.
- At a boundary, verify no scroll chaining into an ancestor or adjacent pane.
  If safe behavior cannot be established, mark that region/backend unsupported.
- Confirm keyboard focus, selected chat/message/contact, active app/window and
  pointer are unchanged, except for intentional viewport movement. Stop on any
  selection, message mutation or unexpected navigation.
- Repeat after resizing, opening/dismissing an overlay, replacing a view,
  switching windows/apps, and hiding/reopening region labels. Old numbers must
  be invalidated; covered/removed targets must fail clearly without movement.
- A nested target must scroll independently; targeting its parent must not
  silently scroll the child instead. Include partially visible and duplicate
  wrapper fixtures and a window with no scrollable content.

**Pass:** every user-marked required region is either correctly identified and
scrollable in both directions, or explicitly documented as unsupported with
evidence. Supported cases have zero wrong-pane scrolls or selection/focus
changes across the matrix. Missing required regions cannot be called full
cross-app success. Report per-app/backend limitations and cold/warm timing,
not just an aggregate success percentage.

**Automated tests if implementation is selected:** structural discovery and
duplicate/nested-region handling; visibility and ambiguous hit tests; stale
region/window identity rejection; direction mapping and boundary behavior;
pointer restoration on success/error and user movement; explicit failures;
label/grammar lifecycle cleanup. Mock tests do not substitute for the live
matrix. Check existing application-number commands and ordinary scrolling for
unchanged behavior.

### Decision, cleanup and rollback

Record a per-fixture evidence table and choose reuse, a minimal generic
implementation, narrower documented support, or no change. Obtain user
approval before promoting the prototype. Do not silently add app-specific
adapters or claim semantic names work when AX labels are missing/ambiguous.

Live scrolling necessarily changes viewport position: agree on fixtures and
restoration beforehand. Record starting scroll state in memory and restore it
when supported; otherwise report that exact restoration is unavailable and
obtain approval before movement. Hide diagnostic labels, restore focus/pointer
where safe, unregister temporary callbacks and remove the isolated probe when
done. Production rollback removes only W10's adopted changes, preserving
unrelated navigation and the Outlook/active-menu investigations.
