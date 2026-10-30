# Mouse-centered AX controls backlog

**Status:** Proposed exploration, not implemented.
Follow the [project principles](README.md). The intended UX is
`show numbers [(left | right | up | down)]` centered on the current pointer:
search within a radius (or directional semicircle), then label only controls
whose bounds intersect that region, including partially contained controls.
The region is conceptual: **no visible circle, custom canvas, or boundary
overlay is requested**. The user is also open to nearest-N as an alternative,
not a settled replacement for radius search.

Unlike ordinary application numbers, this is intended to target the window
under the pointer even if it is not focused, similar to macOS hover scrolling.
Hover scrolling does not establish that background AX discovery or activation
is supported. This track is an explicit, opt-in focused-window exception;
ordinary commands must retain their current scope.

## M1. Discover the hovered AX window without changing focus

Inspect supported Talon pointer, hit-test, element-parent, and window APIs.
The existing [status discovery](../status/discovery.py) uses `ui.element_at`
and parent traversal; reuse that supported pattern, not its menu-bar scan.
Start with a foreground window, then a different window of the same app, then
a background app. Compare returned owner/window and focused window using only
metadata, not private text. Reuse existing supported hit-testing patterns.

**Done when:** a capability table states whether the actual hovered window
can be resolved without activation. Test overlapping windows, desktop, menu/
popup, inaccessible window, and multiple displays. No all-app tree scan,
native AX observer, or silent fallback to the focused window.

## M2. Compare radius filtering and nearest-N selection

**Depends on:** no live AX API; independent of M1.

Choose a radius for the experiment and document screen-coordinate units,
display scaling, inclusive boundary/tangent behavior, and the directional
axis (left/right/up/down in screen coordinates). Radius is still undecided;
do not make a permanent configuration API yet.

Use rectangle/region intersection, not element-center containment. A directional
region is the circle intersected with its selected half-plane; require overlap
with that combined region, not independent overlap with each part.

**Done when:** tests cover fully inside, partial overlap, tangent, outside,
rectangles crossing the center line, corners outside the disk, invalid/zero
frames, negative coordinates, and each direction. No live overlay needed.

Separately test nearest-N using distance to the control rectangle, not just
its center (a large control can contain the pointer). Define deterministic
tie-breaking, directional eligibility for controls crossing the axis, and
whether there is a maximum distance: nearest-N can otherwise label remote
controls in a sparse window. Compare both approaches on dense and sparse
layouts before selecting the UX. **Effort:** S, including pure tests.

## M3. Query and filter one hovered window in an isolated action

**Depends on:** M1 and M2.

Reuse native query and label primitives; keep diagnostic traversal out.
Measure query/filter/label times and counts on the actual hovered window.
Exclude occluded/background-window areas only if the supported API can determine
them reliably; otherwise document the limitation rather than calling them visible.

**Done when:** only intersecting controls of the resolved target window are
numbered, or unsupported targeting fails explicitly. No tree scanning of
unrelated applications, new polling loop, or change to generic show numbers.

## M4. Probe background activation and stale-target safety

**Depends on:** M3.

Separate discovery from activation: test whether selecting a label presses
without focus, activates the owning window first, or fails. Test pointer moves,
window moves/closes, app changes, and invalidated nodes between show/select.
Decide whether the region freezes at invocation (initial experiment) or follows
the pointer (additional scope); do not introduce pointer tracking implicitly.

**Done when:** observed activation/focus effects and safe stop behavior are
documented. Revalidate ownership/region before pressing; never click through
to a newly exposed app or use coordinate clicking as an unannounced fallback.

## M5. Resolve grammar and document the chosen spatial mode

**Depends on:** M3 and M4. **Effort:** XS-S.

Compare proposed `show numbers [direction]` with existing generic commands and
mouse-grid/Rango bindings; use a distinct experimental command until resolved.

**Done when:** the selected radius/nearest-N and directional semantics are
documented, native label cleanup works, and voice precedence/escape behavior
is explicit. No visible spatial boundary and no replacement of ordinary
`show numbers` without a separate promotion decision.
