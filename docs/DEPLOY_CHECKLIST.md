# Deploy checklist

Ops-only. Do **not** cover production from a Draft PR.

## Scope of this tree (files operators may touch)

| Path | Role |
|------|------|
| `app.py` / `config.py` | App entry + env loading |
| `scripts/run_scanner.py` | Scanner process entry |
| `scripts/run_ci.sh` | Minimal local/CI unittest hook |
| `docs/ci-workflow.example.yml` | Example CI workflow (promote when `workflow` scope available) |
| `systemd/smct-scanner.service` | Example scanner unit file |
| `systemd/smct-15m-shadow.service` | 15m shadow log-only unit (Phase 1; no TG) |
| `systemd/smct-volume-weak-shadow.service` | Unclosed volume weak shadow log-only (TG env default off) |
| `engine/` | Runtime decision / filter code |
| `legacy_quarantine/` | Dead helpers; do not run as entrypoints |
| `docs/ARCHITECTURE.md` | Runtime overview |
| `docs/DEPLOY_CHECKLIST.md` | This file |
| `tests/` | Unit tests |

## Continuous checks

- **Local / host hook:** `./scripts/run_ci.sh` (or `python -m unittest discover -s tests -p 'test_*.py' -v`).
- **CI:** copy `docs/ci-workflow.example.yml` → `.github/workflows/ci.yml` using a credential with the `workflow` scope, then push. Triggers: push to `main` / `refactor/**`, and PRs targeting `main`.

## Pull / install (host)

1. Backup state JSON and the current release tag/commit.
2. `git fetch` and check out the reviewed commit (or tag).
3. Activate the host venv; `pip install -r requirements.txt`.
4. Confirm `SMCT_ENV_FILE` points at the host `.env` (do not commit secrets). Default host path: `/opt/smct-alert/config/.env`.
5. Run `./scripts/run_ci.sh` on the host.
6. Restart units only after a successful dry check (see below).

## Environment keys (placeholders — never commit real values)

Load via `SMCT_ENV_FILE`.

| Key | Purpose |
|-----|---------|
| Notification-channel token / destination | Outbound alert credentials (host env only) |
| `WEBHOOK_SECRET` | Inbound webhook auth |
| `SMCT_ENV_FILE` | Absolute path to the env file |
| `SMCT_SIGNAL_STATE_FILE` | Signal state JSON path |
| `SMCT_RUNTIME_STATE_FILE` | Runtime state JSON path |
| `WEBHOOK_STATE_FILE` | Webhook state JSON path |
| `TREND_SNAPSHOT_STATE_FILE` | Snapshot state JSON path |
| `WEBHOOK_LOG_FILE` | Webhook log path |
| `MARKET_SOURCE` | `binance_futures` (default) or `binance_spot` |
| `BINANCE_SYMBOL` | Symbol (default `BTCUSDT`) |
| Kline endpoint URLs / `KLINE_LIMIT` / `KLINE_LIMIT_15M` | Market data lookback |
| `SCAN_INTERVAL_SECONDS` | Scanner loop interval |
| `ALERT_COOLDOWN_SECONDS` | Alert family cooldown |
| `REQUEST_TIMEOUT_SECONDS` | HTTP timeout |
| `FREEZE_MODE_SEND_X_ONLY` | `1` / `0` delivery freeze flag |
| `SEND_NEAR_MISS_SUMMARY` | `1` / `0` near-miss summary flag |
| `HEARTBEAT_STALE_AFTER_SECONDS` | Heartbeat staleness threshold |
| Ops poll enable / lock file | Exclusive flock so only one process polls ops updates when `smct-alert` and `smct-webhook` share `app:app` |
| `SMCT_REPO_ROOT` | Optional absolute git root for ops status HEAD |
| Ops error alert cooldown | Cooldown for backend exception notices |
| `WEBHOOK_PERSIST_SECONDS` | Webhook persistence window |

Do not paste production tokens, destinations, or webhook secrets into git, CI logs, or this checklist.

## systemd (high level)

Example units: `systemd/smct-scanner.service`, `systemd/smct-15m-shadow.service`, `systemd/smct-volume-weak-shadow.service`.

Host units commonly used in production:

- `smct-scanner`
- `smct-alert`
- `smct-webhook`
- `smct-volume-weak-shadow` — unclosed volume weak shadow log-only (`scripts/run_volume_weak_shadow.py --shadow`); TG `SMCT_ABNORMAL_VOLUME_WEAK_ENABLED` stays off until calibrated.
- `smct-15m-shadow` — 15m shadow log-only (`scripts/run_15m_shadow.py --shadow`); enable/restart with the other units when restoring resident shadow. Does **not** require enabling TG weak reminders (`SMCT_15M_WEAK_REMINDER_ENABLED` stays off for Phase 1).

- Working directory and `ExecStart` point at the host install (example: `/opt/smct-alert`).
- Prefer the host venv interpreter in `ExecStart`.
- After a reviewed cutover: `systemctl daemon-reload` (if the unit changed), then restart the active units (including `smct-15m-shadow` when used) and confirm they are active.
- Keep `Restart=always`; investigate crash loops via journal before force-restarting again.

Exact unit names and paths are host-local — adjust to the install; do not invent secrets in the unit file.

## Notification channel (high level)

- Outbound alerts require valid credentials in the host env file.
- Prefer a shadow / dry run with send disabled (or freeze flags) before enabling live delivery.
- Pending-confirmation state must only be written after a successful send (runtime invariant).
- Rotate or revoke credentials outside git if exposure is suspected.
- `FREEZE_MODE_SEND_X_ONLY=1` restricts live delivery while freeze is on.

## Ops status helpers

- Timed bihourly probe (`scripts/run_bihourly_report.py`) is **silent on success**; it may still push on health failure.
- Prefer disabling any host cron/timer that only existed to spam an old running heartbeat, or keep it as a silent probe.
- When both `smct-alert` and `smct-webhook` share the same `app:app`, ops polling uses an exclusive flock so only one process runs the poller.
- Ops HEAD resolution prefers `SMCT_REPO_ROOT` (optional) then the install root from `__file__`, not the process cwd.
- Backend exceptions (scanner loop / `run_once`) may push a short system notice with cooldown.
- Do not change business alert templates in the ops path.

## Before any production cutover

- [ ] Draft PR reviewed and marked ready only after explicit OK
- [ ] `./scripts/run_ci.sh` (or CI) green on the tip commit
- [ ] Full unittest green on the target host
- [ ] Shadow / dry run without live send (or freeze mode)
- [ ] Confirm `.env` / secrets untouched by the deploy pull
- [ ] Rollback path ready: previous release tag/commit + state JSON backup

## Rollback

1. Stop or freeze outbound send if alerts are misfiring (`FREEZE_MODE_SEND_X_ONLY=1` or stop units).
2. Check out the previous known-good tag/commit.
3. Restore state JSON from the pre-cutover backup if needed.
4. Reinstall requirements if dependency pins changed; restart `smct-alert`, `smct-scanner`, `smct-webhook`, and `smct-15m-shadow` (if installed).
5. Confirm heartbeat / one safe scan cycle before re-enabling live send.
