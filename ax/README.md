# Shared macOS accessibility utilities

- [inventory.py](inventory.py): bounded AX tree collection, node metadata and
  formatting, shared by diagnostics and window hints. No Talon registration.
- [surfaces.py](surfaces.py): focused-window and active-menu roots.

`collect` optionally accepts `max_depth` (root depth zero) and `stop_roles`.
Boundary nodes are included without reading their children. Both options are
opt-in; diagnostic and application-control callers retain the default walk.
Window-hint profiles use these bounds to stop control content overwhelming
pane discovery.

Application-control queries and session behavior belong to
[application_controls/](../application_controls/README.md); diagnostic commands
belong to [diagnostics/](../diagnostics/README.md).
