from math import isfinite

from talon import actions, cron, ctrl, ui

from .roles import CONTROL_ROLES

MENU_WAIT_TICKS = 15
MENU_HOVER_DELAY_TICKS = 3
MENU_BACK_FALLBACK_TICKS = 10
LABEL_TEXT_LEVELS = 4


def usable_frame(element):
    frame = element.get("AXFrame")
    return (
        frame is not None
        and all(
            isfinite(value) for value in (frame.x, frame.y, frame.width, frame.height)
        )
        and frame.width > 0
        and frame.height > 0
    )


def label_element(element, in_menu=False, boundaries=None):
    """Anchor a row or menu item on contained text when useful."""
    role = element.get("AXRole")
    if (
        role == "AXButton"
        and not element.get("AXTitle")
        and not element.get("AXDescription")
    ):
        parent = element.get("AXParent")
        if (
            parent is not None
            and parent.get("AXRole") == "AXComboBox"
            and "AXPress" not in parent.actions
            and usable_frame(parent)
            and usable_frame(element)
        ):
            pressable = [
                child
                for child in parent.get("AXChildren") or ()
                if "AXPress" in child.actions
            ]
            bounds = parent.get("AXFrame")
            frame = element.get("AXFrame")
            if (
                len(pressable) == 1
                and pressable[0] == element
                and bounds.x <= frame.x
                and bounds.y <= frame.y
                and frame.x + frame.width <= bounds.x + bounds.width
                and frame.y + frame.height <= bounds.y + bounds.height
            ):
                return parent
    menu_item = in_menu and role == "AXMenuItem"
    if role != "AXRow" and not menu_item:
        return element
    if menu_item and not usable_frame(element):
        return element
    bounds = element.get("AXFrame")
    boundaries = boundaries or {}
    level = list(element.get("AXChildren") or ())
    for _ in range(LABEL_TEXT_LEVELS):
        level = [
            child
            for child in level
            if not any(
                child == target for target in boundaries.get(child.get("AXRole"), ())
            )
        ]
        texts = []
        for child in level:
            if (
                child.get("AXRole") == "AXStaticText"
                and (not menu_item or child.get("AXHidden") is not True)
                and usable_frame(child)
            ):
                frame = child.get("AXFrame")
                x = frame.x + frame.width / 2
                y = frame.y + frame.height / 2
                if (
                    bounds.x <= x <= bounds.x + bounds.width
                    and bounds.y <= y <= bounds.y + bounds.height
                ):
                    if not menu_item:
                        return child
                    texts.append(child)
        if texts:
            return min(texts, key=lambda child: child.get("AXFrame").x)
        level = [
            grandchild
            for child in level
            if child.get("AXRole") not in CONTROL_ROLES
            and (not menu_item or child.get("AXRole") != "AXMenu")
            for grandchild in child.get("AXChildren") or ()
        ]
    return element


def label_elements(targets, in_menu=False):
    """Keep badge anchors distinct without changing target order or activation."""
    targets = list(targets)
    boundaries = {}
    for target in targets:
        boundaries.setdefault(target.get("AXRole"), []).append(target)
    anchors = [
        label_element(target, in_menu=in_menu, boundaries=boundaries)
        for target in targets
    ]
    if all(target is anchor for target, anchor in zip(targets, anchors)):
        return anchors
    # AX equality can make synchronous cross-process calls. Compare only elements
    # with matching roles and frames, and only when an anchor was substituted.
    buckets = {}
    for index, (target, anchor) in enumerate(zip(targets, anchors)):
        for element in (target,) if target is anchor else (target, anchor):
            bounds = element.get("AXFrame")
            key = (
                element.get("AXRole"),
                None
                if bounds is None
                else (bounds.x, bounds.y, bounds.width, bounds.height),
            )
            buckets.setdefault(key, []).append((index, element))
    collisions = set()
    for candidates in buckets.values():
        for index, anchor in candidates:
            if anchor is targets[index]:
                continue
            if any(
                index != other and anchor == candidate
                for other, candidate in candidates
            ):
                collisions.add(index)
    return [
        target if index in collisions else anchor
        for index, (target, anchor) in enumerate(zip(targets, anchors))
    ]


def submenu_hover_point(target, menu):
    if (
        target.get("AXRole") != "AXMenuItem"
        or target.get("AXHasPopup") is not True
        or target.get("AXEnabled") is False
        or target.get("AXHidden") is True
        or "AXPress" not in target.actions
        or not usable_frame(target)
        or not usable_frame(menu)
    ):
        return None

    frame = target.get("AXFrame")
    bounds = menu.get("AXFrame")
    x = frame.x + frame.width / 2
    y = frame.y + frame.height / 2
    if not (bounds.x < x < bounds.x + bounds.width) or not (
        bounds.y < y < bounds.y + bounds.height
    ):
        return None

    ancestor = target
    for _ in range(100):
        ancestor = ancestor.get("AXParent")
        if ancestor is None:
            return None
        if ancestor == menu:
            return x, y
        if ancestor.get("AXRole") in ("AXWindow", "AXApplication"):
            return None
    return None


def menu_parent(menu):
    owner = menu.get("AXParent")
    if owner is None:
        return None
    if owner.get("AXRole") in ("AXMenu", "AXMenuBar"):
        return owner
    return owner.get("AXParent")


def menu_opener(menu):
    owner = menu.get("AXParent")
    if (
        owner is not None
        and owner.get("AXRole") in ("AXMenuItem", "AXMenuBarItem")
        and owner.get("AXEnabled") is not False
        and owner.get("AXHidden") is not True
        and "AXPress" in owner.actions
        and any(child == menu for child in owner.get("AXChildren") or ())
    ):
        return owner
    return None


class LabelSession:
    _render_generation = 0

    def __init__(self, context, active_tag, names):
        self.context = context
        self.active_tag = active_tag
        self.names = names
        self.job = None
        self.stopped = False
        self.preserve_hide = False

    def render(self, elements):
        if self.stopped:
            return False
        elements = list(elements)
        LabelSession._render_generation += 1
        generation = LabelSession._render_generation
        if self.names:
            actions.labels.show_names(elements)
        else:
            actions.labels.show(elements)
        if self.stopped:
            # A replacement session may have rendered while this one was stopping.
            if generation == LabelSession._render_generation:
                actions.labels.hide()
            return False
        self.context.tags = [self.active_tag]
        return True

    def start_updates(self, callback, interval="100ms"):
        self.job = cron.interval(interval, callback)

    def hide_for_transition(self):
        previous = self.preserve_hide
        self.preserve_hide = True
        try:
            actions.labels.hide()
        finally:
            self.preserve_hide = previous

    def hover_submenu_if_current(
        self, target, menu, position, focus_valid, active_menu=None
    ):
        """Hover only while the session, focus, menu, and pointer remain current."""
        if self.stopped or ctrl.mouse_pos() != position or not focus_valid():
            return
        point = submenu_hover_point(target, menu)
        if (
            self.stopped
            or point is None
            or ctrl.mouse_pos() != position
            or not focus_valid()
            or (active_menu or ui.active_menu)() != menu
            or self.stopped
        ):
            return
        actions.mouse_move(*point)

    def stop(self):
        if self.stopped:
            return
        self.stopped = True
        if self.job is not None:
            cron.cancel(self.job)
            self.job = None
        self.context.tags = []
