---
name: repo-conventions
description: Conventions and validation for the aiops repository. Always active.
always: true
metadata:
  validate_cmd: "python -m pytest -q"
---

# aiops conventions

- PR titles must be prefixed with `[aiops-agent]`.
- Every new function's docstring must end with the tag [aiops].
