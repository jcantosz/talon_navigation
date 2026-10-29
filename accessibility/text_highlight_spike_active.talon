os: mac
tag: user.text_highlight_spike_active
-

highlight next | next:
    user.text_highlight_spike_next()
highlight previous | previous:
    user.text_highlight_spike_previous()
highlight first | first:
    user.text_highlight_spike_first()
highlight last | last:
    user.text_highlight_spike_last()
highlight <number> | <number>:
    user.text_highlight_spike_select(number)
hide highlights | close highlights | cancel highlights:
    user.text_highlight_spike_hide()

key(escape):
    user.text_highlight_spike_hide()
