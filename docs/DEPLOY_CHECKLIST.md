# Deploy checklist

Ops-only. Do **not** cover production from a Draft PR.

## Scope of this tree (files operators may touch)

| Path | Role |
|------|------|
| `app.py` / `config.py` | App entry + env loading |
| `scripts/run_scanner.py` | Scanner process entry |
| `scripts/run_ci.sh` | Minimal local/CI unittest hook |
| `docs/ci-workflow.example.yml` | Example CI workflow (promote when `workflow` scope available) |
| `systemd/amst-alert.service` | Example app unit (`0.0.0.0:80`) |
| `systemd/amst-scanner.service` | Example scanner unit file (includes `PYTHONPATH`) |
| `systemd/amst-scanner.service.d/90-alertbot-early-shadow.conf` | Scanner drop-in; `AMST_*` + legacy `SMCT_*` env keys |
| `systemd/amst-webhook.service` | Example webhook unit (`127.0.0.1:8000`) |
| `systemd/amst-15m-shadow.service` | 15m shadow log-only unit (Phase 1; no TG) |
| `systemd/amst-volume-weak-shadow.service` | Unclosed volume weak shadow log-only (TG env default off) |
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
4. Confirm `AMST_ENV_FILE` points at the host `.env` (do not commit secrets). Default host path: `/opt/amst-alert/config/.env`.
5. Run `./scripts/run_ci.sh` on the host.
6. Restart units only after a successful dry check (see below).

## Environment keys (placeholders — never commit real values)

Load via `AMST_ENV_FILE`. Prefixed keys (`ENV_FILE`, `SIGNAL_STATE_FILE`, `RUNTIME_STATE_FILE`, `REPO_ROOT`, `ABNORMAL_VOLUME_WEAK_ENABLED`) read `AMST_*` first and fall back to `SMCT_*` if unset or empty. Keys without an `AMST_`/`SMCT_` prefix are unchanged; only their default path prefixes moved to `/opt/amst-alert` or `/tmp/amst-tg-ops-poll.lock`.

| Key | Purpose |
|-----|---------|
| Notification-channel token / destination | Outbound alert credentials (host env only) |
| `WEBHOOK_SECRET` | Inbound webhook auth |
| `AMST_ENV_FILE` | Absolute path to the env file |
| `AMST_SIGNAL_STATE_FILE` | Signal state JSON path |
| `AMST_RUNTIME_STATE_FILE` | Runtime state JSON path |
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
| Ops poll enable / lock file | Exclusive flock so only one process polls ops updates when `amst-alert` and `amst-webhook` share `app:app` |
| `AMST_REPO_ROOT` | Optional absolute git root for ops status HEAD |
| Ops error alert cooldown | Cooldown for backend exception notices |
| `WEBHOOK_PERSIST_SECONDS` | Webhook persistence window |

Do not paste production tokens, destinations, or webhook secrets into git, CI logs, or this checklist.

## systemd (high level)

Example units: `systemd/amst-alert.service`, `systemd/amst-scanner.service`, `systemd/amst-webhook.service`, `systemd/amst-15m-shadow.service`, `systemd/amst-volume-weak-shadow.service`, plus `systemd/amst-scanner.service.d/90-alertbot-early-shadow.conf`.

Host units commonly used in production:

- `amst-scanner`
- `amst-alert`
- `amst-webhook`
- `amst-volume-weak-shadow` — unclosed volume weak shadow log-only (`scripts/run_volume_weak_shadow.py --shadow`); TG `AMST_ABNORMAL_VOLUME_WEAK_ENABLED` stays off until calibrated.
- `amst-15m-shadow` — 15m shadow log-only (`scripts/run_15m_shadow.py --shadow`); enable/restart with the other units when restoring resident shadow. Does **not** require enabling TG weak reminders (`AMST_15M_WEAK_REMINDER_ENABLED` stays off for Phase 1).

- Working directory and `ExecStart` point at the host install (example: `/opt/amst-alert`).
- Prefer the host venv interpreter in `ExecStart`.
- After a reviewed cutover: `systemctl daemon-reload` (if the unit changed), then restart the active units (including `amst-15m-shadow` when used) and confirm they are active.
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
- When both `amst-alert` and `amst-webhook` share the same `app:app`, ops polling uses an exclusive flock so only one process runs the poller.
- Ops HEAD resolution prefers `AMST_REPO_ROOT` (optional) then the install root from `__file__`, not the process cwd.
- Backend exceptions (scanner loop / `run_once`) may push a short system notice with cooldown.
- Do not change business alert templates in the ops path.

## SMCT → AMST host rename (future window; not executed in this PR)

Repo display names and unit templates already use AMST. The GitHub repo stays `Exlekkk/AlertBot`. Do **not** ship or run a cutover script from this PR. When L + user later approve a host window, the locked ops shape is:

- Install root moves `/opt/smct-alert` → `/opt/amst-alert` as a whole-tree rename (including `config/.env`, `logs/`, `state/`, `venv/`). Abort if the target already exists; do not overwrite.
- Soak-period symlink: `/opt/smct-alert` → `/opt/amst-alert`, so a rollback to old unit files still finds the tree. Remove the symlink only after a decided soak.
- Old `smct-*` units: `disable` + `mask`, and **keep the unit files** until rollback is no longer needed.
- Host env: update **only** path values on `WEBHOOK_LOG_FILE` (both occurrences; this window does not dedupe or rewrite the file), `SMCT_SIGNAL_STATE_FILE` / `AMST_SIGNAL_STATE_FILE`, `SMCT_RUNTIME_STATE_FILE` / `AMST_RUNTIME_STATE_FILE`, and `WEBHOOK_STATE_FILE`. Do not change other secret values. If key names are flipped to `AMST_*` at the same time, keep a server-local copy of the previous env file (not in git).
- Rename rollback means moving the directory back and restoring the previous units / cron / env copy. It is **not** a tip rollback to `8e3dbea`.
- A short outage is unavoidable (port 80 / 8000 cannot be bound twice; do not run old and new scanners together). Rewrite venv shebangs that still point at `/opt/smct-alert`.

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
4. Reinstall requirements if dependency pins changed; restart `amst-alert`, `amst-scanner`, `amst-webhook`, and `amst-15m-shadow` (if installed).
5. Confirm heartbeat / one safe scan cycle before re-enabling live send.
