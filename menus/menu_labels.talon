os: mac
tag: user.menu_labels_enabled
-

# Override the generic default commands only while our menu navigation is enabled.
# Say a displayed title, or a bare number, to select it.
# Each submenu replaces the previous labels, keeping the same label style.
show menu labels | show menu bar labels | menu labels | men labels | men lab:
    user.menu_labels_show()

# Keep this exact rule separate: the default package has the same exact phrase.
show menu numbers:
    user.menu_labels_show(false)

show menu bar numbers | menu numbers | men numbers | men numb:
    user.menu_labels_show(false)

hide menu labels | hide menu numbers | lab hide | hide lab:
    labels.hide()

# you can also just say <number>
click menu label <number>:
    user.menu_labels_click(number)

move to menu label <number>:
    user.menu_labels_move(number)
