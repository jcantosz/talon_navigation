# Repository agent guidance

Follow the [project principles](backlog/README.md#project-principles) and the
current feature documentation before changing behavior.

## Superseded features

When implementing a feature that supersedes an old implementation, remove
the obsolete code, configuration and files as part of the same change.
Update callers, tests and documentation to exercise the replacement; do not
keep a redundant implementation solely as a test baseline. Retain old behavior
only for an explicit, documented compatibility requirement.

## Implementation spike completion

After each implementation spike, explicitly review whether the code is the best
solution: efficient, clean, and maintainable. Check for redundant work,
unnecessary state or abstractions, and opportunities to reuse existing resources.
Measure user-facing interaction costs and test the required behavior, including
failure and lifecycle cases; passing unit tests alone is not enough.
Do not declare completion or deliver a partially working implementation. Verify
the feature end to end and preserve existing behavior. Record the review,
validation evidence, and any remaining limitations before proceeding.
