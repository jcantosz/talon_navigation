mode: command
mode: dictation
mode: sleep
-

# Sleep only the machine whose configured name or operating system is spoken.
^ sleep {user.targeted_sleep_target} | stop listening {user.targeted_sleep_target} $:
    speech.disable()

^ {user.targeted_sleep_target} sleep | {user.targeted_sleep_target} stop listening $:
    speech.disable()

# Wake only the machine whose configured name or operating system is spoken.
^ (wake | listen) [up] {user.targeted_sleep_target} | start listening {user.targeted_sleep_target} $:
    speech.enable()

^ {user.targeted_sleep_target} (listen | wake) [up] | {user.targeted_sleep_target} start listening $:
    speech.enable()
