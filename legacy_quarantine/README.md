# Quarantine (repo root)

Dead / one-shot helpers moved off the live entry path. Do not run as an
entrypoint, and do not reattach to scanner / trial / deploy wiring without
an explicit review.

- `apply_refactor.py` — historical one-shot file rewriter; unused by the live
  path. Kept for archaeology only (not executed).
- Engine builders (dual-log / classic-swing / inertial) live under
  `engine/legacy_quarantine/`.
