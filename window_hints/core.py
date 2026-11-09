"""Pure pane-candidate geometry, rules and scoring for window hints.

No Talon imports: the same functions run on live inventory nodes and on saved
snapshots. See backlog/window-hints.md (WH0-WH2).
"""

from dataclasses import dataclass, field
from math import isfinite

PANE_ROLES = frozenset(
    {
        "AXSplitGroup",
        "AXScrollArea",
        "AXTabGroup",
        "AXToolbar",
        "AXOutline",
        "AXTable",
        "AXList",
        "AXWebArea",
        "AXBrowser",
    }
)
MIN_PANE_SIZE = 40
ROW_TOLERANCE = 8
HINT_INSET = 4


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height

    @property
    def center(self):
        return (self.x + self.width / 2, self.y + self.height / 2)


@dataclass(frozen=True)
class Candidate:
    """One AX container reduced to the fields the rules need."""

    role: str
    frame: Rect
    depth: int = 0
    subrole: str | None = None
    named: bool = False
    ref: object = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class Anchor:
    x: float
    y: float
    underline_start: tuple
    underline_end: tuple


def as_rect(value):
    """Return a Rect for a Talon rect, dict or 4-sequence; None when unusable."""
    if value is None:
        return None
    if isinstance(value, dict):
        parts = [value.get(key) for key in ("x", "y", "width", "height")]
    elif hasattr(value, "width"):
        parts = [value.x, value.y, value.width, value.height]
    else:
        parts = list(value)
    if len(parts) != 4 or not all(
        isinstance(part, (int, float)) and isfinite(part) for part in parts
    ):
        return None
    rect = Rect(*parts)
    return rect if rect.width > 0 and rect.height > 0 else None


def intersect(a, b):
    left, top = max(a.x, b.x), max(a.y, b.y)
    right, bottom = min(a.right, b.right), min(a.bottom, b.bottom)
    if right <= left or bottom <= top:
        return None
    return Rect(left, top, right - left, bottom - top)


def iou(a, b):
    overlap = intersect(a, b)
    if overlap is None:
        return 0.0
    shared = overlap.width * overlap.height
    return shared / (a.width * a.height + b.width * b.height - shared)


def _contains(outer, inner):
    return (
        outer.x <= inner.x
        and outer.y <= inner.y
        and outer.right >= inner.right
        and outer.bottom >= inner.bottom
    )


RULES = ("structural", "named")


def _rank(candidate):
    return (not candidate.named, candidate.depth)


def select_candidates(candidates, window, rule="named", min_size=MIN_PANE_SIZE):
    """Keep pane-like containers clipped to the window.

    structural: any pane role. named: pane role that also has a title,
    description or identifier, so it is a subset of structural. Identical
    frames collapse to the named candidate, then the outermost.
    """
    if rule not in RULES:
        raise ValueError(f"Unknown rule {rule!r}; expected one of {RULES}")
    kept = {}
    for candidate in candidates:
        if candidate.role not in PANE_ROLES:
            continue
        if rule == "named" and not candidate.named:
            continue
        clipped = intersect(candidate.frame, window)
        if clipped is None or min(clipped.width, clipped.height) < min_size:
            continue
        if clipped == window:
            continue
        key = (clipped.x, clipped.y, clipped.width, clipped.height)
        existing = kept.get(key)
        if existing is None or _rank(candidate) < _rank(existing):
            kept[key] = Candidate(
                candidate.role,
                clipped,
                candidate.depth,
                candidate.subrole,
                candidate.named,
                candidate.ref,
            )
    return order_panes(kept.values())


def order_panes(panes):
    """Left to right, then top to bottom, with a few pixels of row tolerance."""
    return sorted(
        panes,
        key=lambda pane: (
            round(pane.frame.x / ROW_TOLERANCE),
            round(pane.frame.y / ROW_TOLERANCE),
            pane.frame.width,
            pane.frame.height,
            pane.role,
        ),
    )


def hint_anchor(rect, inset=HINT_INSET):
    """Top-left hint position inside the pane, plus the pane-width rule."""
    inset = min(inset, rect.width / 2, rect.height / 2)
    x, y = rect.x + inset, rect.y + inset
    return Anchor(x, y, (rect.x, rect.y), (rect.right, rect.y))


def hint_overlaps(anchors, hint_size=(80, 20)):
    """Index pairs of anchors whose hint boxes overlap."""
    width, height = hint_size
    pairs = []
    for i, first in enumerate(anchors):
        for j in range(i + 1, len(anchors)):
            second = anchors[j]
            if abs(first.x - second.x) < width and abs(first.y - second.y) < height:
                pairs.append((i, j))
    return pairs


@dataclass(frozen=True)
class Score:
    matched: tuple
    missed: tuple
    extra: tuple

    @property
    def precision(self):
        total = len(self.matched) + len(self.extra)
        return len(self.matched) / total if total else 1.0

    @property
    def recall(self):
        total = len(self.matched) + len(self.missed)
        return len(self.matched) / total if total else 1.0


def score(truth, panes, threshold=0.8):
    """Match hand-recorded {name: Rect} to candidate panes by best IoU, one to one."""
    pairs = sorted(
        (
            (iou(rect, pane.frame), name, index)
            for name, rect in truth.items()
            for index, pane in enumerate(panes)
        ),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    matched, used_names, used_panes = [], set(), set()
    for value, name, index in pairs:
        if value < threshold:
            break
        if name in used_names or index in used_panes:
            continue
        matched.append((name, index))
        used_names.add(name)
        used_panes.add(index)
    return Score(
        tuple(sorted(matched)),
        tuple(sorted(set(truth) - used_names)),
        tuple(sorted(set(range(len(panes))) - used_panes)),
    )


def pane_count_summary(panes):
    counts = {}
    for pane in panes:
        counts[pane.role] = counts.get(pane.role, 0) + 1
    return counts
