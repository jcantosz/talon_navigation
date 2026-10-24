os: mac
tag: user.menu_labels_enabled
-

# Override the generic default commands only while our menu navigation is enabled.
# Say a displayed title, or a bare number, to select it.
# Each submenu replaces the previous labels, keeping the same label style.
[show] (men | menu) [bar] (lab | label | labels):
    user.menu_labels_show()

# Keep this exact rule separate: the default package has the same exact phrase.
show menu numbers:
    user.menu_labels_show(false)

[show] (men | menu) [bar] (num | numb | number | numbers):
    user.menu_labels_show(false)

