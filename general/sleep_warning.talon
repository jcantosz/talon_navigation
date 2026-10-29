mode: command
mode: dictation
mode: sleep
-

^ sleep warnings on | show sleep warnings $:
    user.sleep_warning_enable()

^ sleep warnings (off | disabled) | hide sleep warnings $:
    user.sleep_warning_disable()

^ sleep warnings (off | disabled) [for] <user.sleep_warning_duration> | hide sleep warnings [for] <user.sleep_warning_duration> $:
    user.sleep_warning_disable_for(sleep_warning_duration)
