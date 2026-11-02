import logging
from pathlib import Path

from talon import Module, app, ui

from .controls import focused_surfaces
from .inventory_core import collect, format_node
from .snapshots import write_snapshots

mod = Module()
SNAPSHOT_DIRECTORY = Path(__file__).resolve().parents[1] / "ax-trees"


def _inventories(owner):
    return [(name, collect(root, ui.UIErr)) for name, root in focused_surfaces(owner)]


def _active_app(title):
    owner = ui.active_app()
    if owner is None:
        app.notify(title, "There is no active application.")
    return owner


def _print_inventory(owner, include_all):
    inventories = _inventories(owner)
    partial = False
    for name, inventory in inventories:
        displayed = (
            inventory.nodes
            if include_all
            else (node for node in inventory.nodes if node.is_control)
        )
        print(f"\nAccessibility inventory: {owner.name!r} {name}")
        print(
            f"nodes={len(inventory.nodes)} "
            f"errors={len(inventory.errors)} "
            f"truncated={inventory.truncated}"
        )
        for node in displayed:
            print(format_node(node))
        for error in inventory.errors:
            print(f"ERROR {error}")
        partial = partial or bool(inventory.errors) or inventory.truncated
    return partial


@mod.action_class
class Actions:
    def accessibility_debug_inventory(include_all: bool = False):
        """Print the focused accessibility surfaces to the Talon log."""
        title = "Accessibility debug inventory"
        owner = _active_app(title)
        if owner is None:
            return
        try:
            partial = _print_inventory(owner, include_all)
        except (RuntimeError, ui.UIErr):
            logging.exception("Accessibility debug inventory failed")
            app.notify(title, "Unable to read the focused accessibility surfaces.")
            return
        app.notify(
            title,
            "Partial results (errors or truncation) were printed to the Talon log."
            if partial
            else "Results were printed to the Talon log.",
        )

    def accessibility_debug_snapshot():
        """Write full and redacted focused accessibility trees as JSON."""
        title = "Accessibility debug snapshots"
        owner = _active_app(title)
        if owner is None:
            return
        try:
            paths, partial = write_snapshots(
                SNAPSHOT_DIRECTORY,
                owner,
                _inventories(owner),
                ui.UIErr,
            )
        except (RuntimeError, ui.UIErr, OSError, TypeError, ValueError):
            logging.exception("Accessibility debug snapshot failed")
            app.notify(title, "Unable to capture or save accessibility snapshots.")
            return
        print(
            "Accessibility debug snapshots: " + ", ".join(str(path) for path in paths)
        )
        app.notify(
            title,
            "Saved PARTIAL snapshots; see the errors and surfaces fields."
            if partial
            else "Saved full and redacted snapshots.",
        )
