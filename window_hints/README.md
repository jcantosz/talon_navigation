# Window hints

Accepted pane-label feature for the focused macOS application window. It uses
Talon's native label rendering and command grammar, not a custom overlay.

## Commands

- **window hints**: show the configured profile, or named generic AX containers
  when the application has no profile.
- **window hint numbers**: show numbers for generic AX containers.
- **window hints all**: show the broader structural generic candidate set.
- **hover files**, **hover tabs one**, **hover editor two**, etc.: existing
  label commands move to the named target's centre.
- **hide labels**: dismiss hints.

When a profile is selected, all three show commands currently use that
profile's configured label mode and targets. The numbers/all variants only
differ for applications without a profile.

VS Code selects `vscode_named` in [vscode.talon](vscode.talon). Its current
targets are search, activity bar, manage, files, each tab strip, each code
editor, an optional bottom panel, and the secondary sidebar (named chat).
Repeated targets are named **tabs one / tabs two**, **editor one / editor two**.
A singleton has no number. Numbering follows AX tree order, not a guaranteed
left-to-right order.

## Profiles

Profiles are JSON data in [profiles/](profiles/); no application branches are
needed in the traversal. An application context selects one with:

```talon
settings():
    user.window_hints_profile = "vscode_named"
```

Each entry defines a `name`, `match`, optional `scope`, and optional
`max_depth`. See [profiles.py](profiles.py) for the validated schema.
`scope: "self"` targets the matching element; an ancestor matcher targets the
nearest matching ancestor. Depth filters the collected nodes, not the walk
itself. Profile mode `labels: "names"` uses custom centre labels; `numbers`
uses original pane rectangles. Optional `tiles` enables coverage/overlap
validation for layouts intended to fill the window.

## Implementation

| File | Purpose |
|---|---|
| [window_hints.py](window_hints.py) | Actions, focused-window collection, diagnostics and error reporting |
| [profiles.py](profiles.py) | Pure profile validation, matching, target resolution and coverage |
| [core.py](core.py) | Pure generic pane rules and geometry |
| [labels.py](labels.py) | Named `ui.Element` proxies with 12x12 centre geometry |

Collection reuses the bounded AX inventory walker and focused-surface helper
from [accessibility/](../accessibility/). Window hints do not change the
production application-number session.

## Reliability and limits

- Current VS Code single/split-editor layouts have screenshot and command
  replay validation. Automated tests cover geometry, profiles, duplicate names,
  original-reference action routing and synchronous error fallback.
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
  Hover works independently of `AXPress`. Scoped numbering and pane-focus
  commands are not implemented.
- VS Code selectors depend on internal DOM classes. Notebooks, diffs, webviews,
  rearranged views, relaunch and future app versions need additional validation.
  The name `chat` means the secondary sidebar, even when it hosts another view.
- Hints are snapshots, not continuously refreshed. Run **window hints** again
  after layout changes; hide them before switching windows.
- Generic AX discovery is best-effort and does not guarantee every pane.

The [development and validation log](../backlog/window-hints.md) retains the
experiments and rejected approaches. Acceptance does not remove these limits.
