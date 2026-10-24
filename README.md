# Talon Navigation

macOS application-menu/status-bar navigation and local Talon command reports.
Install this repository anywhere under Talon's `user` directory. Menu navigation
requires macOS accessibility support and Talon's native labels API.

## Formatted dictation

On macOS, **type**, **literal**, and **say** followed by dictation use Talon
Community's existing `<user.prose>` capture for punctuation, spacing, and
capitalization, then record the result in Community's phrase history and use
`insert()`, just like the **phrase** command.
For example, **say hello comma world period** inserts **Hello, world.**
This requires Talon Community and avoids requiring an accessible text field,
which can be unreliable in editors such as VS Code.

This overrides the default command prefixes without modifying the default
package. It does not change unprefixed dictation mode or the **phrase** command.
It uses Community's prose formatting rather than native AX-aware dictation;
native last-dictation correction/selection tracking is not retained.
The original `type <phrase> | literal <phrase> | say <phrase>` rule is also
overridden exactly, so plain phrases cannot fall through to `dictate.phrase()`.
That plain-phrase path uses Talon's existing word replacements, records history,
and calls `insert()` directly. Existing formatter commands are left unchanged.

- **Dictate long**: allow two seconds of silence before ending an utterance.
- **Dictate short**: remove that override and restore your normal configured
  speech timeout (not a hard-coded value).

Say either timeout command as a separate utterance before dictating. The
selection persists until changed or Talon reloads these definitions. While long
is enabled, it affects all speech, not only the three dictation prefixes.

## Menu navigation

- **Show menu labels** or **menu labels**: label the active application's menu by title.
- **Show menu numbers**: label it by number.
- Say the displayed title or number to select an item. Each submenu replaces the
  previous labels and keeps the same label style.
- **Menu back**: close one menu level and relabel the parent.
- **Hide menu labels** or **hide menu numbers**: stop labeling.

The exact `show menu numbers` rule uses a dedicated tag so it overrides the
generic default command without modifying the default package.
`Go back` is also an alias while menu labels are active, but overlaps with browser
navigation commands; `menu back` is less ambiguous.

## Status icons and panels

- **Show status labels**: label the accessible top-right menu-bar icons by name.
- **Show status numbers**: label those icons by number.
- If a status menu or accessible system panel is already open, either command
  labels its controls instead of resetting to the icons. Repeating the command
  switches title/number style on the current panel, including while it opens.
- Say a displayed title or number to open that icon's menu or panel. Its controls
  replace the icon labels in the same style.
- **Status back**: use an accessible Back button or close a nested native menu
  when available; otherwise close the panel and relabel the status icons.
- **Hide status labels** or **hide status numbers**: remove labels and stop
  navigation. This does not itself close the open panel.
- **Refresh status labels** or **refresh status numbers**: relabel the open panel,
  or freshly scan the visible menu bar when no panel is open.

From the first request, discovery hit-tests the menu bar at 8-point intervals,
finds status items' parent menu bars, and reads those parents' contents. Every
normal icon-show request performs a fresh scan, so new providers can be found
without a cache-expiry delay. App metadata is used only to associate discovered
parents with their owners; unrelated apps' accessibility trees are not queried.
Back navigation rereads the already-discovered parents.

There is no all-application discovery scan or legacy fallback. Accessibility
failures produce a notification. Unusually narrow or vertically offset custom
accessibility bounds can be missed by the scan.

Titles come from macOS accessibility information. Some third-party icons have
generic names such as `MenuBarItem`. Discovery verifies each icon's center against
screen hit-testing: items covered by the application's menu bar or hidden behind
other UI are not clickable targets, even if macOS reports an on-screen rectangle.
Long names can collide: Talon's native label
layout spreads badges downward and may omit badges when space runs out. Numbers
are preferable for a crowded menu bar. This feature does not reposition icons.

Selecting a panel button, checkbox, or switch performs its normal action, which
can change a system setting. Selecting a slider does **not** click its midpoint:
use **status increase &lt;label&gt;** or **status decrease &lt;label&gt;** for an
advertised accessibility increment/decrement action. **Status details
&lt;label&gt;** only invokes an explicitly advertised “show details” action; it
never substitutes a toggle. Unsupported controls or transitions without an
accessible replacement panel produce a notification.

Increase/decrease uses the label **on the adjustable control inside the panel**,
not the status icon or a button that opens the panel. For example, if the volume
slider is numbered **7**, say **status increase seven** or **status decrease
seven**. Labels stay visible, so the same command can be repeated without
showing labels again. Reaching the slider's minimum or maximum does not remove
labels. Value-only changes and tiny animation movements do not rebuild the
overlay; meaningful changes to the panel's controls still refresh it.
A normal checkbox/toggle does not become adjustable merely because it
has a label; unsupported adjustments notify without pressing it.

Panels differ between apps and macOS versions. Only accessible controls and
menus are supported; appearance on screen alone does not guarantee accessibility.
Discovery of already-open windows accepts accessible system dialogs/popovers
owned by status providers, not their ordinary document/settings windows. Back
from an adopted panel needs an identifiable opener or an advertised close action;
if neither is available, it notifies instead of guessing which icon to press.
Root icons are opened with a mouse click because some apps advertise an
accessibility press action that does nothing. Switching to an unrelated app
ends status navigation. Default Talon command files are not modified.

### Command aliases

Use whole-word alternatives: `(lab | label)` means either word, while
`[lab | label | num | number]` means one of those words or nothing.
For example, `move [to] [menu] [lab | label | num | numb | number] <number>`
accepts “move five,” “move menu label five,” and “move to menu number five.”
`lab[el]` does not join a suffix onto a word; Talon parses it as `lab [el]`,
which requires “lab” followed by an optional separate “el” token.

## On-demand command reports

Each command takes a fresh snapshot before opening its report in your default
browser. The active application and modes are captured **before** the browser
opens.

| Voice command | Starting view |
| --- | --- |
| **Talon commands report** | All installed voice-command rules |
| **Talon top level report** | First-word sections with expandable command definitions |
| **Talon conflicts report** | All duplicate, shared-phrase, and potential-overlap candidates |
| **Talon active commands report** | Rules in the active command registry at generation time |

All reports include search, package/status filters, source locations, context
restrictions, and **All at once** in the rows-per-page selector. The conflict
report also has separate tabs for duplicate grammar, shared phrases/templates,
and potential capture/list overlaps.

Reports are self-contained HTML files stored under
`~/.talon/reports/talon_navigation/`, outside the repository. Regenerating a report
replaces its previous snapshot. Files stay local; no external scripts, network
requests, or telemetry are used. Do not publish generated reports without
checking them: they contain your local command rules, app names, and source paths.

### What counts as a conflict

A shared first word is not a conflict or a formal Talon namespace. Duplicate
rules can be intentional overrides or belong to mutually exclusive apps.
“Active” does not mean a rule wins recognition.

The analysis expands aliases and optional words up to 256 combinations per rule.
Repeated or larger rules remain in the inventory and prefix index, but are marked
as excluded from phrase expansion. Potential reference overlaps approximate
captures/lists as one or more words and are not confirmed ambiguities. Dynamic
lists, capture-vs-capture intersections, future context combinations, phonetic
similarity, and full recognition precedence are not resolved.

## Lint and tests

Menu and status navigation share label rendering, active-context, polling, and
cancellation behavior through [`lib/labels.py`](lib/labels.py). Feature modules
own only their navigation-specific state and accessibility traversal.

The checker runs Ruff's Python syntax/lint checks, Python formatting checks, the
Tree-sitter Talon parser and Cursorless formatter, then all unit tests. It checks
only this repository and excludes dependencies and virtual environments.

Install development tools once using Python **3.10+** and Node **20+**:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci --ignore-scripts
```

On this Mac, the system `python3` is older. You can use Talon's bundled Python
instead; its bundle does not include the `ensurepip` wheel, so bootstrap the
environment with the existing Talon pip:

```sh
~/.talon/bin/python -m venv --without-pip .venv
~/.talon/bin/python -m pip --python .venv install -r requirements-dev.txt
npm ci --ignore-scripts
```

Run everything with one command from the repository root:

```sh
.venv/bin/python scripts/check.py
```

Checks are read-only by default. To apply import sorting and formatting fixes
before running the tests:

```sh
.venv/bin/python scripts/check.py --fix
```

Syntax errors fail the check and are not automatically rewritten. Every check
runs even if an earlier check fails; the script exits nonzero if any stage fails.
Missing development tools are reported explicitly. The Talon checker uses the
public formatter/parser APIs because the pinned upstream CLI assumes a nested
npm installation layout.

Static linting cannot guarantee that an action exists in your running Talon
installation or that speech precedence is correct. The menu-number exact-rule
regression test protects the known override, and live Talon checks are still
needed for runtime behavior.

### Tests only

From the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Tests use Python's standard library and mocked Talon APIs, so Talon does not need
to be running. They cover menu/status traversal and back navigation, status
parent-based discovery, slider safety, grammar analysis, report
views and HTML escaping, report regeneration, browser opening, and explicit
failure notifications. Test paths are relative to the repository, not a specific
user's installation.
Slider tests model Talon's inset hit rectangles, changing accessibility geometry,
and repeated adjustments without hiding or unnecessarily redrawing labels.

### Status discovery validation

[discovery.py](status/discovery.py) is the discovery path used by voice commands.
Its `discover` function
hit-tests menu-bar rows, walks to the status items' parent bars, then reads their
contents. It accepts the running Talon `ui` object plus the status module's
visibility and hit-test helpers, and reports elements, owning application
elements, parents, probe rows, probe query/empty-hit counts, and elapsed time.

[test_status_discovery_probe.py](tests/test_status_discovery_probe.py) compares
this approach with an all-provider reference using simulated accessibility
trees. It covers narrow icons, covered/hidden/disabled items, empty hits,
descendant hits, hidden bars, and monitors with different offsets and bar
heights. Tests also document the accepted limits: a sparse stride can miss a
narrow icon whose parent has not otherwise been found, and a single probe row can
miss vertically offset custom accessibility bounds. The normal path uses
8-point spacing for real-world status icons and does not fall back to app scans.
The Talon linter integration tests also exercise malformed files and read-only
checks; these are explicitly skipped if Node or the npm development dependencies
are absent.
