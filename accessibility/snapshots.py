import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

REDACTED_ATTRIBUTES = {
    "AXDescription",
    "AXDocument",
    "AXDOMIdentifier",
    "AXFilename",
    "AXHelp",
    "AXIdentifier",
    "AXPlaceholderValue",
    "AXRoleDescription",
    "AXTitle",
    "AXURL",
    "AXValue",
}
RELATIONSHIP_ATTRIBUTES = {
    "AXChildren",
    "AXFocusedUIElement",
    "AXFocusedWindow",
    "AXMenuBar",
    "AXParent",
    "AXSelectedChildren",
    "AXTopLevelUIElement",
    "AXVisibleChildren",
    "AXWindow",
    "AXWindows",
}


def _json_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if all(hasattr(value, name) for name in ("x", "y", "width", "height")):
        return {
            "x": value.x,
            "y": value.y,
            "width": value.width,
            "height": value.height,
        }
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return repr(value)


def snapshot_data(application, surfaces, ui_error, redacted):
    nodes = []
    errors = []
    for surface_name, inventory in surfaces:
        for node in inventory.nodes:
            try:
                attributes = {
                    key: _json_value(value)
                    for key, value in node.element.dump().items()
                    if key not in RELATIONSHIP_ATTRIBUTES
                }
            except ui_error as error:
                errors.append(
                    f"{surface_name}:{node.path}: {type(error).__name__}: {error}"
                )
                attributes = {}
            if redacted:
                attributes = {
                    key: (
                        "<redacted>"
                        if key in REDACTED_ATTRIBUTES and value not in (None, "")
                        else value
                    )
                    for key, value in attributes.items()
                }
            nodes.append(
                {
                    "surface": surface_name,
                    "path": list(node.path),
                    "attributes": attributes,
                    "actions": list(node.actions),
                    "matches_show_numbers": node.matches_show_numbers,
                }
            )

    return {
        "application": {
            "name": "<redacted>" if redacted else application.name,
            "bundle": application.bundle,
            "pid": application.pid,
        },
        "captured_at": datetime.now().astimezone().isoformat(),
        "redacted": redacted,
        "nodes": nodes,
        "errors": errors,
    }


def _write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temporary.replace(path)
    except (OSError, TypeError, ValueError):
        temporary.unlink(missing_ok=True)
        raise


def write_snapshots(directory, application, surfaces, ui_error):
    bundle = application.bundle or f"pid-{application.pid}"
    safe_bundle = "".join(
        character if character.isalnum() or character in ".-_" else "_"
        for character in bundle
    )
    paths = []
    for redacted, suffix in ((False, "full"), (True, "redacted")):
        path = directory / f"{safe_bundle}.{suffix}.json"
        _write_atomic(
            path,
            snapshot_data(application, surfaces, ui_error, redacted),
        )
        paths.append(path)
    return paths
