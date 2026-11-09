"""Window hints: label panes of the focused window.

With a bundle match in `user.window_hints_applications`, panes come from
the mapped declarative profile; otherwise from
generic AX pane roles. Visible labels refresh on application/window focus changes.
See window_hints/README.md for supported behavior and compatibility limits.
"""

import time

from talon import Context, Module, actions, app, settings, ui

from ..ax.inventory import collect
from ..ax.surfaces import focused_surfaces
from . import core, profiles, section_actions
from . import labels as pane_labels
from .lifecycle import FocusChanged, HintSession
from .sections import ActiveSections

mod = Module()
mod.tag("window_hints_active", desc="Window section hints own the visible labels")
mod.list("window_sections", desc="Named sections from the current window hint profile")
mod.list("window_section_directions", desc="Directions for section wheel scrolling")
mod.setting(
    "window_hints_applications",
    type=str,
    default="",
    desc="Comma-separated exact bundle=profile mappings; unmatched apps use generic panes.",
)
TITLE = "Window hints"
ctx = Context()
ctx.matches = "os: mac"
ctx.lists["user.window_sections"] = {}
ctx.lists["user.window_section_directions"] = {
    direction: direction for direction in ("up", "down", "left", "right")
}
active_ctx = Context()
active_ctx.matches = "os: mac\ntag: user.window_hints_active"
_sections = ActiveSections()


def _read(element, attribute, default):
    try:
        return element.get(attribute) or default
    except ui.UIErr:
        return default


def _walk(profile=None):
    owner = ui.active_app()
    if owner is None:
        raise RuntimeError("There is no active application.")
    root = focused_surfaces(owner)[0][1]
    started = time.perf_counter()
    options = (
        {
            "max_depth": profile.get("max_depth"),
            "stop_roles": ("AXTable", "AXOutline", "AXTextField", "AXTextArea"),
        }
        if profile is not None
        else {}
    )
    inventory = collect(root, ui.UIErr, **options)
    return inventory, time.perf_counter() - started


def _window_rect(inventory):
    for node in inventory.nodes:
        if node.role == "AXWindow":
            return core.as_rect(node.frame)
    return None


def _profile_nodes(inventory):
    return [
        profiles.Node(
            node.path,
            core.as_rect(node.frame),
            node.role or "",
            _read(node.element, "AXSubrole", ""),
            _read(node.element, "AXDOMIdentifier", ""),
            frozenset(_read(node.element, "AXDOMClassList", ())),
            node.title or "",
            node.description or "",
            node.element,
            identifier=node.identifier or "",
            help=_read(node.element, "AXHelp", ""),
        )
        for node in inventory.nodes
    ]


def _warn_if_partial(inventory):
    if inventory.truncated or inventory.errors:
        app.notify(TITLE, "Partial walk; see the Talon log. Showing what was found.")


def _show_profile(name, names=True, current=lambda: True):
    profile = profiles.load_profile(name)
    inventory, walk_time = _walk(profile)
    _warn_if_partial(inventory)
    started = time.perf_counter()
    panes = profiles.find_panes(_profile_nodes(inventory), profile)
    if not current():
        return
    _check_window(inventory)
    if not current():
        return
    ctx.lists["user.window_sections"] = {
        pane_labels.spoken_name(p.name): p.name for p in panes
    }
    if not inventory.truncated and not inventory.errors:
        _sections.publish(ui.active_app(), inventory.nodes[0].element, name, panes)
    window = _window_rect(inventory)
    result = profiles.report(panes, window, profile.get("tiles", False))
    print(
        f"Window hints (profile {name}): panes={len(panes)} "
        f"coverage={result['coverage']:.3f} overlaps={result['overlaps']} "
        f"walk={walk_time:.2f}s match={time.perf_counter() - started:.2f}s"
    )
    for index, pane in enumerate(panes, 1):
        frame = pane.frame
        print(
            f"  {index}: {pane.name} "
            f"({frame.x:.0f},{frame.y:.0f},{frame.width:.0f},{frame.height:.0f})"
        )
    if not panes:
        app.notify(TITLE, f"Profile {name!r} matched no panes.")
        return
    if not result["ok"]:
        app.notify(TITLE, f"Profile {name!r} panes do not tile the window.")
    app.notify(TITLE, ", ".join(f"{i}: {p.name}" for i, p in enumerate(panes, 1)))
    if not current():
        return
    with _session.drawing():
        pane_labels.show(panes, names=names)


def _show_generic(rule, names, current=lambda: True):
    inventory, walk_time = _walk()
    if not current():
        return
    _check_window(inventory)
    _warn_if_partial(inventory)
    candidates = []
    for node in inventory.nodes:
        rect = core.as_rect(node.frame)
        if rect is None:
            continue
        candidates.append(
            core.Candidate(
                node.role or "",
                rect,
                len(node.path),
                None,
                bool(node.title or node.description or node.identifier),
                node.element,
            )
        )
    window = _window_rect(inventory)
    if window is None:
        raise RuntimeError("The focused window has no usable AXWindow frame.")
    panes = core.select_candidates(candidates, window, rule)
    print(
        f"Window hints: rule={rule} nodes={len(inventory.nodes)} "
        f"errors={len(inventory.errors)} truncated={inventory.truncated} "
        f"panes={len(panes)} {core.pane_count_summary(panes)} walk={walk_time:.2f}s"
    )
    for index, pane in enumerate(panes, 1):
        print(f"  {index}: {pane.role} named={pane.named} frame={pane.frame}")
    if not panes:
        app.notify(TITLE, f"No panes found with rule {rule!r}.")
        return
    elements = [pane.ref for pane in panes]
    if not current():
        return
    with _session.drawing():
        if names:
            actions.labels.show_names(elements)
        else:
            actions.labels.show(elements)


def _check_window(inventory):
    if not inventory.nodes:
        raise RuntimeError("The focused window exposes no readable AX tree.")
    root = inventory.nodes[0].element
    owner = ui.active_app()
    if owner is None or focused_surfaces(owner)[0][1] != root:
        raise FocusChanged("The focused window changed while resolving sections.")


def _render(rule, names):
    section_actions.refresh_scroll_direction()
    revision = _session.revision

    def current():
        return _session.mode is not None and _session.revision == revision

    ctx.lists["user.window_sections"] = {}
    _sections.clear()
    profile = _current_profile()
    if profile:
        _show_profile(profile, names=names, current=current)
    else:
        _show_generic(rule, names, current=current)


previous = globals().get("_session")
if previous is not None:
    previous.stop()
_session = HintSession(ctx, _render)


@mod.action_class
class Actions:
    def window_hints_show(rule: str = "named", names: bool = True):
        """Label the focused window's panes, refreshing on window/app focus."""
        _session.show(rule, names)

    def window_section_scroll(name: str, direction: str, amount: int = 1):
        """Scroll a current section using a verified pointer-positioned wheel."""
        section_actions.run(
            lambda: section_actions.scroll(
                lambda: _resolve_section(name), direction, amount
            )
        )

    def window_section_number(name: str):
        """Number actionable descendants of a named section using application numbers."""
        section_actions.run(
            lambda: actions.user.accessibility_show_section_numbers(
                lambda: _resolve_section(name)
            )
        )


def _resolve_section(name):
    return _sections.resolve(name, _current_profile())


def _current_profile():
    mapping = profiles.application_mapping(
        settings.get("user.window_hints_applications")
    )
    owner = ui.active_app()
    return mapping.get(owner.bundle, "") if owner is not None else ""


@active_ctx.action_class("labels")
class LabelOverrides:
    def hide():
        actions.next()
        _session.replaced()

    def show(targets):
        actions.next(targets)
        _session.replaced()

    def show_names(targets):
        actions.next(targets)
        _session.replaced()


def _focus_changed(*event):
    _sections.clear()
    ctx.lists["user.window_sections"] = {}
    _session.focus_changed(*event)


ui.register("app_activate", _focus_changed)
ui.register("win_focus", _focus_changed)
