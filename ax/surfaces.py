"""Focused accessibility surfaces shared by navigation and diagnostics."""

from talon import ui


def contains(root, element):
    """Test bounded AX ancestry without enumerating a subtree."""
    for _ in range(100):
        if element is None:
            return False
        if element == root:
            return True
        element = element.get("AXParent")
    raise RuntimeError("Unable to resolve accessibility ancestry.")


def focused_surfaces(owner):
    focused_window = owner.element.get("AXFocusedWindow")
    if focused_window is None:
        raise RuntimeError(
            f"{owner.name} does not expose an AXFocusedWindow attribute."
        )
    surfaces = [("focused-window", focused_window)]
    menu = ui.active_menu()
    if menu is not None:
        surfaces.append(("active-menu", menu))
    return surfaces
