from pathlib import Path

from talon import Module, app, ui

from .inventory import focused_surfaces
from .inventory_core import collect, format_node
from .snapshots import write_snapshots

mod = Module()
SNAPSHOT_DIRECTORY = Path(__file__).resolve().parents[1] / "ax-trees"


def _inventories(owner):
    return [(name, collect(root, ui.UIErr)) for name, root in focused_surfaces(owner)]


@mod.action_class
class Actions:
    def accessibility_debug_inventory(include_all: bool = False):
        """Print the focused accessibility surfaces to the Talon log."""
        owner = ui.active_app()
        inventories = _inventories(owner)
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
        app.notify(
            "Accessibility debug inventory",
            "Results were printed to the Talon log.",
        )

    def accessibility_debug_snapshot():
        """Write full and redacted focused accessibility trees as JSON."""
        owner = ui.active_app()
        paths = write_snapshots(
            SNAPSHOT_DIRECTORY,
            owner,
            _inventories(owner),
            ui.UIErr,
        )
        print(
            "Accessibility debug snapshots: " + ", ".join(str(path) for path in paths)
        )
        app.notify(
            "Accessibility debug snapshots",
            "Saved full and redacted snapshots.",
        )
