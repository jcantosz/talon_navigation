"""Enable AX interfaces while respecting application exclusions and overrides."""

import logging

from talon import settings, ui

ACCESSIBILITY_ATTRIBUTES = (
    "AXEnhancedUserInterface",
    "AXManualAccessibility",
)


def _activation_disallowed(owner):
    configured = settings.get("user.accessibility_activation_disallowed_bundles")
    bundles = {bundle.strip() for bundle in configured.split(",") if bundle.strip()}
    return owner.bundle in bundles


def set_interfaces(owner, enabled, force=False):
    if enabled and not force and _activation_disallowed(owner):
        return "disallowed", ()

    if enabled:
        # Firefox and other lazy AX providers activate when their app role is read.
        owner.element.get("AXRole")

    changed = []
    for attribute in ACCESSIBILITY_ATTRIBUTES:
        try:
            owner.element[attribute] = enabled
        except ui.UIErr:
            continue
        changed.append(attribute)
    return "updated", tuple(changed)


def application_key(owner):
    return owner.pid, owner.created_at


def prepare(owner, overrides):
    if overrides.get(application_key(owner)) is False:
        return False

    status, changed = set_interfaces(owner, True)
    if status == "disallowed":
        logging.debug(
            "Application labels: AX activation is disallowed for %s (%s)",
            owner.name,
            owner.bundle,
        )
        return False

    logging.debug(
        "Application labels: enabled AX interfaces for %s: %s",
        owner.name,
        changed,
    )
    return True
