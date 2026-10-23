import logging
import webbrowser
from pathlib import Path

from talon import Module, app

from .command_inventory import REPORTS, write_report

mod = Module()
REPORT_DIRECTORY = Path.home() / ".talon" / "reports" / "talon_navigation"


def generate_and_open(report_type):
    if report_type not in REPORTS:
        raise ValueError(f"Unknown command report: {report_type}")
    destination = REPORT_DIRECTORY / f"{report_type}.html"
    write_report(destination, report_type)
    if not webbrowser.open(destination.as_uri(), new=2):
        raise RuntimeError(f"Unable to open command report: {destination}")
    return destination


@mod.action_class
class Actions:
    def navigation_command_report(report_type: str = "commands"):
        """Generate and open a fresh command inventory, prefix, conflict, or active report."""
        try:
            generate_and_open(report_type)
        except (OSError, ValueError, RuntimeError):
            logging.exception("Unable to generate or open the Talon command report")
            app.notify(
                "Talon command reports",
                "Unable to generate or open the report. See the Talon log for details.",
            )
