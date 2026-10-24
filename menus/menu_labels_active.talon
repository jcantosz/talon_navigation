os: mac
tag: user.menu_labels_active
-

# Close one submenu and relabel its parent, preserving titles or numbers.
go back | menu back | men back:
    user.menu_labels_back()

hide (men | menu) (lab | label | labels | num | numb | number | numbers) | (men | menu) hide | hide (men | menu) | (lab | label | labels) hide | hide (lab | label | labels):
    labels.hide()

# you can also just say <number>
[click] [menu] (lab | label | num | numb | number) <number>:
    user.menu_labels_click(number)

move [to] [menu] [lab | label | num | numb | number] <number>:
    user.menu_labels_move(number)