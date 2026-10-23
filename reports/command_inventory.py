"""Build local, read-only reports of Talon's installed command rules."""

import json
from collections import defaultdict
from datetime import datetime
from html import escape
from itertools import product
from pathlib import Path
from tempfile import NamedTemporaryFile

EXPANSION_LIMIT = 256
REPORTS = {
    "commands": ("All Talon commands", "commands", "all"),
    "prefixes": ("Talon top-level command index", "prefixes", "all"),
    "conflicts": ("Talon command conflicts and potential overlaps", "conflicts", "all"),
    "active": ("Talon active commands", "commands", "active"),
}


class ExpansionLimit(Exception):
    pass


def variants(node):
    """Expand aliases and optional words, retaining references as symbolic tokens."""
    kind = type(node).__name__
    if kind == "Literal":
        return {(node.name.casefold(),)}
    if kind in ("RuleRef", "ListRef"):
        return {(str(node),)}
    if kind == "Rep":
        raise ExpansionLimit("Repeated grammar is not expanded.")
    children = [variants(child) for child in node.children]
    if kind in ("Alt", "Opt"):
        result = set().union(*children)
        if kind == "Opt":
            result.add(())
    elif kind == "Seq":
        result = {()}
        for child in children:
            if len(result) * len(child) > EXPANSION_LIMIT:
                raise ExpansionLimit("Too many alias/optional combinations.")
            result = {left + right for left, right in product(result, child)}
    else:
        raise ExpansionLimit(f"Unsupported grammar node: {kind}.")
    if len(result) > EXPANSION_LIMIT:
        raise ExpansionLimit("Too many alias/optional combinations.")
    return result


def first_tokens(node):
    """Return possible leading tokens even when full expansion is too large."""
    kind = type(node).__name__
    if kind == "Literal":
        return {node.name.casefold()}, False
    if kind in ("RuleRef", "ListRef"):
        return {str(node)}, False
    children = [first_tokens(child) for child in node.children]
    if kind in ("Alt", "Opt"):
        words = set().union(*(words for words, _ in children))
        return words, kind == "Opt" or any(empty for _, empty in children)
    if kind == "Seq":
        words = set()
        for leading, empty in children:
            words.update(leading)
            if not empty:
                return words, False
        return words, True
    if kind == "Rep":
        return children[0]
    raise ValueError(f"Unsupported grammar node: {kind}")


def is_reference(token):
    return token.startswith(("<", "{"))


def could_match(tokens, phrase):
    """Conservative overlap check: each unknown reference consumes 1+ words."""
    reachable = {0}
    for token in tokens:
        next_positions = set()
        for position in reachable:
            if is_reference(token):
                next_positions.update(range(position + 1, len(phrase) + 1))
            elif position < len(phrase) and token == phrase[position]:
                next_positions.add(position + 1)
        reachable = next_positions
        if not reachable:
            return False
    return len(phrase) in reachable


def build_analysis(commands, expansions):
    prefixes = defaultdict(set)
    grammars = defaultdict(set)
    literals = defaultdict(set)
    templates = defaultdict(set)
    for command, forms in zip(commands, expansions, strict=True):
        index = command["id"]
        grammars[(command["grammar"], command["anchor"])].add(index)
        for prefix in command["prefixes"]:
            prefixes[prefix].add(index)
        for form in forms:
            if not form:
                continue
            if any(is_reference(token) for token in form):
                templates[form].add(index)
            else:
                literals[form].add(index)

    def group(label, ids, kind):
        ids = sorted(ids)
        active = sum(commands[index]["active"] for index in ids)
        return {
            "label": label,
            "ids": ids,
            "kind": kind,
            "active": active,
            "files": len({commands[index]["file"] for index in ids}),
            "packages": sorted({commands[index]["package"] for index in ids}),
        }

    duplicates = [
        group(f"{anchor} {grammar}".strip(), ids, "Same grammar")
        for (grammar, anchor), ids in grammars.items()
        if len(ids) > 1
    ]
    overlaps = [
        group(" ".join(phrase), ids, "Shared literal phrase")
        for phrase, ids in literals.items()
        if len(ids) > 1 and len({commands[index]["grammar"] for index in ids}) > 1
    ]
    shared_templates = [
        group(" ".join(form), ids, "Shared symbolic template")
        for form, ids in templates.items()
        if len(ids) > 1 and len({commands[index]["grammar"] for index in ids}) > 1
    ]

    # Compare concrete phrases against references without guessing capture/list contents.
    literal_buckets = defaultdict(list)
    for phrase, ids in literals.items():
        literal_buckets[phrase[0]].append((phrase, ids))
    potential_pairs = defaultdict(set)
    for form, template_ids in templates.items():
        # Capture-led rules have no literal namespace and match almost anything
        # under this approximation. Keep them in the prefix index, not this scan.
        if is_reference(form[0]):
            continue
        for phrase, literal_ids in literal_buckets.get(form[0], []):
            if could_match(form, phrase):
                for template_id in template_ids:
                    other_ids = literal_ids - {template_id}
                    if other_ids:
                        potential_pairs[(" ".join(phrase), " ".join(form))].update(
                            other_ids | {template_id}
                        )
    possible = [
        group(f"{phrase}  ↔  {template}", ids, "Potential reference overlap")
        for (phrase, template), ids in potential_pairs.items()
    ]

    def order(item):
        return (-int(item["active"] > 1), -item["active"], item["label"])

    return {
        "prefixes": sorted(
            (group(prefix, ids, "Shared prefix") for prefix, ids in prefixes.items()),
            key=lambda item: item["label"],
        ),
        "duplicates": sorted(duplicates, key=order),
        "overlaps": sorted(overlaps + shared_templates, key=order),
        "possible": sorted(possible, key=order),
    }


def snapshot():
    from talon import registry, ui

    active_commands = {
        id(command)
        for implementations in registry.commands.values()
        for command in implementations
    }
    active_contexts = set(registry.last_active_contexts)
    commands = []
    expansions = []
    root = Path.home() / ".talon" / "user"
    for context_name, context in sorted(registry.contexts.items()):
        for implementation in context.commands.values():
            rule = implementation.rule
            if rule.root is None:
                raise ValueError(f"Unparsed registered rule: {rule.rule}")
            source = Path(implementation.script.filename).resolve()
            relative = (
                source.relative_to(root) if source.is_relative_to(root) else source
            )
            package = relative.parts[0] if len(relative.parts) > 1 else "(local files)"
            limitation = ""
            try:
                forms = variants(rule.root)
            except ExpansionLimit as error:
                forms = set()
                limitation = str(error)
            leading, _ = first_tokens(rule.root)
            match = context._match
            restrictions = (
                "Global (no context restriction)"
                if type(match).__name__ == "MatchAny"
                else str(match)
            )
            commands.append(
                {
                    "id": len(commands),
                    "rule": rule.rule,
                    "grammar": str(rule.root),
                    "anchor": rule.anchor,
                    "file": str(relative),
                    "uri": source.as_uri(),
                    "line": implementation.lineno,
                    "context": context_name,
                    "matches": restrictions,
                    "package": package,
                    "active": id(implementation) in active_commands,
                    "contextActive": context in active_contexts,
                    "prefixes": sorted(leading),
                    "limitation": limitation,
                }
            )
            expansions.append(forms)
    analysis = build_analysis(commands, expansions)
    active_app = ui.active_app()
    return {
        "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "app": active_app.name,
        "modes": sorted(registry.last_modes),
        "contexts": len(registry.contexts),
        "commands": commands,
        **analysis,
    }


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>__TITLE__</title>
<style>
:root { color-scheme: light dark; font: 15px/1.5 system-ui, sans-serif; }
body { max-width: 1500px; margin: 28px auto; padding: 0 24px; }
h1 { margin-bottom: 8px; } h2 { margin-top: 30px; }
input, select, button { font: inherit; padding: 8px; border: 1px solid #888; border-radius: 5px; }
button, summary { cursor: pointer; } button[aria-pressed="true"] { background: #165bc0; color: white; }
nav, .filters, .pager { display: flex; flex-wrap: wrap; gap: 10px; margin: 16px 0; align-items: center; }
#search { min-width: 280px; flex: 1; }
table { border-collapse: collapse; width: 100%; }
th, td { padding: 9px 12px; border-bottom: 1px solid #9996; vertical-align: top; text-align: left; }
thead { background: #8882; } code { overflow-wrap: anywhere; }
.muted { opacity: .75; } .badge { border-radius: 4px; padding: 2px 6px; background: #8882; white-space: nowrap; }
.active { background: #23844533; } .warn { background: #c9841833; }
.notice { padding: 14px 18px; border-left: 4px solid #3678c8; background: #3678c810; }
.rules { margin: 8px 0; padding-left: 22px; } .rules li { margin-bottom: 10px; }
a { color: light-dark(#155ac0, #8dbaff); } #stats { font-weight: 600; }
.table-scroll { overflow-x: auto; } .small { font-size: .9em; }
</style>
</head>
<body>
<h1>__TITLE__</h1>
<p id="snapshot"></p>
<p id="stats"></p>
<div class="notice">
<strong>This is a local snapshot, not a live command palette.</strong>
All installed contexts are included, even for other operating systems and apps.
“Active now” means present in Talon’s active command registry at export time; it does not mean
every definition wins recognition. Source files and context restrictions are shown.
This report uses no external scripts, assets, network calls, or telemetry.
</div>
<details>
<summary><strong>How to interpret conflicts and coverage</strong></summary>
<ul>
<li><strong>Same grammar:</strong> multiple definitions of the same parsed grammar and anchors.
Some are intentional overrides, or apply to mutually exclusive apps/platforms.</li>
<li><strong>Shared phrases/templates:</strong> different rule patterns expand to the same literal
phrase or symbolic template through aliases and optional words. Anchors and contexts can still distinguish them.</li>
<li><strong>Potential reference overlaps:</strong> a literal phrase might also fit a rule containing
a capture or list. References are conservatively treated as one or more words.
Their actual contents are not evaluated, so these are candidates, not confirmed conflicts.</li>
<li><strong>Top-level words:</strong> an index of possible first words, not formal namespaces.
Sharing a first word is not a conflict. Leading captures/lists appear as symbolic entries.</li>
<li>Repeated rules and rules exceeding 256 alias/optional combinations remain in the complete
inventory and prefix index, but are not expanded for phrase matching. Use “Expansion limited” to find them.</li>
<li>Literal-vs-reference scanning covers rules with literal first words; capture-led rules are
indexed but omitted from that scan. We do not solve capture-vs-capture intersections,
expand dynamic lists, determine future context combinations, rank recognition winners,
or detect phonetic ambiguity. Grammar chaining/anchors can affect recognition.</li>
<li>These are command <em>rules</em>, not every possible utterance. Captures such as
<code>&lt;user.text&gt;</code> can represent unlimited phrases. Hotkeys and non-voice triggers
are not part of the inventory. Source links point to local files; browsers may restrict opening them.</li>
</ul>
</details>
<nav aria-label="Report sections" id="tabs"></nav>
<div class="filters">
<label for="search">Search everything</label>
<input id="search" type="search" placeholder="Word, rule, source file, context, or prefix">
<label for="status">Status</label>
<select id="status">
<option value="all">All installed</option>
<option value="active">At least one active now</option>
<option value="multiple">Two or more active definitions</option>
<option value="limited">Expansion limited</option>
</select>
<label for="package">Package</label><select id="package"></select>
<button id="reset">Reset filters</button>
</div>
<p id="count" aria-live="polite"></p>
<div id="results" class="table-scroll"></div>
<div class="pager">
<button id="previous">Previous</button><span id="page"></span><button id="next">Next</button>
<label for="size">Rows per page</label>
<select id="size"><option>50</option><option>200</option><option value="all">All at once</option></select>
</div>
<noscript>Enable JavaScript to browse this self-contained local inventory.</noscript>
<script id="inventory-data" type="application/json">__DATA__</script>
<script>
"use strict";
const data = JSON.parse(document.getElementById("inventory-data").textContent);
const commands = data.commands;
const $ = id => document.getElementById(id);
data.conflicts = [...data.duplicates, ...data.overlaps, ...data.possible].sort((a,b) =>
  Number(b.active > 1) - Number(a.active > 1) || b.active - a.active || a.label.localeCompare(b.label));
const sections = {
  commands: "All commands", prefixes: "Top-level words", conflicts: "All conflict candidates", duplicates: "Same grammar",
  overlaps: "Shared phrases / templates", possible: "Potential reference overlaps"
};
let section = data.report.section, page = 0;
$("status").value = data.report.status;
const escapeHtml = value => String(value).replace(/[&<>"']/g, ch =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const activeCount = commands.filter(c => c.active).length;
$("snapshot").textContent = `Generated ${data.generated} · Focused app: ${data.app} · Modes: ${data.modes.join(", ")}`;
$("stats").textContent = `${commands.length.toLocaleString()} command definitions · ${activeCount.toLocaleString()} active registry definitions · ${data.contexts} contexts · ${data.prefixes.length} first-word entries`;
for (const [key, label] of Object.entries(sections)) {
  const button = document.createElement("button");
  button.textContent = `${label} (${key === "commands" ? commands.length : data[key].length})`;
  button.dataset.section = key;
  button.addEventListener("click", () => { section = key; page = 0; render(); });
  $("tabs").appendChild(button);
}
for (const name of ["All packages", ...new Set(commands.map(c => c.package).sort())]) {
  const option = document.createElement("option");
  option.textContent = name;
  option.value = name === "All packages" ? "" : name;
  $("package").appendChild(option);
}
const commandSearch = c => [c.rule, c.file, c.context, c.matches, c.package, ...c.prefixes].join(" ").toLowerCase();
const searchable = commands.map(commandSearch);
function commandDetails(c) {
  const state = c.active ? "Active now" : c.contextActive ? "Context active; not in active command registry" : "Inactive context";
  return `<code>${escapeHtml(c.rule)}</code> <span class="badge ${c.active ? "active" : ""}">${state}</span>
    <div class="small"><a href="${escapeHtml(c.uri)}">${escapeHtml(c.file)}:${c.line}</a></div>
    <div class="small muted">${escapeHtml(c.matches)}</div>
    ${c.limitation ? `<div class="small warn">Expansion limited: ${escapeHtml(c.limitation)}</div>` : ""}`;
}
function matchesCommand(c, query) {
  return (!query || searchable[c.id].includes(query)) &&
    (!$("package").value || c.package === $("package").value);
}
function filterRows() {
  const query = $("search").value.trim().toLowerCase();
  const status = $("status").value;
  if (section === "commands") {
    return commands.filter(c => matchesCommand(c, query) &&
      (status !== "active" || c.active) &&
      (status !== "multiple" || false) &&
      (status !== "limited" || c.limitation));
  }
  return data[section].filter(group => {
    const selected = group.ids.map(id => commands[id]).filter(c =>
      !$("package").value || c.package === $("package").value);
    if (!selected.length) return false;
    if (query && !group.label.toLowerCase().includes(query) &&
      !selected.some(c => searchable[c.id].includes(query))) return false;
    // Prefix groups are discovery only: active counts are not conflict counts.
    const active = selected.filter(c => c.active).length;
    return (status !== "active" || active > 0) &&
      (status !== "multiple" || active > 1) &&
      (status !== "limited" || selected.some(c => c.limitation));
  });
}
function render() {
  document.querySelectorAll("#tabs button").forEach(button =>
    button.setAttribute("aria-pressed", String(button.dataset.section === section)));
  const rows = filterRows();
  const size = $("size").value === "all" ? Math.max(1, rows.length) : Number($("size").value);
  const pages = Math.max(1, Math.ceil(rows.length / size));
  page = Math.min(page, pages - 1);
  $("count").textContent = `${rows.length.toLocaleString()} matching ${section === "commands" ? "command definitions" : "groups"}${section === "prefixes" ? " — shared prefixes are not conflicts." : ""}${section === "commands" && $("status").value === "multiple" ? " — choose a conflict section for multi-definition groups." : ""}`;
  const slice = rows.slice(page * size, (page + 1) * size);
  if (section === "commands") {
    $("results").innerHTML = `<table><thead><tr><th>Command rule / status / source / restrictions</th><th>Top-level words</th><th>Package</th></tr></thead><tbody>${
      slice.map(c => `<tr><td>${commandDetails(c)}</td><td>${c.prefixes.map(escapeHtml).join(", ")}</td><td>${escapeHtml(c.package)}</td></tr>`).join("")
    }</tbody></table>`;
  } else {
    $("results").innerHTML = `<table><thead><tr><th>${section === "prefixes" ? "First word / reference" : "Phrase / grammar"}</th><th>Definitions</th><th>Sources and contexts</th></tr></thead><tbody>${
      slice.map(group => `<tr><td><code>${escapeHtml(group.label)}</code><div class="small">${escapeHtml(group.kind)}</div></td>
        <td>${group.ids.length} total<br>${group.active} active now<br>${group.files} files</td>
        <td><details><summary>${escapeHtml(group.packages.join(", "))} — expand all definitions</summary>
        <ul class="rules">${group.ids.map(id => `<li>${commandDetails(commands[id])}</li>`).join("")}</ul></details></td></tr>`).join("")
    }</tbody></table>`;
  }
  $("page").textContent = `Page ${page + 1} of ${pages}`;
  $("previous").disabled = page === 0;
  $("next").disabled = page >= pages - 1;
}
for (const id of ["search", "status", "package", "size"]) {
  $(id).addEventListener(id === "search" ? "input" : "change", () => { page = 0; render(); });
}
$("previous").addEventListener("click", () => { page--; render(); });
$("next").addEventListener("click", () => { page++; render(); });
$("reset").addEventListener("click", () => {
  $("search").value = ""; $("status").value = "all"; $("package").value = ""; page = 0; render();
});
render();
</script>
</body>
</html>
"""


def render_report(data, report_type="commands"):
    title, section, status = REPORTS[report_type]
    data = {**data, "report": {"section": section, "status": status}}
    # The JSON is embedded in a script element; neutralize HTML closing tags.
    encoded = json.dumps(data, ensure_ascii=True).replace("<", "\\u003c")
    return HTML.replace("__TITLE__", escape(title)).replace("__DATA__", encoded)


def write_report(output, report_type="commands"):
    data = snapshot()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    content = render_report(data, report_type)
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent, delete=False
        ) as file:
            temporary = Path(file.name)
            file.write(content)
        temporary.replace(output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(
        json.dumps(
            {
                "report": str(output),
                "commands": len(data["commands"]),
                "active": sum(command["active"] for command in data["commands"]),
                "same_grammar_groups": len(data["duplicates"]),
                "shared_phrase_template_groups": len(data["overlaps"]),
                "potential_reference_groups": len(data["possible"]),
                "prefixes": len(data["prefixes"]),
                "limited": sum(bool(c["limitation"]) for c in data["commands"]),
            },
            indent=2,
        )
    )
    return data


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", choices=REPORTS, default="commands")
    arguments = parser.parse_args()
    write_report(arguments.output, arguments.report)
