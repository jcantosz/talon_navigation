os: mac
tag: user.application_numbers_enabled
-

# The tag makes this more specific than the default package's identical phrase.
show numbers [once]:
    user.accessibility_show_application_numbers()

# The default package's original query, kept for comparison and fallback.
show (legacy | native | talon) numbers [once]:
    labels.show_query("[AXPosition]:action(AXPress)")
