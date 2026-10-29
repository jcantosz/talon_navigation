"""Convert an accessibility snapshot into a searchable HTML control tree."""

import argparse
import html
import json
from dataclasses import dataclass, field
from pathlib import Path

NAME_ATTRIBUTES = (
    "AXTitle",
    "AXDescription",
    "AXPlaceholderValue",
    "AXValue",
    "AXDOMIdentifier",
    "AXIdentifier",
    "AXHelp",
)
IGNORED_ACTIONS = {"AXCancel", "AXScrollToVisible"}
GENERIC_ROLE_DESCRIPTIONS = {"", "group"}
STRUCTURAL_ROLES = {
    "AXGroup",
    "AXLayoutArea",
    "AXList",
    "AXOutline",
    "AXScrollArea",
    "AXSplitter",
    "AXTabGroup",
    "AXTable",
    "AXToolbar",
    "AXWebArea",
}


@dataclass
class Node:
    record: dict
    children: list["Node"] = field(default_factory=list)

    @property
    def attributes(self):
        return self.record.get("attributes", {})

    @property
    def actions(self):
        return tuple(self.record.get("actions", ()))

    @property
    def actionable(self):
        return any(action not in IGNORED_ACTIONS for action in self.actions)

    @property
    def name(self):
        for attribute in NAME_ATTRIBUTES:
            value = self.attributes.get(attribute)
            if value not in (None, "", [], {}):
                return str(value)
        role_description = str(self.attributes.get("AXRoleDescription") or "")
        if role_description.casefold() not in GENERIC_ROLE_DESCRIPTIONS:
            return role_description
        classes = self.attributes.get("AXDOMClassList") or ()
        if classes:
            return _class_name(classes[0])
        return str(self.attributes.get("AXRole") or "<unnamed>")


def _class_name(value):
    value = str(value).split("__", 1)[0]
    value = value.removeprefix("p-").removeprefix("c-")
    return value.replace("_", " ").replace("-", " ").strip()


def build_surfaces(records):
    surfaces = {}
    for record in records:
        surface = record["surface"]
        path = tuple(record["path"])
        surfaces.setdefault(surface, {})[path] = Node(record)

    roots = []
    for surface, nodes in surfaces.items():
        for path, node in nodes.items():
            if path:
                parent = nodes.get(path[:-1])
                if parent is not None:
                    parent.children.append(node)
        for node in nodes.values():
            node.children.sort(key=lambda child: tuple(child.record["path"]))
        roots.extend(
            (surface, node) for path, node in sorted(nodes.items()) if not path
        )
    return roots


def prune(node, root=False):
    children = []
    for child in node.children:
        children.extend(prune(child))
    node.children = children
    if node.attributes.get("AXRole") == "AXGroup" and len(children) == 1:
        return children
    if root or node.actionable or len(children) > 1:
        return [node]
    return children


def _metadata(node):
    return str(node.attributes.get("AXRole") or "Unknown")


def _secondary_text(node):
    for attribute in ("AXDescription", "AXValue"):
        value = node.attributes.get(attribute)
        if value not in (None, "", [], {}) and str(value) != node.name:
            text = str(value).replace("\n", " ")
            return text if len(text) <= 160 else text[:157] + "..."
    return ""


def _render_actions(node):
    return "".join(
        f'<span class="action">{html.escape(action.removeprefix("AX"))}</span>'
        for action in node.actions
        if action not in IGNORED_ACTIONS
    )


def _render_node(node, depth=0):
    name = html.escape(node.name)
    role = html.escape(_metadata(node))
    secondary = html.escape(_secondary_text(node))
    actions = _render_actions(node)
    if not node.children:
        description = f'<div class="description">{secondary}</div>' if secondary else ""
        action_row = f'<div class="actions">{actions}</div>' if actions else ""
        return (
            f'<li class="control" data-depth="{depth}">'
            f'<div class="control-heading"><span class="name">{name}</span>'
            f'<span class="role">{role}</span></div>'
            f"{description}{action_row}</li>"
        )
    children = "".join(_render_node(child, depth + 1) for child in node.children)
    count = sum(1 for child in node.children if child.actionable)
    return (
        f'<li class="group depth-{depth % 5}" data-depth="{depth}">'
        f'<details open><summary><span class="name">{name}</span>'
        f'<span class="role">{role}</span>'
        f'<span class="count">{count} direct control'
        f"{'s' if count != 1 else ''}</span>"
        f"</summary>"
        f'<ul class="children">{children}</ul></details></li>'
    )


def _walk(node, depth=0):
    yield node, depth
    for child in node.children:
        yield from _walk(child, depth + 1)


def _frame(node):
    frame = node.attributes.get("AXFrame")
    if not isinstance(frame, dict):
        return None
    required = ("x", "y", "width", "height")
    if not all(isinstance(frame.get(key), (int, float)) for key in required):
        return None
    if frame["width"] <= 0 or frame["height"] <= 0:
        return None
    return frame


def _spatial_style(frame, root, depth):
    left = 100 * (frame["x"] - root["x"]) / root["width"]
    top = 100 * (frame["y"] - root["y"]) / root["height"]
    width = 100 * frame["width"] / root["width"]
    height = 100 * frame["height"] / root["height"]
    return (
        f"left:{left:.3f}%;top:{top:.3f}%;width:{width:.3f}%;"
        f"height:{height:.3f}%;--depth:{depth}"
    )


def _is_spatial_group(node):
    return bool(node.children) or node.attributes.get("AXRole") in STRUCTURAL_ROLES


def _render_spatial_node(node, root_frame, depth):
    frame = _frame(node)
    if frame is None:
        return ""
    name = html.escape(node.name)
    role = html.escape(_metadata(node))
    description = html.escape(_secondary_text(node), quote=True)
    actions = html.escape(
        ", ".join(
            action.removeprefix("AX")
            for action in node.actions
            if action not in IGNORED_ACTIONS
        ),
        quote=True,
    )
    style = _spatial_style(frame, root_frame, depth)
    title = html.escape(f"{node.name} · {_metadata(node)}", quote=True)
    if _is_spatial_group(node):
        return (
            f'<button class="spatial-group depth-{depth % 5} searchable" '
            f'style="{style}" data-name="{name}" data-role="{role}" '
            f'data-description="{description}" data-actions="{actions}" '
            f'title="{title}"><span>{name}</span></button>'
        )
    return (
        f'<button class="spatial-control searchable" style="{style}" '
        f'data-name="{name}" data-role="{role}" '
        f'data-description="{description}" data-actions="{actions}" '
        f'title="{title}"><span>{name}</span>'
        f"<small>{role}</small></button>"
    )


def _render_spatial(surface, root):
    root_frame = _frame(root)
    if root_frame is None:
        return (
            f"<section><h2>{html.escape(surface)}</h2>"
            "<p>This surface has no usable AXFrame.</p></section>"
        )
    nodes = list(_walk(root))
    groups = "".join(
        _render_spatial_node(node, root_frame, depth)
        for node, depth in nodes
        if node is not root and _is_spatial_group(node)
    )
    controls = "".join(
        _render_spatial_node(node, root_frame, depth)
        for node, depth in nodes
        if node is not root and not _is_spatial_group(node)
    )
    ratio = root_frame["width"] / root_frame["height"]
    return (
        f'<section class="spatial-section"><h2>{html.escape(surface)}</h2>'
        '<div class="spatial-layout">'
        f'<div class="spatial-stage" style="aspect-ratio:{ratio:.5f}">'
        f"{groups}{controls}</div>"
        '<aside class="inspector"><h3>Control details</h3>'
        "<p>Select a group or control in the spatial diagram.</p>"
        '<dl><dt>Name</dt><dd data-field="name">—</dd>'
        '<dt>Type</dt><dd data-field="role">—</dd>'
        '<dt>Description</dt><dd data-field="description">—</dd>'
        '<dt>Actions</dt><dd data-field="actions">—</dd></dl></aside>'
        "</div></section>"
    )


def render(snapshot):
    roots = [
        (surface, prune(root, root=True)[0])
        for surface, root in build_surfaces(snapshot["nodes"])
    ]
    trees = "".join(
        f"<section><h2>{html.escape(surface)}</h2>"
        f'<ul class="tree">{_render_node(root)}</ul></section>'
        for surface, root in roots
    )
    spatial = "".join(_render_spatial(surface, root) for surface, root in roots)
    application = snapshot.get("application", {})
    title = f"{application.get('name') or application.get('bundle') or 'AX'} controls"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body {{ font: 14px system-ui, sans-serif; margin: 24px; color: #202124; }}
input {{ box-sizing: border-box; padding: 8px; width: min(680px, 100%); }}
.toolbar {{ align-items: center; display: flex; flex-wrap: wrap; gap: 8px;
  margin-bottom: 16px; }}
.toolbar input {{ margin-right: auto; }}
.tab {{ background: #fff; border: 1px solid #dadce0; border-radius: 6px;
  cursor: pointer; padding: 8px 12px; }}
.tab.active {{ background: #1a73e8; border-color: #1a73e8; color: #fff; }}
.view {{ display: none; }}
.view.active {{ display: block; }}
ul {{ list-style: none; padding-left: 22px; }}
.tree {{ padding-left: 0; }}
li {{ box-sizing: border-box; }}
summary {{ align-items: center; cursor: pointer; display: flex; flex-wrap: wrap;
  gap: 7px; padding: 7px 9px; }}
.name {{ font-weight: 650; overflow-wrap: anywhere; }}
.role {{ background: #e8eaed; border-radius: 999px; color: #3c4043;
  font: 11px ui-monospace, monospace; padding: 2px 6px; }}
.count {{ color: #5f6368; font-size: 12px; }}
.group {{ border: 2px solid #5f6368; border-radius: 10px; margin: 10px 0;
  min-width: 260px; overflow: hidden; }}
.group > details > summary {{ background: #f1f3f4; }}
.group.depth-1 {{ border-color: #1a73e8; }}
.group.depth-2 {{ border-color: #188038; }}
.group.depth-3 {{ border-color: #a142f4; }}
.group.depth-4 {{ border-color: #e37400; }}
.children {{ align-items: flex-start; display: flex; flex-wrap: wrap; gap: 10px;
  padding: 10px; }}
.children > .group {{ flex: 1 1 420px; margin: 0; }}
.control {{ background: #e8f0fe; border: 1px solid #aecbfa;
  border-left: 5px solid #1a73e8; border-radius: 7px; flex: 1 1 220px;
  max-width: 420px; min-width: 180px; padding: 9px; position: relative; }}
.control-heading {{ align-items: flex-start; display: flex; gap: 7px;
  justify-content: space-between; }}
.description {{ color: #5f6368; font-size: 12px; margin-top: 6px;
  overflow-wrap: anywhere; }}
.actions {{ display: flex; flex-wrap: wrap; gap: 4px; margin-top: 7px; }}
.action {{ background: #fff; border: 1px solid #aecbfa; border-radius: 4px;
  color: #174ea6; font-size: 10px; padding: 1px 5px; }}
.spatial-layout {{ align-items: flex-start; display: grid;
  grid-template-columns: minmax(700px, 1fr) minmax(220px, 300px); gap: 16px;
  overflow-x: auto; }}
.spatial-stage {{ background: #f8f9fa; border: 1px solid #dadce0;
  min-width: 700px; position: relative; width: 100%; }}
.spatial-group, .spatial-control {{ box-sizing: border-box; cursor: pointer;
  overflow: hidden; position: absolute; text-align: left; }}
.spatial-group {{ background: transparent; border: 2px solid #5f6368;
  color: #3c4043; padding: 0; z-index: calc(10 + var(--depth)); }}
.spatial-group > span {{ background: #fff; display: inline-block; font-size: 10px;
  max-width: 100%; overflow: hidden; padding: 1px 4px; text-overflow: ellipsis;
  white-space: nowrap; }}
.spatial-group.depth-1 {{ border-color: #1a73e8; }}
.spatial-group.depth-2 {{ border-color: #188038; }}
.spatial-group.depth-3 {{ border-color: #a142f4; }}
.spatial-group.depth-4 {{ border-color: #e37400; }}
.spatial-control {{ background: #d2e3fcdd; border: 1px solid #1a73e8;
  border-radius: 3px; color: #174ea6; font-size: 9px; padding: 2px;
  z-index: calc(100 + var(--depth)); }}
.spatial-control span, .spatial-control small {{ display: block; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }}
.spatial-control small {{ font-size: 8px; opacity: .75; }}
.spatial-control:hover, .spatial-control:focus {{
  outline: 2px solid #174ea6; }}
.spatial-group:hover, .spatial-group:focus {{ background: #ffffff22;
  outline: 2px solid currentColor; }}
.inspector {{ background: #fff; border: 1px solid #dadce0; border-radius: 8px;
  padding: 12px; position: sticky; top: 12px; }}
.inspector h3 {{ margin-top: 0; }}
.inspector dt {{ color: #5f6368; font-size: 11px; margin-top: 9px;
  text-transform: uppercase; }}
.inspector dd {{ margin: 2px 0 0; overflow-wrap: anywhere; }}
.hidden {{ display: none; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<p>Actionable controls and branching containers from
{html.escape(snapshot.get("captured_at", "an unknown capture time"))}.</p>
<div class="toolbar">
  <input id="search" type="search" placeholder="Filter controls" autofocus>
  <button class="tab active" data-view="spatial-view">Spatial</button>
  <button class="tab" data-view="hierarchy-view">Hierarchy</button>
</div>
<main id="spatial-view" class="view active">{spatial}</main>
<main id="hierarchy-view" class="view">{trees}</main>
<script>
const search = document.querySelector("#search");
search.addEventListener("input", () => {{
  const query = search.value.toLocaleLowerCase();
  for (const item of document.querySelectorAll("li, .searchable")) {{
    const matches = !query || item.textContent.toLocaleLowerCase().includes(query);
    item.classList.toggle("hidden", !matches);
    if (matches && query) {{
      const details = item.querySelector(":scope > details");
      if (details) details.open = true;
    }}
  }}
}});
for (const tab of document.querySelectorAll(".tab")) {{
  tab.addEventListener("click", () => {{
    document.querySelectorAll(".tab, .view").forEach(element =>
      element.classList.remove("active"));
    tab.classList.add("active");
    document.querySelector(`#${{tab.dataset.view}}`).classList.add("active");
  }});
}}
for (const node of document.querySelectorAll(".spatial-group, .spatial-control")) {{
  node.addEventListener("click", event => {{
    event.stopPropagation();
    const section = node.closest(".spatial-section");
    const inspector = section.querySelector(".inspector");
    for (const field of ["name", "role", "description", "actions"]) {{
      inspector.querySelector(`[data-field="${{field}}"]`).textContent =
        node.dataset[field] || "—";
    }}
  }});
}}
</script>
</body>
</html>
"""


def output_path(input_path):
    return input_path.with_suffix("").with_suffix(".tree.html")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    arguments = parser.parse_args(argv)
    snapshot = json.loads(arguments.snapshot.read_text())
    destination = arguments.output or output_path(arguments.snapshot)
    destination.write_text(render(snapshot))
    print(destination)


if __name__ == "__main__":
    main()
