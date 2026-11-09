# Window hints

Accepted pane-label feature for the focused macOS application window. It uses
Talon's native label rendering and command grammar, not a custom overlay.

## Commands

- **window hints**: show the configured profile, or named generic AX containers
  when the application has no profile.
- **window hint numbers**: number the same configured targets at their centres,
  or use generic AX containers without a profile.
- **window hints all**: number the configured targets, or show the broader
  structural generic candidate set without a profile.
- **hover files**, **hover tabs one**, **hover editor two**, etc.: existing
  label commands move to the named target's centre.
- **hide labels**: dismiss hints.
- **scroll channels down**, **scroll mail up two**, **scroll message down**:
  scroll the named section. Optional amount is 1–20 existing wheel units,
  default one. Up/down/left/right mean viewport navigation in that direction,
  accounting for the macOS natural-scroll preference.
- **number channels**, **number mail**, **number message**: replace section hints
  with production control numbers scoped to that section. Use existing number
  selection commands. **show application numbers** returns to the full window;
  **hide numbers** ends the session.

Profiles define targets, not rendering modes. Names and numbers share the same
centre geometry, real-group action routing and original-element fallback.

VS Code selects the single [vscode profile](profiles/vscode.json) through the
central mapping in [window_hints.talon](window_hints.talon). Its current
targets are search, sidebar, manage, files, each tab strip, each code
editor, an optional bottom panel, and the secondary sidebar (named chat).
Repeated targets are named **tabs one / tabs two**, **editor one / editor two**.
A singleton has no number. Numbering follows AX tree order, not a guaranteed
left-to-right order.

Slack's channels layout selects the [slack profile](profiles/slack.json):
**search**, **sidebar**, **manage**, **channels**, **messages**, optional
**thread**, and **compose**. Multiple compose inputs become **compose one** /
**compose two**; a single input remains **compose**.

Outlook's mail layout selects the [outlook profile](profiles/outlook.json):
**search**, **sidebar**, **inboxes**, **mail**, **message**. The mail list and
message body use their visible AX container/scroll viewport, not their much
larger offscreen content frames.

In either app, say **window hints** (or **show sections**), then e.g.
**hover channels**, **hover compose two**, **hover inboxes**, or **hover message**.
**hide sections** also dismisses the labels. Profiles activate by exact macOS
bundle ID. Only these current layouts have been validated; there is no
view-state detection for Slack's other sections or Outlook's Calendar/People.
Shared markers may still match there, but do not imply those views are supported.
Absent optional panes are omitted, not guessed.

## Refresh and section actions

Visible section hints follow supported Talon application-activation and
window-focus events, coalesced with a 100 ms delay so application settings can
settle. Old labels disappear immediately. Named/numbered rendering mode is
preserved. Hiding or replacing hints with another label feature cancels refresh;
changing focus never resurrects dismissed hints or overwrites control numbers.
A cancelled or superseded walk cannot publish late labels.

Say **show sections** first to discover sections and retain their real AX roots.
Scroll and number commands reuse those references, checking the current app,
window, profile, hidden state and live frame without another profile load/window
walk. Focus changes invalidate them even after labels have been hidden or handed
to control numbers. Missing/ambiguous names, incomplete discovery and invalid
references fail visibly; show sections again after a layout change.

Scrolling checks final focus/ownership, including the root's owning window. It moves the
pointer without clicking only when needed; subsequent scrolls at that centre
do not move it again. Native `ctrl.mouse_scroll(pos=...)` targets the event
explicitly, so asynchronous pointer movement needs no completion sleep or polling.
The pointer stays there. Open menus refuse scrolling with a notification.
Like ordinary wheel commands, a non-menu overlay covering that point may receive
the event. Per-scroll AX hit-testing is intentionally omitted: Slack exposes
transient full-window AX overlays while scrolling that caused false refusals.
This policy was explicitly approved after the real-wheel validation failure.
This does not set keyboard focus.
Direction normalization reads only `com.apple.swipescrolldirection` through
macOS `defaults` once after showing/refreshing sections; repeated scrolling uses
the cached value. Show sections again after changing the OS preference.
Failed/non-boolean reads are not cached and block scrolling rather than guessing.
Native wheel dispatch reuses the positive community settings
`user.mouse_wheel_down_amount` (vertical, default 120) and
`user.mouse_wheel_horizontal_amount` (default 40), multiplied by the spoken amount.
Adjust those settings to change distance. Custom community wheel-action overrides
are not invoked; no artificial scrolling animation is added.

Scoped numbering reuses the application-control query, filtering, row anchors,
selection, menu/back behavior and event refresh. The real section is the query
root, with controls clipped to its viewport. Native tables at that root or
immediately beneath it use `AXVisibleRows` and their header, not all offscreen
rows. A nested pressable AXCell under a non-pressable row is a control; it is
not duplicated when its row is itself pressable. Outlook mail rows expose these
cells in the ordinary AX tree, not a separate tree.

Startup performs one section resolution/collection. Before scoped selection,
only the selected target's signature, enabled/hidden/pressable state, section
ancestry and viewport overlap are checked, together with current focus/window.
There is no full section-control query. Changed/recreated/detached targets refuse
the old number and request fresh labels; unrelated sibling changes alone do not
block an unchanged target. Pending refreshes refuse selection until new numbers
are ready. Arbitrary non-menu occlusion is not guaranteed by AX state checks;
Electron hit tests can return generic ancestors at legitimate row locations.
Scrolling hides stale numbers and requests the existing session's
refresh. Empty/inaccessible sections stop with notification, not full-window
fallback. Mail-cell AXPress is exposed and numbered, but live mail activation
has not been tested to avoid opening or marking messages read.
An initially empty section can retry for up to the normal two-second startup
window; an empty section after successful numbering stops immediately.

## Profiles

Profiles are JSON data in [profiles/](profiles/); no application branches are
needed in the traversal. All application associations live in the single
`user.window_hints_applications` setting in
[window_hints.talon](window_hints.talon), using comma-separated exact
`bundle=profile` entries. For example:

```talon
settings():
    user.window_hints_applications = "com.microsoft.VSCode=vscode, com.tinyspeck.slackmacgap=slack, com.microsoft.Outlook=outlook"
```

The checked-in mapping also preserves the seven macOS variants formerly covered
by the Community `app: vscode` context. This is a fixed list, not a dependency on
future Community alias changes; additional bundle IDs must be added explicitly.
No per-application hint-selector Talon files are needed.

The mapping is parsed and its profile paths checked once per setting value.
Repeated scrolling/section resolution does not read profile files or scan the
directory. Mapping edits take effect on the next resolution/refresh; show sections
again to discover targets under the changed profile. Focus refresh selects the
new application's mapping automatically. Unmatched apps (or an empty mapping)
use generic hints. Invalid entries, duplicate bundles and missing profile paths
report errors instead of guessing; the chosen JSON is validated during rendering.
The superseded `user.window_hints_profile` setting has been removed.

Each entry defines a `name`, `match`, optional `scope`, and optional
`max_depth`. See [profiles.py](profiles.py) for the validated schema.
`scope: "self"` targets the matching element; an ancestor matcher targets the
nearest matching ancestor. Matchers support exact `role`, `subrole`, `dom_id`,
native AX `identifier` and `help`, `title`, and `description`, plus required
`classes` and `class_suffix`.

The profile-level `max_depth` bounds collection (root depth is zero); an entry's
`max_depth` further filters its marker. Profile collection includes but does not
descend into AXTable, AXOutline, AXTextField or AXTextArea: these are content
boundaries, preventing huge lists or repeated text-field chains from exhausting
the walk before later panes. Select their containing ancestors or the controls
themselves, not children within those roles. AXWebArea remains traversable for
Electron apps. Generic hints and diagnostic collection retain their existing
walk behavior. The show command selects named or numbered centre labels.
Optional `tiles` enables coverage/overlap
validation for layouts intended to fill the window.

## Implementation

| File | Purpose |
|---|---|
| [window_hints.py](window_hints.py) | Actions, focused-window collection, diagnostics and error reporting |
| [profiles.py](profiles.py) | Pure profile validation, matching, target resolution and coverage |
| [core.py](core.py) | Pure generic pane rules and geometry |
| [labels.py](labels.py) | Named `ui.Element` proxies with 12x12 centre geometry |
| [lifecycle.py](lifecycle.py) | Visible-hint ownership, focus refresh and cancellation |
| [sections.py](sections.py) | Current-window section references and invalidation |
| [section_actions.py](section_actions.py) | Verified positioned wheel scrolling and cached direction preference |

Collection reuses the bounded AX inventory walker and focused-surface helper
from [ax/](../ax/README.md). Window hints do not change the
production application-number session.

## Reliability and limits

- Current VS Code single/split-editor layouts have screenshot and command
  replay validation. Automated tests cover geometry, profiles, duplicate names,
  original-reference action routing and synchronous error fallback.
- Slack channels (eight targets, including two compose inputs) and Outlook mail
  (five targets) have live screenshot validation, named hover command replay
  within one logical pixel of every centre, and numbered-label count checks.
  Their bounded walks completed without truncation or AX errors. Synthetic
  regression fixtures contain only structural selectors, not message content.
- Focus-switch replay verified Slack/Outlook refresh in both rendering modes,
  explicit hide, replacement by native named/numbered labels and scoped numbers.
  Later current-layout queries numbered 36 Slack channel controls, 12 Outlook
  mail cells plus three header controls, and 26 visible message links.
- Cropped local screenshots verified Slack channel-list and Outlook mail-list
  scrolling. Outlook message scrollbar values verified direction normalization
  and inverse restoration. Scrolling either Outlook viewport left the other
  viewport's screenshot byte-identical. No mail-cell presses were performed.
- Performance validation verifies warmed
  scrolling without walks, profile reads, subprocesses, sleeps or redundant
  pointer movement; single-collection numbering startup; and targeted selection
  validation without recollecting the section. These are command-dispatch
  measurements, not speech-recognition or UI-animation timings.
- The proxy wraps a real copied AX reference and overrides only its displayed
  name and geometry. Actions delegate to the original element; no native AX
  attributes are changed and no unsupported actions are fabricated.
- **Compatibility risk:** constructing that proxy uses Talon's private `_ref`
  field. A Talon upgrade can break it. Proxy/render failures log and notify,
  then retry original group labels; custom geometry failures use original
  geometry. This fallback may lose custom names or centre placement. Errors
  deferred by Talon after the show call are not caught by this retry.
- **Selection is not focus:** many groups lack `AXPress`. Talon rejects
  selection on those groups; there is no automatic click/focus substitute.
  Hover and wheel scrolling work independently of `AXPress`. Scoped numbering
  labels actionable descendants, not the group itself. Keyboard pane-focus
  commands are not implemented.
- VS Code and Slack selectors depend on internal DOM classes; Outlook uses
  native semantic attributes. App versions, localization and other views need
  revalidation. Notebooks, diffs, webviews,
  rearranged views, relaunch and future app versions need additional validation.
  The name `chat` means the secondary sidebar, even when it hosts another view.
- Hints refresh on application/window focus, not on every internal layout or
  view change. Run **window hints** again after rearranging the current window.
- Generic AX discovery is best-effort and does not guarantee every pane.

The [development and validation log](../backlog/window-hints.md) retains the
experiments and rejected approaches. Acceptance does not remove these limits.
