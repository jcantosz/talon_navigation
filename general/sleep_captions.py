from talon import Module, actions, app, cron, menu

mod = Module()
_enabled = True
_previous_captions = None

def captions_enable():
    """Enable captions without automatic sleep control."""
    global _enabled, _previous_captions
    _enabled = False
    _previous_captions = None
    set_captions(True)
    app.notify("Talon captions", "Captions enabled")

def captions_disable():
    """Disable captions without automatic sleep control."""
    global _enabled, _previous_captions
    _enabled = False
    _previous_captions = None
    set_captions(False)
    app.notify("Talon captions", "Captions disabled")

def caption_item():
    # The native menu owns subtitle state independently of speech._subtitles.
    pending = [menu.menu]
    while pending:
        current = pending.pop()
        for item in current.items:
            if item.attrs.get("name") == "Show Subtitles":
                return item
            submenu = item.attrs.get("submenu")
            if submenu is not None:
                pending.append(submenu)
    raise RuntimeError("Talon's native Show Subtitles menu control was not found")


def set_captions(enabled):
    """Operate the same native toggle as the Show Subtitles menu item."""
    item = caption_item()
    if item.checked != enabled:
        item()


def sync_captions():
    global _previous_captions
    if not _enabled:
        return
    if _previous_captions is None:
        _previous_captions = caption_item().checked
    set_captions(actions.speech.enabled())


@mod.action_class
class Actions:
    def captions_enable():
        """Enable captions without automatic sleep control."""
        captions_enable()

    def captions_disable():
        """Disable captions without automatic sleep control."""
        captions_disable()

    def sleep_captions_hidden():
        """Show native captions while awake and hide them while asleep."""
        global _enabled
        _enabled = True
        sync_captions()
        app.notify("Talon captions", "Automatic sleep captions on")

    def sleep_captions_default():
        """Restore native caption state without automatic sleep control."""
        global _enabled, _previous_captions
        _enabled = False
        if _previous_captions is not None:
            set_captions(_previous_captions)
            _previous_captions = None
        app.notify("Talon captions", "Automatic sleep captions off")


def on_ready():
    sync_captions()
    cron.interval("250ms", sync_captions)


app.register("ready", on_ready)
