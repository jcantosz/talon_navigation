mouse move down <number> | mouse down <number>:
    mouse_nudge(0, number)

mouse move right <number> | mouse right <number>:
    mouse_nudge(number, 0)

mouse move up <number> | mouse up <number>:
    mouse_nudge(0, -1 * number)

mouse move left <number> | mouse left <number>:
    mouse_nudge(-1 * number, 0)

mouse jump down <number> | jump down <number>:
    mouse_nudge(0, 10 * number)

mouse jump right <number> | jump right <number>:
    mouse_nudge(10* number, 0)

mouse jump up <number> | jump up <number>:
    mouse_nudge(0, -10 * number)

mouse jump left <number> | jump left <number>:
    mouse_nudge(-10 * number, 0)

mouse leap down <number> | leap down <number>:
    mouse_nudge(0, 100 * number)

mouse leap right <number> | leap right <number>:
    mouse_nudge(100 * number, 0)

mouse leap up <number> | leap up <number>:
    mouse_nudge(0, -100 * number)

mouse leap left <number> | leap left <number>:
    mouse_nudge(-100 * number, 0)
