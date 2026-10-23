os: mac
tag: user.status_labels_active
-

[status] back:
    user.status_labels_back()

[status] (deet | tails | details) <labels.target>:
    user.status_labels_adjust(labels.target, "details")

[status] (up | ink | increase) <labels.target>:
    user.status_labels_adjust(labels.target, "increase")

[status] (down | deek | decrease) <labels.target>:
    user.status_labels_adjust(labels.target, "decrease")
