mode: command
mode: dictation
mode: sleep
-

# Sleep only the machine whose configured name or operating system is spoken.
^sleep {user.targeted_sleep_target}$:
    speech.disable()

^{user.targeted_sleep_target} sleep$:
    speech.disable()

# Wake only the machine whose configured name or operating system is spoken.
^wake [up] {user.targeted_sleep_target}$:
    speech.enable()

^{user.targeted_sleep_target} wake [up]$:
    speech.enable()
