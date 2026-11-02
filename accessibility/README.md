# Application control numbers

The application-number collector labels supported pressable controls in the
focused window. When macOS exposes an active menu, that menu replaces the
window as the numbered surface. While a session is active, a lightweight
active-menu check detects menus opened or dismissed by mouse as well as by
voice; an unchanged menu state does not trigger a window-tree query. Custom
popovers that macOS does not expose as an active accessibility menu are not
covered by this detection.

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
VS Code's pressable groups inside non-pressable rows keep their existing
selection behavior.

This is a heuristic, not proof that the child will perform the desired action:
accessibility metadata does not establish an action's semantics. Ambiguous
children, small buttons, disabled or hidden groups, and children extending
more than one point outside the row are not substituted. If the selected child
reports an activation error, the session reports it rather than silently
pressing the row instead. When a control still does not activate as expected,
**move mouse to &lt;number&gt;** followed by a click remains an alternative.
