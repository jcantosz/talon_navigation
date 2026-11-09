# Debug commands and incident recording

This directory is reserved for opt-in diagnostic commands and their recording
implementation. Nothing in this directory currently enables recording.
Generated incident files must be kept separate from source and ignored by Git.

## D1. Navigation incident flight recorder

**Status:** implementation spike requested 2026-11-05; design only.
**Effort:** S capability check, M bounded prototype and validation.
**Incident:** [N19](../backlog/numbers-and-menus.md#n19-slack-numbering-disappears-after-channel-selection-touch-and-scroll).

### Goal and non-goals

Explain the state transitions preceding intermittent application-number
failures, without changing navigation decisions or introducing another source
of failures. Failure-only logging is insufficient: preserve the lead-up.

Provide `debug on` and `debug off` commands, subject to command-collision checks.
Do not implement a navigation fix, general system telemetry, speech recording,
AX tree snapshots, application adapters or automatic reproduction.

### D1a. Prove the available observations

Before implementing the recorder:

1. Inspect existing debug commands, logging, lifecycle hooks and supported
   Talon APIs. Reuse existing mechanisms; do not modify Community.
2. Verify a lightweight supported source for macOS frontmost-app identity
   independent of `ui.active_app()`. Record source and limitations. Do not
   add subprocess polling or unsupported native callbacks. If no suitable
   source exists, explicitly mark independent focus unavailable; do not claim
   the recorder can distinguish stale Talon focus from real OS focus.
3. Determine whether supported events expose pointer clicks, scrolling and
   app/window changes without globally intercepting commands. Record gaps;
   never infer a `touch` or scroll event just from pointer movement.
4. Establish which IDs can correlate app instances, windows, sessions and
   operations without retaining AX objects or text. IDs need only be stable
   within a recording session; avoid raw object representations.
5. Measure individual focus and hit-test calls. No periodic AX hit testing or
   window enumeration until cost and supported thread/lifecycle use are proven.

**Exit:** a capability/cost table identifying verified observations, unavailable
observations and candidate hooks. Resolve the recording backend/thread model
here, before adding concurrency. Do not invent independent focus evidence.

### D1b. Small opt-in prototype

Keep the buffer, sanitization, persistence and command registrations under
`debug/`. Navigation instrumentation may call a minimal recording boundary,
but navigation must not depend on diagnostic return values. Avoid circular
imports and global logging-handler interception.

**Lifecycle**

- Disabled by default, including after reload/restart.
- `debug on` starts a new recording session; repeated enable is idempotent.
- `debug off` cancels jobs, unregisters listeners, clears the in-memory buffer
  and releases references. Repeated disable is safe. Explicit off cancels
  pending post-incident collection; already written reports remain on disk.
- Reload/unload performs the same cleanup. No callbacks from a previous module
  instance may survive or produce duplicate records.

**Bounded history and schema**

- Retain at most the preceding 60 seconds, 2,000 events and 1 MiB of sanitized
  serialized event data, evicting oldest entries when any bound is exceeded.
  Include eviction counters and actual history coverage in reports.
- Each event includes monotonic ordering/time, UTC correlation time, recording
  ID, operation/session ID, event kind and explicit source.
- Record before/after show, selection, label hiding, refresh, collection,
  rendering and session stop. Capture counts, durations, exception type,
  call-site identifier, stop reason, session owner and observed app/window
  identity. Record why a refresh is skipped as well as why a session stops.
- Reuse already-read state where possible. Any additional observation is
  explicitly diagnostic and cannot alter the navigation input.
- Collect focus/window transitions through verified supported events. If
  sampling is needed, start at no more than once per second and record gaps;
  no full-tree queries or repeated window inventories.
- At operation boundaries, evaluate pointer position/target ownership and
  focused-window availability only if D1a proves the calls acceptably cheap.
  Mark unavailable/failed observations distinctly from legitimate `None`.
- Record observed menu role/frame and owner, not menu text. Optional costly
  post-failure probes must be bounded and must not delay the original error.

**Privacy**

Use an allowlist of primitive fields. Exclude message text, channel names,
window titles, contact/account details, downloaded filenames/paths, dictated
phrases, clipboard contents and raw AX objects. Arbitrary exception strings
may contain content: persist exception type and sanitized stack locations,
not unrestricted `str(error)` or locals. Correlate with the existing Talon
error using incident ID and timestamp, without copying unrelated log content.

**Incident capture**

- Trigger on navigation query/selection/render failures and unexpected empty
  results. Record ordinary app-switch stops as context, not automatically as
  errors. Record recovered/retried exceptions without creating a report for
  every retry; one failing operation produces one correlated incident.
- Provide a manual `debug capture` action for symptoms the code cannot detect,
  such as labels disappearing without an exception. Confirm its spoken form
  against installed grammar.
- Freeze pre-incident history immediately; collect up to five seconds of
  post-incident events while debug remains enabled. Save an initial report
  promptly and finalize it atomically, so a crash during that interval does
  not erase the preceding evidence.
- Include report schema version, trigger, error correlation, enabled
  capabilities, dropped events, collection failures and incomplete status.
- Coalesce error bursts and bound pending captures; propose one active capture
  and at most one new incident per ten seconds, recording suppressed counts.
- Use a dedicated ignored output directory, atomic writes and bounded
  retention: at most 20 reports, 2 MiB per report and 20 MiB total. Prune only
  recognized recorder-owned report files, never arbitrary directory contents.

**Failure containment**

Diagnostic collection and persistence failures must not escape into navigation,
swallow its errors, recursively trigger captures, or change its result.
Contain exceptions only at the diagnostic boundary: emit one standard log
error/notification, disable recording and clean up its resources. Do not silently
substitute success. Validate storage/threading choices before using them;
no unbounded work queue or worker thread performing unverified Talon UI calls.

### D1c. Validation gates

Use existing test tooling. Test the pure buffer/report logic with a fake clock,
and integration boundaries with existing Talon fakes. No live destructive
fault injection or intentional user-app errors.

| Area | Required validation |
|---|---|
| Off mode | No diagnostic jobs/listeners, observations or writes; navigation results/exceptions unchanged |
| Lifecycle | Enable/disable twice; off during pending capture; reload/unload; no duplicate jobs or retained old session |
| History | Events before and after a synthetic failure present and ordered; 60-second/count/byte limits and eviction counters correct |
| Correlation | One incident per failing operation across retries; distinct operations identified; burst suppression and incomplete reports explicit |
| Error containment | Collectors throw, disk is unwritable/full, serialization/write/rename fails; original navigation outcome preserved and recorder disables once |
| Privacy | Sensitive sentinel strings injected through titles, values, exception messages and objects never appear in reports |
| Retention | File/count/total-byte limits; unrelated files untouched; interrupted writes do not replace a valid report with corrupt data |
| State transitions | Fake Talon/macOS focus agreement and disagreement; focus changes during label hide; no focused window; stale menu; zero targets; ordinary app switch |

**Live validation, with approved non-destructive fixtures:**

1. Prove collection is running using advancing event counters, not a startup
   message. Switch apps intentionally and verify known transitions in a manual
   capture. Verify any independent focus source against those transitions.
2. Verify a controlled recorder test incident includes the preceding known
   events and following five seconds. This exercises diagnostics only, not a
   deliberately broken Slack/Outlook state.
3. Repeat normal show/refresh/hide and channel selection in Slack, Teams,
   Outlook, Word, Finder and VS Code using agreed fixtures. Compare enabled/
   disabled target identities/order and outcomes on unchanged UI states.
   Do not send messages or mutate mail/contact data.
4. For N19, observe ordinary use or repeat the agreed selection -> touch ->
   scroll -> refresh sequence. Save manual capture if no automatic trigger
   occurs. Record download-notice/unread-badge presence by user annotation;
   do not recreate downloads or unread state without permission.
5. If reproduced, preserve the broken state and capture before/after the click
   that restores it. A report must distinguish measured evidence from guesses.

**Overhead gate:** compare off/on in interleaved runs on unchanged fixtures:
at least 20 show/refresh operations per mode, recording p50/p95. Proposed
acceptance: added p95 latency no greater than 20 ms or 5% of baseline, whichever
is larger; idle CPU increase under one percentage point averaged over five
minutes; buffer within its explicit bounds. Report raw samples and measurement
method. If these targets fail, reduce observations or stop; do not declare
overhead negligible from inspection. Measure incident writes separately.

### Decision and rollback

Promote only after the user reviews capability gaps, fault tests, overhead and
an example sanitized report. Capturing an incident is not a diagnosis: N19
still requires the first incorrect state transition to be established, followed
by reproduction or decisive evidence and separate fix validation.

Rollback removes only D1 instrumentation and command registrations. Existing
navigation behavior, error reporting and unrelated debug snapshot commands
must remain intact. Do not move existing diagnostics in this spike merely to
consolidate folders.
