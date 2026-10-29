from collections import Counter
from dataclasses import dataclass, field
from math import isfinite

CONTROL_ROLES = {
    "AXButton",
    "AXCheckBox",
    "AXComboBox",
    "AXDisclosureTriangle",
    "AXLink",
    "AXMenuButton",
    "AXMenuItem",
    "AXPopUpButton",
    "AXRadioButton",
    "AXSearchField",
    "AXSlider",
    "AXSwitch",
    "AXTab",
    "AXTextArea",
    "AXTextField",
}


@dataclass(frozen=True)
class Node:
    element: object = field(compare=False, repr=False)
    path: tuple[int, ...]
    role: str | None
    title: str | None
    description: str | None
    identifier: str | None
    frame: object
    enabled: bool | None
    hidden: bool | None
    attributes: tuple[str, ...]
    actions: tuple[str, ...]

    @property
    def matches_show_numbers(self):
        return "AXPosition" in self.attributes and "AXPress" in self.actions

    @property
    def is_control(self):
        return bool(self.actions) or self.role in CONTROL_ROLES

    def is_visible_number_target(self, screen_bounds):
        frame = self.frame
        if (
            not self.matches_show_numbers
            or self.role not in CONTROL_ROLES
            or self.enabled is False
            or self.hidden is True
            or frame is None
            or not all(
                isfinite(value)
                for value in (frame.x, frame.y, frame.width, frame.height)
            )
            or frame.width <= 0
            or frame.height <= 0
        ):
            return False
        return any(
            frame.x < bounds.x + bounds.width
            and frame.x + frame.width > bounds.x
            and frame.y < bounds.y + bounds.height
            and frame.y + frame.height > bounds.y
            for bounds in screen_bounds
        )


@dataclass(frozen=True)
class Inventory:
    nodes: tuple[Node, ...]
    errors: tuple[str, ...]
    truncated: bool

    def role_counts(self):
        return Counter(node.role or "<no role>" for node in self.nodes)


def _attribute_names(element):
    attributes = element.attrs
    if isinstance(attributes, dict):
        attributes = attributes.keys()
    return tuple(sorted(str(attribute) for attribute in attributes))


def _action_names(element):
    actions = element.actions
    if isinstance(actions, dict):
        actions = actions.keys()
    return tuple(sorted(str(action) for action in actions))


def collect(root, ui_error, limit=10000):
    pending = [(root, ())]
    seen = set()
    nodes = []
    errors = []

    while pending and len(nodes) < limit:
        element, path = pending.pop()
        identity = id(element)
        if identity in seen:
            continue
        seen.add(identity)

        try:
            attributes = _attribute_names(element)
            actions = _action_names(element)
            node = Node(
                element=element,
                path=path,
                role=element.get("AXRole"),
                title=element.get("AXTitle"),
                description=element.get("AXDescription"),
                identifier=element.get("AXIdentifier"),
                frame=element.get("AXFrame"),
                enabled=element.get("AXEnabled"),
                hidden=element.get("AXHidden"),
                attributes=attributes,
                actions=actions,
            )
            children = tuple(element.get("AXChildren") or ())
        except ui_error as error:
            errors.append(f"{format_path(path)}: {type(error).__name__}: {error}")
            continue

        nodes.append(node)
        pending.extend(
            (child, path + (index,))
            for index, child in reversed(tuple(enumerate(children)))
        )

    return Inventory(tuple(nodes), tuple(errors), bool(pending))


def format_path(path):
    return "root" if not path else "root/" + "/".join(map(str, path))


def format_node(node):
    fields = [
        format_path(node.path),
        f"role={node.role!r}",
        f"title={node.title!r}",
        f"description={node.description!r}",
        f"identifier={node.identifier!r}",
        f"frame={node.frame!r}",
        f"enabled={node.enabled!r}",
        f"hidden={node.hidden!r}",
        f"actions={node.actions!r}",
        f"show_numbers={node.matches_show_numbers}",
    ]
    return " ".join(fields)
