"""Own visible section labels and coalesce supported focus events."""

import logging
from contextlib import contextmanager

from talon import actions, app, cron, ui


class FocusChanged(RuntimeError):
    pass


class HintSession:
    def __init__(self, context, render):
        self.context = context
        self.render = render
        self.mode = None
        self.job = None
        self.rendering = False
        self.revision = 0

    def stop(self):
        self.revision += 1
        self.mode = None
        if self.job is not None:
            cron.cancel(self.job)
            self.job = None
        self.context.tags = []

    def show(self, rule, names):
        self.stop()
        actions.labels.hide()
        self.mode = (rule, names)
        self.context.tags = ["user.window_hints_active"]
        self._refresh()

    @contextmanager
    def drawing(self):
        self.rendering = True
        self.context.tags = []
        try:
            yield
        finally:
            self.rendering = False
            if self.mode is not None:
                self.context.tags = ["user.window_hints_active"]

    def focus_changed(self, *_):
        if self.mode is None:
            return
        self.revision += 1
        if self.job is not None:
            cron.cancel(self.job)
        with self.drawing():
            actions.labels.hide()
        self.job = cron.after("100ms", self._refresh)

    def _refresh(self):
        self.job = None
        if self.mode is None:
            return
        try:
            self.render(*self.mode)
        except FocusChanged:
            if self.mode is not None and self.job is None:
                self.focus_changed()
        except (AttributeError, TypeError, ValueError, RuntimeError, ui.UIErr):
            logging.exception("Window hints failed")
            self.stop()
            actions.labels.hide()
            app.notify("Window hints", "Unable to label panes; see the Talon log.")

    def replaced(self):
        if not self.rendering:
            self.stop()
