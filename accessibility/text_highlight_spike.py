import logging

from talon import Context, Module, actions, app, imgui, ui
from talon.types import Span

from .text_highlight_spike_core import (
    context_snippet,
    displayed_match_indices,
    find_matches,
    nearest_match_index,
    python_index_to_utf16,
    utf16_index_to_python,
)

mod = Module()
mod.tag(
    "text_highlight_spike_active",
    desc="Selecting word matches in the focused editable accessibility element",
)
tag_ctx = Context()
tag_ctx.matches = """
os: mac
"""

EDITABLE_ROLES = {
    "AXComboBox",
    "AXSearchField",
    "AXTextArea",
    "AXTextField",
}
DISPLAY_LIMIT = 15

_previous_session = globals().get("_session")
_session = None
if _previous_session is not None:
    _previous_session.stop()


class HighlightSession:
    def __init__(self, owner, window_id, element, content, offset, matches, current):
        self.owner = owner
        self.window_id = window_id
        self.element = element
        self.content = content
        self.offset = offset
        self.matches = matches
        self.current = current
        self.stopped = False
        self.focus_reliable = False

    def start(self):
        self.select(self.current)
        tag_ctx.tags = ["user.text_highlight_spike_active"]
        highlight_gui.show()

    def validate(self):
        if self.stopped:
            raise RuntimeError("The word highlight session is no longer active.")
        if ui.active_app().pid != self.owner.pid:
            raise RuntimeError("The active application changed.")
        if ui.active_window().id != self.window_id:
            raise RuntimeError("The active window changed.")
        if self.focus_reliable and self.element.get("AXFocused") is False:
            raise RuntimeError("The focused editable element changed.")
        if self.element.get("AXValue") != self.content:
            raise RuntimeError("The editable text changed.")
        if _shared_offset(self.element) != self.offset:
            raise RuntimeError("The editable text range changed.")

    def select(self, index):
        self.validate()
        if not 0 <= index < len(self.matches):
            raise IndexError("That match number is out of range.")

        match = self.matches[index]
        start = self.offset + python_index_to_utf16(self.content, match.start)
        end = self.offset + python_index_to_utf16(self.content, match.end)
        selected_range = None
        for _attempt in range(2):
            was_focused = self.element.get("AXFocused") is True
            self.element["AXFocused"] = True
            if not was_focused:
                actions.sleep("100ms")
            self.element["AXSelectedTextRange"] = Span(start, end)
            actions.sleep("100ms")
            selected_range = self.element.get("AXSelectedTextRange")
            if (
                selected_range is not None
                and selected_range.left == start
                and selected_range.right == end
            ):
                break
        else:
            raise RuntimeError("The application did not select the requested word.")
        self.focus_reliable = self.element.get("AXFocused") is True
        self.current = index

    def move(self, amount):
        self.select((self.current + amount) % len(self.matches))

    def stop(self):
        if self.stopped:
            return
        self.stopped = True
        tag_ctx.tags = []
        highlight_gui.hide()


def _stop():
    global _session
    if _session is not None:
        _session.stop()
    _session = None


def _notify_error(message):
    logging.exception("Text highlight spike: %s", message)
    _stop()
    app.notify("Highlight word", message)


def _editable_element():
    try:
        element = actions.user.dictation_current_element()
    except RuntimeError:
        actions.user.accessibility_prepare_active_app()
        actions.sleep("200ms")
        element = actions.user.dictation_current_element()
    if element is None:
        raise RuntimeError("There is no focused accessibility element.")
    if element.get("AXRole") in EDITABLE_ROLES:
        return element

    ancestor = element.get("AXEditableAncestor")
    if ancestor is not None and hasattr(ancestor, "get"):
        return ancestor
    raise RuntimeError("The focused accessibility element is not editable.")


def _shared_offset(element):
    shared_range = element.get("AXSharedCharacterRange")
    if shared_range is None or shared_range.left is None:
        return 0
    return shared_range.left


def _buffer(element):
    content = element.get("AXValue")
    if not isinstance(content, str):
        raise RuntimeError("The focused editable element does not expose text.")

    selection = element.get("AXSelectedTextRange") or Span(0, 0)
    offset = _shared_offset(element)
    selection_right = selection.right if selection.right is not None else offset
    caret = utf16_index_to_python(content, selection_right - offset)
    return content, offset, caret


def _matching_terms(word):
    terms = [word]
    try:
        homophones = actions.user.homophones_get(word)
    except KeyError:
        # Talon raises KeyError when the Community homophones action is absent.
        logging.exception("Text highlight spike: homophones action unavailable")
        app.notify(
            "Highlight word",
            "Homophones are unavailable; matching the exact word only.",
        )
        homophones = None
    except ui.ActionFailed:
        logging.exception("Text highlight spike: homophone lookup failed")
        app.notify(
            "Highlight word",
            "Homophone lookup failed; matching the exact word only.",
        )
        homophones = None
    if homophones:
        terms.extend(homophones)
    return terms


def _start(word):
    global _session
    _stop()
    owner = ui.active_app()
    if owner is None:
        app.notify("Highlight word", "There is no active application.")
        return

    try:
        element = _editable_element()
        content, offset, caret = _buffer(element)
        matches = find_matches(content, _matching_terms(word))
        if not matches:
            app.notify(
                "Highlight word",
                f'No exact or known homophone matches for "{word}".',
            )
            return
        current = nearest_match_index(matches, caret)
        _session = HighlightSession(
            owner,
            ui.active_window().id,
            element,
            content,
            offset,
            matches,
            current,
        )
        _session.start()
    except (RuntimeError, ui.UIErr, ui.ActionFailed):
        _notify_error("Unable to start word highlighting.")


def _run(operation):
    if _session is None:
        app.notify("Highlight word", "There is no active word highlight session.")
        return
    try:
        operation(_session)
    except (IndexError, RuntimeError, ui.UIErr):
        _notify_error("Unable to update the highlighted word.")


def _event_pid(event):
    if hasattr(event, "pid"):
        return event.pid
    owner = getattr(event, "app", None)
    return owner.pid if owner is not None else None


def _focus_changed(event):
    if _session is not None and _event_pid(event) != _session.owner.pid:
        _stop()


def _element_changed(*_event):
    if _session is None:
        return
    try:
        if (
            _session.focus_reliable and _session.element.get("AXFocused") is False
        ) or _session.element.get("AXValue") != _session.content:
            _stop()
    except ui.UIErr:
        _notify_error("The highlighted editable element is no longer available.")


@imgui.open()
def highlight_gui(gui: imgui.GUI):
    if _session is None or _session.stopped:
        return

    gui.text(f"Word matches — {_session.current + 1} of {len(_session.matches)}")
    gui.line()
    for index in displayed_match_indices(
        len(_session.matches),
        _session.current,
        DISPLAY_LIMIT,
    ):
        marker = "→ " if index == _session.current else "  "
        snippet = context_snippet(_session.content, _session.matches[index])
        if gui.button(f"{marker}{index + 1}: {snippet}"):
            actions.user.text_highlight_spike_select(index + 1)
    if len(_session.matches) > DISPLAY_LIMIT:
        gui.text("Use next/previous to view additional matches.")
    gui.line()
    if gui.button("Close highlights"):
        actions.user.text_highlight_spike_hide()


@mod.action_class
class Actions:
    def text_highlight_spike_start(word: str):
        """Highlight the nearest editable occurrence of a word or known homophone."""
        _start(word.strip())

    def text_highlight_spike_next():
        """Highlight the next word match."""
        _run(lambda session: session.move(1))

    def text_highlight_spike_previous():
        """Highlight the previous word match."""
        _run(lambda session: session.move(-1))

    def text_highlight_spike_first():
        """Highlight the first word match."""
        _run(lambda session: session.select(0))

    def text_highlight_spike_last():
        """Highlight the last word match."""
        _run(lambda session: session.select(len(session.matches) - 1))

    def text_highlight_spike_select(number: int):
        """Highlight a numbered word match."""
        _run(lambda session: session.select(number - 1))

    def text_highlight_spike_hide():
        """Close the word highlight session while preserving the selection."""
        _stop()


ui.register("win_focus", _focus_changed)
ui.register("app_activate", _focus_changed)
ui.register("element", _element_changed)
