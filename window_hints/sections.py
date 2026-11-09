"""Current-window section references, independent of visible label ownership."""

from talon import ui

from . import core
from .labels import spoken_name


class ActiveSections:
    def __init__(self):
        self.clear()

    def clear(self):
        self.owner = None
        self.window = None
        self.profile = None
        self.targets = {}

    def publish(self, owner, window, profile, panes):
        self.clear()
        self.owner, self.window, self.profile = owner, window, profile
        for pane in panes:
            self.targets[pane.name] = pane.ref
            self.targets[spoken_name(pane.name)] = pane.ref

    def resolve(self, name, profile):
        owner = ui.active_app()
        if (
            owner is None
            or self.owner is None
            or owner != self.owner
            or profile != self.profile
            or owner.element.get("AXFocusedWindow") != self.window
        ):
            self.clear()
            raise RuntimeError("The focused window changed. Show sections again.")
        root = self.targets.get(name)
        if root is None:
            raise RuntimeError(
                f"Section {name!r} is absent or ambiguous. Show sections again."
            )
        if (
            root.get("AXWindow") != self.window
            or root.get("AXHidden") is True
            or core.as_rect(root.get("AXFrame")) is None
        ):
            self.clear()
            raise RuntimeError(
                "The section is no longer available. Show sections again."
            )
        return root
