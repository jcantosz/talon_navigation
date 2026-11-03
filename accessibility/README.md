# Application control numbers

The application-number collector labels supported pressable controls in the
focused window. When macOS exposes an active menu, that menu replaces the
window as the numbered surface. While a session is active, a lightweight
active-menu check detects menus opened or dismissed by mouse as well as by
voice; an unchanged menu state does not trigger a window-tree query. Custom
popovers that macOS does not expose as an active accessibility menu are not
covered by this detection.

Flat menus exposing direct `AXMenuItem` children are collected without walking
their submenu trees, and only items overlapping the popup frame are numbered.
Other menu structures retain the AX query path. If the reported active menu
has no usable frame, the session uses a unique visible menu in the focused
window when one can be found; it does not guess between multiple visible menus.
The resolved menu is cached while both the reported menu and resolved frame
remain valid, and is shared by selection, refresh, Back, and hover checks.

Selecting an `AXTab`, or an `AXRadioButton` directly inside an `AXTabGroup`,
retains the session and requests refreshed numbers, as do expanding controls
such as combo boxes and popup buttons. Ordinary
non-expanding selections dismiss numbers even if Talon's native selection
does not hide them. A reported activation failure on an ordinary control stops
the session and cancels pending refreshes. An expanding control that reports
`ActionFailed` keeps the session and requests the same post-press refresh,
because some applications open the popup and still report failure. Failed
presses are never retried because an application may have partially performed
the action.
Menu polling and refreshes are paused during selection so native label hiding
cannot erase a menu that a reentrant refresh just numbered. Expanding selections
invalidate the previous render before requesting their post-press refresh.

## Implementation layout

| Module | Responsibility |
|---|---|
| [inventory.py](inventory.py) | Talon actions, settings, tags, event registrations, and ownership of the current session and activation overrides |
| [controls.py](controls.py) | AX queries, control and row filtering, clipping, deferred web areas, and focused surfaces used by diagnostics |
| [activation.py](activation.py) | AX interface activation, bundle exclusions, and process identity checks |
| [application_session.py](application_session.py) | Rendering, refresh scheduling, safe selection, menu transitions, and Back |
| [inventory_core.py](inventory_core.py), [debug_snapshots.py](debug_snapshots.py), [snapshots.py](snapshots.py) | Diagnostic tree traversal, printing, and snapshot output, not the numbered-control query path |

The three extracted implementation modules do not register Talon commands or
contexts. The entry point supplies the session's contexts and stop callback, so
the session does not import the entry point. Each session retains its own
contexts for reload cleanup.
The menu transition state machine stays together rather than being spread over
mixins or mutually dependent modules. Voice commands, settings, query budgets,
control ordering, and per-application overrides are unchanged.
Control roles come from the Talon-independent [shared role definitions](../lib/roles.py);
diagnostic classification still does not implement the runtime row or clipping
rules. The session shares guarded submenu hovering and menu transition timing
through [label helpers](../lib/labels.py), but owns its focus validation and
return-to-window behavior.

Runtime tests follow the same boundaries: `test_application_collection`,
`test_application_rows`, `test_application_web_areas`,
`test_application_activation`, `test_application_session`, and separate menu
scope, selection, and Back modules. Shared Talon doubles live in
[accessibility_support.py](../tests/accessibility_support.py); highlighting and
diagnostic runtime tests are independent. Run the application tests with:

```sh
uv run python -m unittest discover -s tests -p 'test_application_*.py'
```

The experimental word highlighter and diagnostic commands still have active
Talon bindings; their names or lack of Python callers do not make them dead code.
The highlighter will be retained and refined; validation and potential promotion
are tracked in the [highlighting backlog](../backlog/highlighting.md).

## Menu navigation constraints

In application numbers and menu numbers, an item's number can be anchored
to accessible text inside it so a full-width menu item does not put its
badge over unrelated controls. The logical menu item, not the text, receives
`AXPress`. Menu labels by name retain their native label placement.

Some submenu items advertise a press action but only open on hover. After a
numbered selection (or a uniquely matching menu label by name), if no menu
transition appears, the session may move the pointer over that item once.
This fallback requires an `AXMenuItem` explicitly marked as having a popup,
an item not explicitly disabled or hidden that is still inside the active
menu with usable frames, the same focused app and window, and a pointer that
has not moved since the selection. The fallback never clicks automatically.

**Numbers back** first attempts to return one menu level. If an accessible
parent does not respond, it attempts Escape instead and reports when this
closes the whole menu and restores application numbers. Some applications,
including Slack for certain submenus, cannot return one level via their
accessibility or keyboard actions. If the fallback also fails, the session
reports the unsuccessful transition.
**Menu back** uses the same one-level approach but, after a failed return,
attempts to close the menu and relabel the application menu bar instead.
Status-panel navigation shares the menu ancestry and opener checks, but does
not use the hover fallback.

## Row activation constraint

Some applications expose a pressable `AXRow` whose own `AXPress` does not
navigate, while a large child group performs the intended action. To avoid
app-specific control paths, row activation uses this structural rule at
selection time:

- The row must have exactly one direct child advertising `AXPress`, counting
  children of all roles. That child must be an `AXGroup` that is not explicitly
  disabled or hidden and has a finite, positive-size frame.
- The child frame must be contained in the row frame, allowing one point of
  tolerance, and their overlap must cover at least 80% of both the row's
  width and its height. The row frame must also be finite and positive-size.
- If all conditions hold, the child's `AXPress` is used instead of the row's.
  Otherwise the original row/native selection behavior is retained. The row
  remains a single numbered target; the child is not separately numbered.

A row's badge may be drawn on text inside the row for better placement, but
the labelled text, logical row, and activation target are kept separate.
The badge search does not enter another independently numbered target's
subtree, but still traverses unnumbered row/group wrappers. If candidate badge
anchors collide, or borrow another target itself, the affected badges use
their original target elements instead. Target order and child-group activation
are unchanged. These ownership checks use accessibility-element equality,
not application-specific selectors.
An unnamed arrow button contained in an unpressable combo box can use the
combo box's larger frame for badge placement, provided it is the combo box's
only pressable child. Selection still presses the arrow, not the combo box.
Collision checking skips unchanged anchors and limits accessibility-element
comparisons to candidates with matching roles and frames, avoiding all-pairs
cross-process comparisons for large menus.
VS Code's pressable groups inside non-pressable rows keep their existing
selection behavior.

This is a heuristic, not proof that the child will perform the desired action:
accessibility metadata does not establish an action's semantics. Ambiguous
children, small buttons, disabled or hidden groups, and children extending
more than one point outside the row are not substituted. If the selected child
reports an activation error, the session reports it rather than silently
pressing the row instead. When a control still does not activate as expected,
**move mouse to &lt;number&gt;** followed by a click remains an alternative.
