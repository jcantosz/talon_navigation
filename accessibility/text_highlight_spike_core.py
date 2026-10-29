import re
from dataclasses import dataclass

WORD_CHARACTER = r"\w"


@dataclass(frozen=True)
class TextMatch:
    start: int
    end: int
    text: str


def find_matches(content, terms):
    normalized_terms = tuple(
        dict.fromkeys(
            term.strip().casefold()
            for term in terms
            if isinstance(term, str) and term.strip()
        )
    )
    if not normalized_terms:
        return ()

    alternatives = "|".join(
        re.escape(term) for term in sorted(normalized_terms, key=len, reverse=True)
    )
    pattern = re.compile(
        rf"(?<!{WORD_CHARACTER})(?:{alternatives})(?!{WORD_CHARACTER})",
        re.IGNORECASE,
    )
    return tuple(
        TextMatch(match.start(), match.end(), match.group())
        for match in pattern.finditer(content)
    )


def nearest_match_index(matches, caret):
    if not matches:
        raise ValueError("At least one match is required.")

    def distance(match):
        if caret < match.start:
            return match.start - caret
        if caret > match.end:
            return caret - match.end
        return 0

    return min(
        range(len(matches)),
        key=lambda index: (distance(matches[index]), matches[index].start),
    )


def context_snippet(content, match, surrounding_words=4):
    tokens = tuple(re.finditer(r"\S+", content))
    containing = [
        index
        for index, token in enumerate(tokens)
        if token.start() < match.end and token.end() > match.start
    ]
    if not containing:
        return f"[{match.text}]"

    first = max(0, containing[0] - surrounding_words)
    last = min(len(tokens), containing[-1] + surrounding_words + 1)
    segment_start = tokens[first].start()
    segment_end = tokens[last - 1].end()
    segment = (
        content[segment_start : match.start]
        + "["
        + content[match.start : match.end]
        + "]"
        + content[match.end : segment_end]
    )
    collapsed = " ".join(segment.split())
    prefix = "… " if first else ""
    suffix = " …" if last < len(tokens) else ""
    return prefix + collapsed + suffix


def displayed_match_indices(total, current, limit=15):
    if total <= 0:
        return ()
    if not 0 <= current < total:
        raise ValueError("The current match index is out of range.")
    if limit <= 0:
        raise ValueError("The display limit must be positive.")
    if total <= limit:
        return tuple(range(total))

    start = max(0, current - limit // 2)
    start = min(start, total - limit)
    return tuple(range(start, start + limit))
