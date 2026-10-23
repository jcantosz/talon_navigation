from talon import actions, cron


class LabelSession:
    def __init__(self, context, active_tag, names):
        self.context = context
        self.active_tag = active_tag
        self.names = names
        self.job = None
        self.stopped = False
        self.preserve_hide = False

    def render(self, elements):
        if self.stopped:
            return False
        elements = list(elements)
        if self.names:
            actions.labels.show_names(elements)
        else:
            actions.labels.show(elements)
        if self.stopped:
            actions.labels.hide()
            return False
        self.context.tags = [self.active_tag]
        return True

    def start_updates(self, callback, interval="100ms"):
        self.job = cron.interval(interval, callback)

    def hide_for_transition(self):
        self.preserve_hide = True
        try:
            actions.labels.hide()
        finally:
            self.preserve_hide = False

    def stop(self):
        if self.stopped:
            return
        self.stopped = True
        if self.job is not None:
            cron.cancel(self.job)
            self.job = None
        self.context.tags = []
