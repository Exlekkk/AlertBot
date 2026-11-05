# Draft notes archive

Detailed writeups for knife / Draft PRs live in this folder.

## Homepage hygiene

- PR **titles** and squash/merge **commit subjects** on `main` must be **short English only**.
- Do **not** put Chinese text, multi-paragraph business locks, or long acceptance notes in the subject (or in a body that GitHub surfaces as the repo homepage last-commit banner).
- Put the full locks, counterexamples, rollback SHAs, and acceptance checklists in a file here (Chinese detail is fine inside this folder).

## Naming

Prefer `pr-<number>-<short-english-slug>.md` for merged knives, e.g. `pr-42-15m-supply-reject-m-top.md`.

## Unified changelog

Bot knife / deploy change log (short English + Chinese note) lives in [`reports/bot_changes.csv`](../../reports/bot_changes.csv). Keep long locks and acceptance notes in this folder; append one CSV row per knife going forward.
