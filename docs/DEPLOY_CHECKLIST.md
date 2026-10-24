# Deploy checklist

Ops-only. Do **not** cover production from a Draft PR.

## Scope of this branch (files operators may touch)

| Path | Role |
|------|------|
| `app.py` / `config.py` | App entry + env loading |
| `scripts/run_scanner.py` | Scanner process entry |
| `scripts/run_ci.sh` | Minimal local/CI unittest hook |
| `docs/ci-workflow.example.yml` | Example GitHub Actions workflow (promote when `workflow` scope available) |
| `systemd/smct-scanner.service` | Example unit file |
| `engine/` | Runtime decision / filter code |
| `legacy_quarantine/` | Dead helpers; do not run as entrypoints |
| `engine/legacy_quarantine/` | Peeled builders; tests/shims only |
| `docs/ARCHITECTURE.md` | Runtime overview |
| `docs/DEPLOY_CHECKLIST.md` | This file |
| `tests/` | Unit tests |

## Continuous checks

- **Local / host hook:** `./scripts/run_ci.sh` (or `python -m unittest discover -s tests -p 'test_*.py' -v`).
- **GitHub Actions:** copy `docs/ci-workflow.example.yml` → `.github/workflows/ci.yml` using a credential with the `workflow` scope, then push. Triggers: push to `main` / `refactor/**`, and PRs targeting `main`.

## Pull / install (host)

1. Backup state JSON and the current release tag/commit.
2. `git fetch` and check out the reviewed commit (or tag).
3. Activate the host venv; `pip install -r requirements.txt`.
4. Confirm `SMCT_ENV_FILE` points at the host `.env` (do not commit secrets).
5. Run `./scripts/run_ci.sh` on the host (or the unittest command above).
6. Restart the scanner unit only after a successful dry check (see below).

## Environment keys (placeholders — never commit real values)

Load via `SMCT_ENV_FILE` (default path on host installs: `/opt/smct-alert/config/.env`).

| Key | Purpose |
|-----|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token for outbound alerts |
| `TELEGRAM_CHAT_ID` | Destination chat id |
| `WEBHOOK_SECRET` | Inbound webhook auth |
| `SMCT_ENV_FILE` | Absolute path to the env file |
| `SMCT_SIGNAL_STATE_FILE` | Signal state JSON path |
| `SMCT_RUNTIME_STATE_FILE` | Runtime state JSON path |
| `WEBHOOK_STATE_FILE` | Webhook state JSON path |
| `TREND_SNAPSHOT_STATE_FILE` | Snapshot state JSON path |
| `WEBHOOK_LOG_FILE` | Webhook log path |
| `MARKET_SOURCE` | `binance_futures` (default) or `binance_spot` |
| `BINANCE_SYMBOL` | Symbol (default `BTCUSDT`) |
| `BINANCE_SPOT_KLINES_URL` / `BINANCE_FUTURES_KLINES_URL` | Kline endpoints |
| `KLINE_LIMIT` / `KLINE_LIMIT_15M` | Closed-candle lookback |
| `SCAN_INTERVAL_SECONDS` | Scanner loop interval |
| `ALERT_COOLDOWN_SECONDS` | Alert family cooldown |
| `REQUEST_TIMEOUT_SECONDS` | HTTP timeout |
| `FREEZE_MODE_SEND_X_ONLY` | `1` / `0` delivery freeze flag |
| `SEND_NEAR_MISS_SUMMARY` | `1` / `0` near-miss summary flag |
| `HEARTBEAT_STALE_AFTER_SECONDS` | Heartbeat staleness threshold |
| `TELEGRAM_OPS_POLL_ENABLED` | `1` / `0` enable getUpdates `/check` poll |
| `TELEGRAM_OPS_POLL_LOCK_FILE` | Exclusive flock path (default `/tmp/smct-tg-ops-poll.lock`) |
| `SMCT_REPO_ROOT` | Optional absolute git root for `/check` HEAD |
| `TELEGRAM_ERROR_ALERT_COOLDOWN_SECONDS` | Ops error alert cooldown |
| `WEBHOOK_PERSIST_SECONDS` | Webhook persistence window |

Do not paste production tokens, chat ids, or webhook secrets into git, CI logs, or this checklist.

## systemd (high level)

Example unit: `systemd/smct-scanner.service`.

- Working directory and `ExecStart` point at the host install (example: `/opt/smct-alert`).
- Prefer the host venv interpreter in `ExecStart`.
- After a reviewed cutover: `systemctl daemon-reload` (if the unit changed), then restart the scanner service and confirm it is active.
- Keep `Restart=always` behavior; investigate crash loops via journal before force-restarting again.

Exact unit names and paths are host-local — adjust to the install, do not invent secrets in the unit file.

## Telegram (high level)

- Outbound alerts require a valid `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
- Prefer a shadow / dry run with send disabled (or freeze flags) before enabling live delivery.
- Pending-confirmation state must only be written after a successful send (runtime invariant).
- Rotate or revoke tokens outside git if exposure is suspected.

## Ops Telegram (/check + error-only)

- Timed bihourly probe (`scripts/run_bihourly_report.py`) is **silent on success**; it may still push on health failure.
- Prefer disabling any host cron/timer that only existed to spam the old running heartbeat, or keep it as a silent probe.
- Group `/check` is handled by the webhook app: default **getUpdates poll** when `TELEGRAM_OPS_POLL_ENABLED=1` (requires no Telegram `setWebhook`), or POST `/telegram/updates` if you point Bot API webhook there.
- When **both** `smct-alert` and `smct-webhook` share the same `app:app`, poll uses an exclusive flock (`TELEGRAM_OPS_POLL_LOCK_FILE`, default `/tmp/smct-tg-ops-poll.lock`): only one process runs getUpdates; the other logs `ops_poll_skipped reason=lock_held`. No host unit/.env change required.
- `/check` HEAD resolution prefers `SMCT_REPO_ROOT` (optional) then the install root from `__file__`, not the process cwd.
- Backend exceptions (scanner loop / `run_once`) push a short `⚠️ 系统异常` with cooldown (`TELEGRAM_ERROR_ALERT_COOLDOWN_SECONDS`, default 900).
- Do not change business alert templates in this path.

## Before any production cutover

- [ ] Draft PR reviewed and marked ready only after explicit OK
- [ ] `./scripts/run_ci.sh` (or CI) green on the tip commit
- [ ] Full unittest green on the target host
- [ ] Shadow / dry run without live Telegram send (or freeze mode)
- [ ] Confirm `.env` / secrets untouched by the deploy pull
- [ ] Rollback path ready: previous release tag/commit + state JSON backup

## Rollback

1. Stop or freeze outbound send if alerts are misfiring.
2. Check out the previous known-good tag/commit.
3. Restore state JSON from the pre-cutover backup if needed.
4. Reinstall requirements if dependency pins changed; restart the scanner unit.
5. Confirm heartbeat / one safe scan cycle before re-enabling live send.
