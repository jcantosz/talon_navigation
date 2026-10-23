# Talon Navigation

macOS application-menu navigation and local Talon command reports.
Install this repository anywhere under Talon's `user` directory. Menu navigation
requires macOS accessibility support and Talon's native labels API.

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
to be running. They cover menu traversal/back navigation, grammar analysis, report
views and HTML escaping, report regeneration, browser opening, and explicit
failure notifications. Test paths are relative to the repository, not a specific
user's installation.
The Talon linter integration tests also exercise malformed files and read-only
checks; these are explicitly skipped if Node or the npm development dependencies
are absent.
