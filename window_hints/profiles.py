"""Declarative pane profiles for window hints (pure, no Talon imports).

A profile is data: which AX nodes mark a pane, what to call it, and which
ancestor supplies the pane's frame. One generic matcher serves every
application; nothing here knows an application name or a child-index path.

Profile schema (JSON):

    {
      "tiles": true,                       optional: report overlaps/coverage
      "max_depth": 40,                     optional: ignore nodes deeper than this
      "scope": "self" | {"ancestor": M},   optional default
      "panes": [
        {"name": "sidebar", "match": M, "scope": ..., "max_depth": 30}
      ]
    }

A matcher M has any of: role, subrole, dom_id, identifier, help, title,
description (exact),
classes (all must be present), class_suffix (some class ends with it). Every
key present must match. Depth is the node's distance from the window root.
"""

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .core import Rect, intersect

MATCH_KEYS = {
    "role",
    "subrole",
    "dom_id",
    "title",
    "description",
    "classes",
    "class_suffix",
    "identifier",
    "help",
}
PROFILE_KEYS = {"tiles", "max_depth", "scope", "panes"}
PANE_KEYS = {"name", "match", "scope", "max_depth"}
NAME_PATTERN = re.compile(r"^[a-z0-9_-]+$")
TOLERANCE = 1.5
MIN_COVERAGE = 0.98
PROFILE_DIRECTORY = Path(__file__).with_name("profiles")


class ProfileError(RuntimeError):
    pass


@dataclass(frozen=True)
class Node:
    path: tuple
    frame: Rect | None
    role: str = ""
    subrole: str = ""
    dom: str = ""
    classes: frozenset = frozenset()
    title: str = ""
    description: str = ""
    ref: object = field(default=None, compare=False, repr=False)
    identifier: str = ""
    help: str = ""


@dataclass(frozen=True)
class Pane:
    name: str
    frame: Rect
    path: tuple
    ref: object = field(default=None, compare=False, repr=False)


def _validate_match(match, where):
    if not isinstance(match, dict) or not match:
        raise ProfileError(f"{where}: match must be a non-empty object")
    unknown = set(match) - MATCH_KEYS
    if unknown:
        raise ProfileError(f"{where}: unknown match keys {sorted(unknown)}")
    for key, value in match.items():
        if key == "classes":
            ok = (
                isinstance(value, list)
                and value
                and all(isinstance(item, str) and item for item in value)
            )
        else:
            ok = isinstance(value, str) and value
        if not ok:
            raise ProfileError(f"{where}: invalid value for {key!r}")


def _validate_scope(scope, where):
    if scope == "self":
        return
    if (
        isinstance(scope, dict)
        and set(scope) == {"ancestor"}
        and isinstance(scope["ancestor"], dict)
    ):
        _validate_match(scope["ancestor"], f"{where}.scope.ancestor")
        return
    raise ProfileError(f'{where}: scope must be "self" or {{"ancestor": matcher}}')


def _validate_depth(value, where):
    if value is not None and (
        not isinstance(value, int) or isinstance(value, bool) or value < 1
    ):
        raise ProfileError(f"{where}: max_depth must be a positive integer")


def validate(profile):
    """Return the profile if well formed; otherwise raise ProfileError."""
    if not isinstance(profile, dict):
        raise ProfileError("profile must be an object")
    unknown = set(profile) - PROFILE_KEYS
    if unknown:
        raise ProfileError(f"unknown profile keys {sorted(unknown)}")
    panes = profile.get("panes")
    if not isinstance(panes, list) or not panes:
        raise ProfileError("profile needs a non-empty panes list")
    if "scope" in profile:
        _validate_scope(profile["scope"], "profile")
    _validate_depth(profile.get("max_depth"), "profile")
    if not isinstance(profile.get("tiles", False), bool):
        raise ProfileError("tiles must be true or false")
    names = set()
    for index, pane in enumerate(panes):
        where = f"panes[{index}]"
        if not isinstance(pane, dict):
            raise ProfileError(f"{where}: must be an object")
        unknown = set(pane) - PANE_KEYS
        if unknown:
            raise ProfileError(f"{where}: unknown keys {sorted(unknown)}")
        name = pane.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ProfileError(f"{where}: name is required")
        if name in names:
            raise ProfileError(f"{where}: duplicate name {name!r}")
        names.add(name)
        _validate_match(pane.get("match"), f"{where} ({name})")
        if "scope" in pane:
            _validate_scope(pane["scope"], f"{where} ({name})")
        _validate_depth(pane.get("max_depth"), f"{where} ({name})")
    return profile


def load_profile(name, directory=PROFILE_DIRECTORY):
    if not NAME_PATTERN.match(name or ""):
        raise ProfileError(f"invalid profile name {name!r}")
    path = Path(directory) / f"{name}.json"
    try:
        data = json.loads(path.read_text())
    except OSError as error:
        raise ProfileError(f"cannot read profile {name!r}: {error}") from error
    except ValueError as error:
        raise ProfileError(f"profile {name!r} is not valid JSON: {error}") from error
    return validate(data)


@lru_cache(maxsize=1)
def application_mapping(value):
    """Validate bundle=profile entries once per configured mapping."""
    mapping = {}
    if not value.strip():
        return mapping
    for entry in value.split(","):
        bundle, separator, profile = (part.strip() for part in entry.partition("="))
        if (
            not separator
            or not bundle
            or any(character.isspace() for character in bundle)
            or not NAME_PATTERN.fullmatch(profile)
        ):
            raise ProfileError(f"invalid bundle=profile mapping entry {entry!r}")
        if bundle in mapping:
            raise ProfileError(f"duplicate application bundle {bundle!r}")
        if not (PROFILE_DIRECTORY / f"{profile}.json").is_file():
            raise ProfileError(f"mapped profile {profile!r} does not exist")
        mapping[bundle] = profile
    return mapping


def matches(node, match):
    if "identifier" in match and node.identifier != match["identifier"]:
        return False
    if "help" in match and node.help != match["help"]:
        return False
    if "role" in match and node.role != match["role"]:
        return False
    if "subrole" in match and node.subrole != match["subrole"]:
        return False
    if "dom_id" in match and node.dom != match["dom_id"]:
        return False
    if "title" in match and node.title != match["title"]:
        return False
    if "description" in match and node.description != match["description"]:
        return False
    if "classes" in match and not set(match["classes"]) <= node.classes:
        return False
    suffix = match.get("class_suffix")
    if suffix and not any(token.endswith(suffix) for token in node.classes):
        return False
    return True


def _usable(rect):
    return rect is not None and rect.width > 0 and rect.height > 0


def _target(node, scope, by_path):
    if scope == "self":
        return node
    for length in range(len(node.path) - 1, -1, -1):
        ancestor = by_path.get(node.path[:length])
        if ancestor is not None and matches(ancestor, scope["ancestor"]):
            return ancestor
    return None


def find_panes(nodes, profile):
    """Panes in profile order. Identical frames collapse; multiple distinct
    frames all get numeric suffixes in tree order. Singletons stay unsuffixed."""
    nodes = list(nodes)
    by_path = {node.path: node for node in nodes}
    default_scope = profile.get("scope", "self")
    default_depth = profile.get("max_depth")
    result = []
    for entry in profile["panes"]:
        scope = entry.get("scope", default_scope)
        depth = entry.get("max_depth", default_depth)
        found = {}
        for node in sorted(nodes, key=lambda item: item.path):
            if depth is not None and len(node.path) > depth:
                continue
            if not matches(node, entry["match"]):
                continue
            target = _target(node, scope, by_path)
            if target is None or not _usable(target.frame):
                continue
            frame = target.frame
            key = (
                round(frame.x),
                round(frame.y),
                round(frame.width),
                round(frame.height),
            )
            found.setdefault(key, (frame, target))
        for index, (frame, target) in enumerate(found.values(), 1):
            name = entry["name"] if len(found) == 1 else f"{entry['name']} {index}"
            result.append(Pane(name, frame, target.path, target.ref))
    return result


def report(panes, window, tiles=False):
    """Overlaps between panes, coverage of the window, and a pass/fail verdict."""
    overlaps = []
    for index, first in enumerate(panes):
        for second in panes[index + 1 :]:
            shared = intersect(first.frame, second.frame)
            if shared and shared.width > TOLERANCE and shared.height > TOLERANCE:
                overlaps.append((first.name, second.name))
    area = sum(pane.frame.width * pane.frame.height for pane in panes)
    total = window.width * window.height if window else 0
    coverage = area / total if total else 0.0
    ok = not tiles or (not overlaps and coverage >= MIN_COVERAGE)
    return {"overlaps": overlaps, "coverage": coverage, "ok": ok}
