# Accessibility diagnostics

[debug_snapshots.py](debug_snapshots.py) and
[debug_snapshots.talon](debug_snapshots.talon) expose opt-in inventory and
snapshot commands. [snapshots.py](snapshots.py) handles serialization and
redaction. Snapshot output remains in the repository's ignored `ax-trees/`.

The shared traversal and focused-surface utilities live in [ax/](../ax/README.md).
Production control-number sessions do not import these diagnostic commands.
This directory is distinct from the separate incident-recorder work in `debug/`.
