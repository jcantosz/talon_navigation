import time

from talon import Module, actions, app, cron, imgui, settings, speech_system

mod = Module()
mod.setting(
    "sleep_warning",
    type=bool,
    default=True,
    desc="Warn when recognized speech is ignored because Talon is asleep",
)
mod.setting(
    "sleep_warning_use_overlay",
    type=bool,
    default=False,
    desc="Use a temporary Talon overlay instead of native sleep notifications",
)

WARNING_INTERVAL_SECONDS = 30.0
_last_warning = None
_enabled_override = None
_hide_job = None
_resume_job = None
_message = ""


@mod.capture(rule="<number> (second | seconds | minute | minutes | hour | hours)")
def sleep_warning_duration(m) -> int:
    """Convert a spoken duration to seconds using Talon's number capture."""
    unit = str(m[1]).rstrip("s")
    return m.number * {"second": 1, "minute": 60, "hour": 3600}[unit]


@imgui.open()
def warning_gui(gui: imgui.GUI):
    gui.text(_message)


def hide_warning():
    global _hide_job
    warning_gui.hide()
    _hide_job = None


def show_warning(message):
    global _hide_job, _message
    if _hide_job is not None:
        cron.cancel(_hide_job)
        hide_warning()
    if not settings.get("user.sleep_warning_use_overlay"):
        app.notify("Talon sleep warnings", message)
        return
    _message = message
    warning_gui.show()
    _hide_job = cron.after("3s", hide_warning)


def cancel_resume():
    global _resume_job
    if _resume_job is not None:
        cron.cancel(_resume_job)
        _resume_job = None


def enable_warnings():
    global _enabled_override, _last_warning
    cancel_resume()
    _enabled_override = True
    _last_warning = None
    show_warning("Sleep warnings on")


def resume_warnings():
    global _resume_job
    _resume_job = None
    enable_warnings()


@mod.action_class
class Actions:
    def sleep_warning_enable():
        """Enable sleep warnings for this Talon session."""
        enable_warnings()

    def sleep_warning_disable():
        """Disable sleep warnings for this Talon session."""
        global _enabled_override, _last_warning
        cancel_resume()
        _enabled_override = False
        _last_warning = None
        show_warning("Sleep warnings off")

    def sleep_warning_disable_for(seconds: int):
        """Disable sleep warnings temporarily, then automatically enable them."""
        global _enabled_override, _last_warning, _resume_job
        if seconds <= 0:
            raise ValueError("Sleep warning duration must be greater than zero")
        cancel_resume()
        _resume_job = cron.after(f"{seconds}s", resume_warnings)
        _enabled_override = False
        _last_warning = None
        if seconds % 3600 == 0:
            amount, unit = seconds // 3600, "hour"
        elif seconds % 60 == 0:
            amount, unit = seconds // 60, "minute"
        else:
            amount, unit = seconds, "second"
        suffix = "" if amount == 1 else "s"
        show_warning(f"Sleep warnings off for {amount} {unit}{suffix}")


def on_phrase(phrase):
    global _last_warning

    if actions.speech.enabled():
        _last_warning = None
        return
    enabled = (
        settings.get("user.sleep_warning")
        if _enabled_override is None
        else _enabled_override
    )
    if not enabled or not phrase.get("phrase"):
        return

    parsed = phrase.get("parsed", ())
    # The sleep catch-all ignores speech; wake-up and other sleep commands do not.
    if len(parsed) != 1 or parsed[0]._name != "___ltphrase_gt__":
        return

    now = time.monotonic()
    if _last_warning is not None and now - _last_warning < WARNING_INTERVAL_SECONDS:
        return

    show_warning('Talon is asleep. Say "wake up" to enable commands.')
    _last_warning = now


speech_system.register("phrase", on_phrase)
