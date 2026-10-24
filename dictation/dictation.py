from talon import Context, Module, actions, app

mod = Module()
mod.tag("navigation_dictation", desc="Insert formatted dictation on macOS")
mod.tag("navigation_dictation_long", desc="Allow longer pauses between speech")
mod.tag("navigation_dictation_medium", desc="Allow medium pauses between speech")

ctx = Context()
ctx.matches = "os: mac"
ctx.tags = ["user.navigation_dictation"]

long_ctx = Context()
long_ctx.matches = """
tag: user.navigation_dictation_long
"""
long_ctx.settings["speech.timeout"] = 2.0

medium_ctx = Context()
medium_ctx.matches = """
tag: user.navigation_dictation_medium
"""
medium_ctx.settings["speech.timeout"] = 1.0


@mod.action_class
class Actions:
    def navigation_dictation_insert_words(words: list[str]):
        """Insert a default-command phrase and record it in phrase history."""
        text = " ".join(actions.dictate.replace_words(words))
        actions.user.add_phrase_to_history(text)
        actions.insert(text)

    def navigation_dictation_long():
        """Use a two-second speech timeout until dictate short is spoken."""
        ctx.tags = ["user.navigation_dictation", "user.navigation_dictation_long"]
        app.notify("Dictation timeout set to long")

    def navigation_dictation_medium():
        """Use a one-second speech timeout until dictate short is spoken."""
        ctx.tags = ["user.navigation_dictation", "user.navigation_dictation_medium"]
        app.notify("Dictation timeout set to medium")

    def navigation_dictation_short():
        """Remove the long speech timeout override."""
        ctx.tags = ["user.navigation_dictation"]
        app.notify("Dictation timeout reset")
