mode: command
mode: dictation
mode: sleep
-

^sleep captions hidden$:
    user.sleep_captions_hidden()

^sleep captions default$:
    user.sleep_captions_default()

^captions (enable | on)$:
    user.captions_enable()

^captions (disable | off)$:
    user.captions_disable()
