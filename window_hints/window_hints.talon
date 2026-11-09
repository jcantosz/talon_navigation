os: mac
-

settings():
    user.window_hints_applications = """
        com.microsoft.VSCode=vscode,
        com.microsoft.VSCodeInsiders=vscode,
        com.vscodium=vscode,
        co.posit.positron=vscode,
        com.visualstudio.code.oss=vscode,
        com.todesktop.230313mzl4w4u92=vscode,
        com.exafunction.windsurf=vscode,
        com.tinyspeck.slackmacgap=slack,
        com.microsoft.Outlook=outlook
    """

# panes. Then use the existing label commands
# ("move mouse [to] <name or number>", "hide labels").
window hints | show sections: user.window_hints_show("named", true)
window hint numbers: user.window_hints_show("named", false)
window hints all: user.window_hints_show("structural", false)

# extraLabel commands for hiding
hide sections | sections hide: labels.hide()

scroll {user.window_sections} {user.window_section_directions}:
    user.window_section_scroll(window_sections, window_section_directions)

scroll {user.window_sections} {user.window_section_directions} <number_small>:
    user.window_section_scroll(window_sections, window_section_directions, number_small)

number {user.window_sections}:
    user.window_section_number(window_sections)
