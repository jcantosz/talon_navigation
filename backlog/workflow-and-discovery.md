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
