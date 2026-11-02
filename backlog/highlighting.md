# Word highlighting backlog

Follow the [project principles and handoff](README.md). These are experiments,
not commitments to promote the isolated editable-word spike.

## H1. Validate editable highlighting by voice

**Priority:** Highest. **Depends on:** no other feature spike.

Earlier Talon-action checks succeeded in Word and Slack: initial selection,
next occurrence, number 1, and closing the active tag. This is historical
evidence, not a substitute for voice or regression testing.

**Live update (2026-10-29):** the prepared Word fixture passed start, next,
previous, first, last, and emoji-before-target selection after a UTF-16 fix.
The unsent Slack draft passed start/next/previous; it did not include an emoji.
These are direct Talon action checks, not microphone voice recognition. Talon
was in sleep mode during phrase simulation.

Run each case in Slack, VS Code, and Word:

1. One exact occurrence.
2. Several occurrences before and after the caret.
3. `next`, `previous`, `first`, and `last`.
4. Bare number and `highlight <number>`.
5. Popup button selection.
6. Known homophone input.
7. No match.
8. Switching applications while the popup is open.
9. Moving focus to another editable control.
10. Editing the text while the popup is open.
11. More than 15 matches; the popup window follows the current occurrence.

**Done when:** command recognition, selection/popup synchronization, stale-state
rejection, and large-buffer responsiveness are recorded per app. Errors must
identify the cause in the Talon log. No app-name branches.

## H2. Test session lifecycle and decide promotion

**Depends on:** H1 and the highlighting findings in the [audit](accessibility-audit.md).

[Runtime tests](../tests/test_highlight_runtime.py) now cover start,
window/offset/element staleness, homophone failure, and reload. Extend them to
navigation, invalid numbers, selection-write failure, and closing while
preserving the selected word. Include shared-buffer offsets and Unicode
range semantics in the test plan.

**Done when:** tests and H1 evidence support an explicit promote/retain/remove
decision. Promotion renames files/actions to remove `spike` and adds normal
user-facing command documentation. If removed, remove the five isolated files
listed in the [handoff](README.md); retain shared activation fixes only if
another production feature uses them.

## H3. Probe static-text selection, one application at a time

**Priority:** Deferred until editable highlighting is stable.

Slack observations distinguish sent messages (`AXStaticText`, message/document
group, no editable ancestor), composer (`AXTextArea`, editable ancestor), and
sidebar rows/groups with press actions.

For one visible static-text node: read its value, locate an exact whole word,
save the selection, attempt one range write, read it back, and restore the
original range in `finally`. Repeat separately for Slack messages, Firefox
page text, VS Code-rendered text, and Word document text.

**Done when:** each app has a writable/read-only/unsupported result without
printing private text. Readable selection attributes do not prove writability.
No new production traversal or static-text selection commands in this spike.

## H4. Establish whether substring bounds are usable

**Priority:** Deferred/experimental. **Depends on:** stable editable behavior.

Native labels target AX elements, not individual occurrences inside one element.
An earlier unfocused Slack composer `AXBoundsForRange` query returned
`Rect(0, 1117, 0, 0)`, which is unusable.

First probe `AXBoundsForRange` on focused editable elements; separately probe
`AXBoundsForTextMarkerRange` where supported. Compare Slack, Firefox, VS Code,
and Word. Then test wrapping, scrolling, zoom, font changes, and window movement.

**Done when:** bounds and failure cases are recorded per app. Retain the context
popup if bounds are unreliable. No character-count/font-based position estimates;
custom canvas work needs a separate maintenance-cost decision.

## H5. Collect no-match examples before considering fuzzy matching

**Priority:** Deferred.

Current behavior includes exact whole-word, case-insensitive terms and known
community homophones. Collect representative failed utterances without private
document contents; distinguish missing homophones from other failures.

**Done when:** evidence supports either no change or a separate policy proposal
covering edit distance, short-word thresholds, ranking against homophones,
ambiguous results, and visibly distinct fuzzy matches. Any fuzzy search would
run only after exact/homophone matching fails. No fuzzy implementation here.
