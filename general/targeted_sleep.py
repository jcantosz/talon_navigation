import platform
import re
import socket

from talon import Context, Module, cron, settings

mod = Module()
ctx = Context()

DEFAULT_MACHINE_NAME = socket.gethostname().split(".", 1)[0]
OS_TARGETS = {
    "darwin": ("mac", "mac os"),
    "linux": ("linux",),
    "windows": ("windows", "microsoft"),
}

mod.setting(
    "targeted_sleep_name",
    type=str,
    default=DEFAULT_MACHINE_NAME,
    desc="Fallback spoken machine name accepted by targeted wake and sleep commands",
)
mod.setting(
    "targeted_sleep_names",
    type=str,
    default="",
    desc="Comma-separated spoken machine names accepted by targeted wake and sleep commands",
)
mod.list(
    "targeted_sleep_target",
    desc="Names that target wake and sleep commands at this machine",
)


def spoken_form(name):
    """Convert a configured name or hostname into a Talon-friendly spoken form."""
    return re.sub(r"[^a-z0-9]+", " ", name.casefold()).strip()


def targeted_sleep_targets(machine_names, system_name):
    names = [spoken_form(name) for name in machine_names.split(",")]
    if any(not name for name in names):
        raise ValueError(
            "user.targeted_sleep_names must be a comma-separated list of names"
        )
    targets = {name: "machine" for name in names}
    targets.update(
        {spoken: "operating-system" for spoken in OS_TARGETS.get(system_name.casefold(), ())}
    )
    return targets


_current_targets = targeted_sleep_targets(DEFAULT_MACHINE_NAME, platform.system())
ctx.lists["user.targeted_sleep_target"] = _current_targets


def configured_machine_names():
    names = settings.get("user.targeted_sleep_names").strip()
    return names or settings.get("user.targeted_sleep_name")


def refresh_targeted_sleep_targets():
    global _current_targets
    targets = targeted_sleep_targets(configured_machine_names(), platform.system())
    if targets != _current_targets:
        ctx.lists["user.targeted_sleep_target"] = targets
        _current_targets = targets


cron.interval("1s", refresh_targeted_sleep_targets)
