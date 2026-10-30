# Cross-platform navigation backlog

Follow the [project principles](README.md). These are independent portability
and convenience investigations, not prerequisites for macOS feature spikes.

## P1. Compare existing macOS AX and Windows accessibility capabilities

Inspect Talon's supported Windows accessibility APIs and installed Community
helpers before proposing custom UI Automation bindings. Compare focused-root
discovery, children/query, role/action semantics, bounds, enabled/visible state,
text ranges, and events. Distinguish the debug walker from production queries.

**Done when:** a capability matrix identifies genuine overlap, unsupported
operations, and a small cross-platform use case. Windows runtime results require
a Windows machine; do not infer them from macOS tests.

## P2. Test one portable traversal contract

**Depends on:** P1 and evidence of useful overlap.

Try one read-only focused-window control inventory on both platforms using
existing helpers. Keep platform semantics explicit; only extract shared pure
logic demonstrated to be equivalent. No generic framework or replacement AX
backend just because both platforms expose trees.

**Done when:** fixtures and one live result per OS establish what is shared
and what must remain platform-specific, including partial traversal/errors.
If overlap is too small, document that and keep implementations separate.

## P3. Inventory Windows shortcut equivalents and collisions

**Status:** custom shortcut work withdrawn; learn Community's existing
commands first (2026-10-29). No replacement grammar requested.

**Likely already solved:** Community's Windows modifier list maps
`command: ctrl`, so `command c` and `command l` should already send Ctrl+C and
Ctrl+L. Start by verifying this on the Windows machine; P4 may be unnecessary.

**Depends on:** [W5 command discovery](workflow-and-discovery.md#w5-build-an-existing-command-overlap-inventory).

For `command c` and `command l`, inspect existing key captures, edit-copy actions,
and browser/address/search-bar actions on Windows. The intended behavior is copy
and address/search-bar focus while switching between Mac and Windows, not
literally sending a nonexistent Windows Command modifier.

**Done when:** existing equivalents, active grammar collisions, target
applications, and Ctrl+L differences are documented. Determine whether the
request is browser-only or includes app-specific search before broadening it.

## P4. Windows convenience aliases (cancelled)

Do not implement: the user will learn the existing Community commands.
Only reopen if P3 establishes a concrete unsupported task on Windows.
