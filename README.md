# AlertBot

AlertBot is a BTCUSDT closed-candle alert engine. It watches higher-timeframe bias, emits selective formal alerts on the primary structure timeframe, and keeps a lower-timeframe path in shadow for diagnostics. Stocks and multi-asset scanning are out of scope.

## How it works

### Timeframe roles

| Layer | Role |
|-------|------|
| **4H** | Background bias only. Sets directional context; does not emit formal trade alerts by itself. |
| **1H** | Formal alert layer. Structure, evidence weighting, and delivery decisions run here. |
| **15m** | Shadow only. Records possible entry-location timing for review; does not change 1H conclusions, cooldowns, or live delivery. |

Flow in one line: **4H bias → 1H formal alerts → 15m shadow**.

### Selective alerts over spam

The engine prefers fewer, higher-quality alerts over frequent noise:

- Cooldown and dedupe suppress repeated families in the same practical area.
- Range / accumulation context reduces duplicate observations without blanket-blocking a valid early trial when evidence is asymmetric.
- Opposite formal trials in the same box need fresh structure information.
- 15m cadence follows new-information quality, not a hard daily cap.

### Evidence gating (pending vs accepted)

Decisions use candle-based evidence bundles with approximate / proxy flags. Neutral rules:

- **Pending** evidence can inform weighting; it is not the same as an accepted structural event.
- **Accepted** means the engine treated the event as confirmed enough to act on (for example after a successful closed-candle validation).
- Delivery state for a pending confirmation is written only after a successful send on the configured notification channel.
- Auxiliary filters add timing or confidence; they are never standalone triggers.

Exact indicator brands, chart-vendor scripts, and strategy jargon are intentionally omitted from this public README. Runtime modules under `engine/` implement the live path.

## Runtime surfaces

| Surface | Role |
|---------|------|
| Scanner (`scripts/run_scanner.py` → `engine/scanner.py`) | Main 1H loop |
| App / webhook process (`app.py`) | HTTP entry, ops helpers, inbound webhook |
| Shadow / 15m path | Server-side diagnostics; not live formal delivery |
| Notification channel | Outbound alerts; credentials via env (never commit secrets) |
| State JSON | Runtime + signal persistence (atomic writes) |

## Install

Typical host layout uses `/opt/smct-alert` as the install root and a local venv.

```bash
sudo mkdir -p /opt/smct-alert
sudo rsync -a --exclude '.git' --exclude '.env' --exclude 'config/.env' \
  --exclude 'venv' --exclude 'logs' --exclude 'state' \
  ./ /opt/smct-alert/
cd /opt/smct-alert
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

Copy `.env.example` to the host env file (default: `/opt/smct-alert/config/.env`) and fill secrets locally. Point `SMCT_ENV_FILE` at that absolute path if it is not the default.

Do not commit tokens, chat ids, webhook secrets, or production `.env` files.

## Configuration

Load env via `SMCT_ENV_FILE` (see `.env.example` and `docs/DEPLOY_CHECKLIST.md`).

Important ops flags (names only; set values on the host):

| Key | Purpose |
|-----|---------|
| `FREEZE_MODE_SEND_X_ONLY` | `1` / `0` delivery freeze flag |
| `SMCT_ENV_FILE` | Absolute path to the env file |
| `SMCT_SIGNAL_STATE_FILE` / `SMCT_RUNTIME_STATE_FILE` | State JSON paths |
| `BINANCE_SYMBOL` | Symbol (default `BTCUSDT`) |
| `MARKET_SOURCE` | `binance_futures` (default) or `binance_spot` |
| `SCAN_INTERVAL_SECONDS` / `ALERT_COOLDOWN_SECONDS` | Loop and cooldown |

Notification-channel credentials and webhook secrets stay in the host env file only.

## systemd

Production expects three units (host names may match these examples):

| Unit | Role |
|------|------|
| `smct-scanner` | Scanner loop (`scripts/run_scanner.py`) |
| `smct-alert` | App process (shared `app:app` with webhook on many hosts) |
| `smct-webhook` | Webhook / HTTP surface |

Example unit file in-repo: `systemd/smct-scanner.service` (WorkingDirectory `/opt/smct-alert`, venv interpreter in `ExecStart`).

After install or unit edits:

```bash
sudo systemctl daemon-reload
sudo systemctl restart smct-alert smct-scanner smct-webhook
sudo systemctl is-active smct-alert smct-scanner smct-webhook
```

Prefer `Restart=always`; investigate crash loops via journal before force-restarting.

## Tests

```bash
./scripts/run_ci.sh
# or
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q engine services scripts tests
```

## Upgrade

1. Backup state JSON and note the current commit/tag.
2. Fetch and check out the reviewed commit (do **not** cut over from an unreviewed Draft PR).
3. Sync code into `/opt/smct-alert` without overwriting `.env`, `venv`, `logs`, or `state`.
4. `pip install -r requirements.txt` in the host venv if dependencies changed.
5. Run `./scripts/run_ci.sh` on the host.
6. Restart the three units; confirm they are active.
7. Confirm `FREEZE_MODE_SEND_X_ONLY` (and other delivery flags) still match intent before enabling live send.

A safe sync pattern (no `--delete` against a live `config/` that holds `.env`):

```bash
sudo rsync -a \
  --exclude '.git' --exclude '.env' --exclude 'config/.env' \
  --exclude 'venv' --exclude '.venv' \
  --exclude 'logs' --exclude 'state' \
  --exclude '__pycache__' --exclude '*.pyc' \
  /path/to/reviewed/checkout/ /opt/smct-alert/
```

## Rollback

1. Freeze or stop outbound send if alerts misfire (`FREEZE_MODE_SEND_X_ONLY=1` or stop units).
2. Check out the previous known-good commit/tag and sync into `/opt/smct-alert` the same way.
3. Restore state JSON from the pre-cutover backup if needed.
4. Reinstall requirements if pins changed; restart the three units.
5. Confirm one healthy scan cycle before re-enabling live delivery.

## Docs

| Path | Role |
|------|------|
| `docs/ARCHITECTURE.md` | Neutral runtime overview |
| `docs/DEPLOY_CHECKLIST.md` | Ops cutover checklist |
| `docs/ci-workflow.example.yml` | Example CI workflow |

## License / scope

Public documentation describes operation and hosting only. Strategy semantics, chart-script parameters, and notification copy templates are not published here.
