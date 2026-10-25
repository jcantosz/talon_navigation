mode: command
mode: dictation
mode: sleep
-

^sleep warnings on$:
    user.sleep_warning_enable()

^sleep warnings (off | disabled)$:
    user.sleep_warning_disable()

^sleep warnings (off | disabled) [for] <user.sleep_warning_duration>$:
    user.sleep_warning_disable_for(sleep_warning_duration)
