# Deploy checklist (draft branch)

**Do not cover production** from this Draft PR.

## Added / touched (this refactor branch)

| Path | Note |
|------|------|
| `docs/ARCHITECTURE.md` | Runtime overview (English) |
| `docs/DEPLOY_CHECKLIST.md` | This file |
| `engine/auto_range.py` | Range detector (candle approx) |
| `engine/sweep_hunter.py` | Sweep proxy |
| `engine/delta_profile.py` | Volume-profile / delta approx |
| `engine/ifvg.py` | Imbalance-zone approx |
| `engine/range_lock.py` | Maps range detector → legacy box fields |
| `engine/scanner.py` | Attaches `evidence` + merge helpers |
| `engine/trend_config.py` | Feature knobs |
| `legacy_quarantine/` | Old one-shot refactor script quarantined |
| `tests/test_auto_range.py` / `tests/test_evidence_proxies.py` | Smoke tests |

## Before any production cutover

- [ ] Draft PR reviewed and marked ready only after explicit OK
- [ ] Full unittest green on target host
- [ ] Shadow run without Telegram send (or dry-run)
- [ ] Confirm `.env` / secrets untouched
- [ ] Rollback path: previous release tag + state JSON backup

## Still open

- Trial weighting not fully on new evidence fields
- Legacy liq / vp / ict adapters still parallel
- Heatmap / 15m participation filter wiring
- Minimal CI + replay harness
