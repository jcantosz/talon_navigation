os: mac
tag: user.navigation_dictation
-



# For some fields I can't insert using say
#  except sometimes I can if the phrase has punctuation
# I guess when its prose (has punctuation) it goes throught a different path? with the community scripts
# - another thing to note when using say we don't use a $, so commands said in the middle of a say command are interpreted as commands instead of literal text
# we can use speak or prose instead of say, literal, or type for formatted text
#   but we cannot consistently override this, because overrides must match literally, and we would prefer say to end in a $ so it doesn't interpret other commands
# 
# type <phrase> | literal <phrase> | say <phrase>:
#    # help: Type the phrase
#    dictate.phrase(phrase)
#

prose <user.prose>$:
    user.add_phrase_to_history(prose)
    insert(prose)
