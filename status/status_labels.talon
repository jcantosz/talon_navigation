os: mac
-

[show] (stat | status) (lab | label | labels):
    user.status_labels_show()

[show] (stat | status) (num | numb | number | numbers):
    user.status_labels_show(false)

refresh status labels:
    user.status_labels_refresh()

refresh status numbers:
    user.status_labels_refresh(false)

hide [(stat | status)] (lab | label | labels | num | numb | number | numbers):
    labels.hide()
