"""Offline WH1 probe: run pane-candidate rules over a saved AX snapshot.

Usage: python scripts/window_hints_probe.py ax-trees/<bundle>.full.json

Prints roles, depth, frames and whether a name attribute exists. It never
prints titles, descriptions, identifiers or values.
"""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "window_hints_core",
    ROOT / "window_hints" / "core.py",
)
core = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = core
spec.loader.exec_module(core)


def candidates_from_snapshot(data):
    result, window = [], None
    for node in data["nodes"]:
        attributes = node["attributes"]
        rect = core.as_rect(attributes.get("AXFrame"))
        if rect is None:
            continue
        role = attributes.get("AXRole")
        if role == "AXWindow" and window is None:
            window = rect
        result.append(
            core.Candidate(
                role or "",
                rect,
                len(node["path"]),
                attributes.get("AXSubrole"),
                any(
                    attributes.get(key)
                    for key in ("AXTitle", "AXDescription", "AXIdentifier")
                ),
            )
        )
    return result, window


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    data = json.loads(Path(argv[1]).read_text())
    candidates, window = candidates_from_snapshot(data)
    if window is None:
        print("No AXWindow node with a usable frame; nothing to evaluate.")
        return 1
    print(f"window={window} nodes={len(data['nodes'])}")
    for rule in core.RULES:
        panes = core.select_candidates(candidates, window, rule)
        print(f"\nrule={rule} panes={len(panes)} {core.pane_count_summary(panes)}")
        for pane in panes:
            anchor = core.hint_anchor(pane.frame)
            print(
                f"  {pane.role:<14} depth={pane.depth:<2} named={pane.named!s:<5} "
                f"frame=({pane.frame.x:.0f},{pane.frame.y:.0f},"
                f"{pane.frame.width:.0f},{pane.frame.height:.0f}) "
                f"hint=({anchor.x:.0f},{anchor.y:.0f})"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
