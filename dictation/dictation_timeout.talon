##

dictate [timeout] long | long dictation [timeout]:
    user.navigation_dictation_long()

dictate [timeout] (mid | medium) | (mid | medium) dictation [timeout]:
    user.navigation_dictation_medium()

dictate [timeout] (short | reset) | (short | reset) dictation [timeout]:
    user.navigation_dictation_short()
