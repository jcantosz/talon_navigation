# Shared macOS accessibility utilities

- [inventory.py](inventory.py): bounded AX tree collection, node metadata and
  formatting, shared by diagnostics and window hints. No Talon registration.
- [surfaces.py](surfaces.py): focused-window and active-menu roots.

Application-control queries and session behavior belong to
[application_controls/](../application_controls/README.md); diagnostic commands
belong to [diagnostics/](../diagnostics/README.md).
