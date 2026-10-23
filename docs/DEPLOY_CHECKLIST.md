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
| `engine/scanner.py` | Builds `evidence` early; passes to trial |
| `engine/trial_decision.py` / `engine/key_zones.py` | Trial reads `evidence.ifvg` |
| `engine/core_levels_filter.py` | 1H+ soft filter only |
| `engine/formation_shadow.py` | 15m shadow / participation only |
| `engine/trend_config.py` | Feature knobs (`core_levels_filter`, `formation_shadow`; legacy aliases kept) |
| `legacy_quarantine/` | Old one-shot refactor script quarantined |
| `engine/legacy_quarantine/` | Peeled dual-log / classic-swing / inertial builders |
| `tests/test_auto_range.py` / `tests/test_evidence_proxies.py` | Smoke tests |

## Before any production cutover

- [ ] Draft PR reviewed and marked ready only after explicit OK
- [ ] Full unittest green on target host
- [ ] Shadow run without Telegram send (or dry-run)
- [ ] Confirm `.env` / secrets untouched
- [ ] Rollback path: previous release tag + state JSON backup

## Still open

- Dual-log / classic-swing / inertial peeled from live decision weights (builders may remain for tests)
- Trial inverted-imbalance weight reads `evidence.ifvg` (legacy `range_lock.imbalance` fallback remains)
- Broader trial migration onto remaining evidence fields still open
- Legacy liq / vp / ict adapters still parallel
- Deeper `core_levels_filter` / `formation_shadow` participation wiring
- Minimal CI + replay harness
