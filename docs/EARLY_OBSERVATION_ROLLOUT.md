# Controlled early-observation rollout

This change is for review first. Do not deploy an unreviewed PR. Baseline:
`8e3dbead13eebe32731984bcaa3d77f6fcdb31cf` (main before this change).

## Behavior and boundaries

- `SMCT_EARLY_OBSERVATION_MODE=off` is the default. `shadow` evaluates the
  same candidate/delivery gates into a separate ledger without early Telegram
  sends. `live` opts in to early delivery. Normal closed alerts keep running
  in all three modes; use the standalone `--shadow` runner for a fully silent scan.
- Existing closed 1H structural zones and 4H background are the only anchors.
  Initially only the two explicit structural zone sources already used by the
  observation engine qualify; generic range edges alone do not open early delivery.
- 15m and 1H each need their own absolute volume floor (strictly greater than
  6000 / 12000 base units) AND a ratio of at least 1.8 against their own previous
  20 completed bars. No extrapolation or borrowing one timeframe's volume/body.
- The source must be the current forming candle with continuous preceding
  volume history and current closed 1H context. Boundary races fail closed.
- Volume adds a bounded timing weight to existing early assessment. Current
  price must react in the matching direction near the closed structural zone.
  Risk, chase, opposite evidence, range edge/reward and minimum-score checks remain.
- Auto Range's accepted flag is annotation only: it cannot waive wrong-edge,
  range reward/risk, middle-box minimum score, or same-box cooldown rules.
  This safety fix applies to the closed path as well, even when early mode is off.
- Existing message types and templates are reused: 15m location reminder and
  1H trial observation. Their existing status/conclusion text explicitly says
  the source is unclosed and awaits close confirmation. No new alert family.
- Raw candles never enter structural builders. Early evidence is labelled
  `forming=true`, `closed_confirmation=false`, with volume `confirmed=false`.
  Forming price reactions receive no closed acceptance/reaction bonus.

## Delivery and state

`SMCT_EARLY_OBSERVATION_STATE_FILE` defaults to
`/opt/smct-alert/state/early_observation.sqlite3`. Shadow uses the same path plus
`.shadow`, so shadow reservations cannot consume live cooldowns.

The early ledger has independent symbol/timeframe/side slots. Same-side
cooldown is four source bars; opposite-side cooldown is two source bars.
Changing zone bounds cannot bypass them. Simultaneous overlapping-area sends
(including contradictory sides) coalesce for 15 minutes; 1H is evaluated first.
This delivery coalescing does not copy 15m candle IDs into 1H state.

SQLite transactions serialize reservations across scanner instances. A
reservation is committed before Telegram IO. An uncertain outcome keeps the
reservation, so a timeout/restart does not repeatedly send the same event.
The tradeoff is possibly missing an early notification; this is not an
exactly-once delivery guarantee. Do not delete the ledger to retry blindly.

Early sends do not write formal signal slots, observation pending state, trend
snapshots or secondary-confirmation state. 1H reads closed observation cooldown
context; 15m does not. A delivered 1H early observation suppresses the matching
same-area first closed-candle copy. Later closed structures continue through
normal formal rules. Closed eligible alerts take precedence over early delivery.
Optional early-data/ledger errors are logged and do not stop closed scans.

The previous standalone volume-weak and 15m shadow scripts are unchanged and
remain log-only. Their old flags do not enable this new integration. The legacy
freeze flag does not gate the scanner's existing trial send path; use the new
explicit mode switch to disable early sends. No server flags are changed by this PR.

## Validation

- Local original baseline: 140 tests, 139 passed; Linux `fcntl` test cannot run
  on Windows. Temporary-directory permissions were corrected for the test run.
- Added deterministic regressions for forming evidence, both source periods and
  sides, timing/floors, input immutability, safety gates, persistent dedupe,
  first-close coalescing, uncertain sends and full-scanner silent Shadow.
- Linux CI runs the complete suite, including the existing `fcntl` test.
- Public-market standalone Shadow smoke: successful scan, no Telegram, both
  sources rejected because volume was below threshold. A snapshot cannot
  establish false-positive rate, lead-time improvement or trading performance.
- Before live enablement, run sustained server Shadow across representative
  market conditions and inspect eligibility, suppress reasons, candle times,
  and repeat/flip behavior. Do not infer performance from synthetic fixtures.

## Safe server preparation and pull (after PR review/merge)

The following assumes the actual Git checkout and systemd scanner use
`/opt/smct-alert` and `venv/bin/python`, with the three existing scanner/app/webhook units
listed in the README. Confirm these names/paths against the host before running.
If the server uses a separate source checkout plus rsync, follow the existing
README sync procedure instead. No credentials need to be displayed or copied.

Use the full approved **main merge commit SHA**, not the PR branch head after a
squash merge. The explicit SHA check prevents accidentally deploying later main
commits that have not been reviewed. Run in Bash:

```bash
set -euo pipefail
cd /opt/smct-alert
APPROVED_MAIN_SHA='REPLACE_WITH_REVIEWED_MERGE_COMMIT_SHA'
[[ "$APPROVED_MAIN_SHA" =~ ^[0-9a-f]{40}$ ]]
test "$(git branch --show-current)" = main
test -z "$(git status --porcelain)"
git fetch origin main
test "$(git rev-parse origin/main)" = "$APPROVED_MAIN_SHA"
git merge-base --is-ancestor HEAD "$APPROVED_MAIN_SHA"

# Validate the exact reviewed source in an isolated checkout before cutover.
STAGE=$(mktemp -d /tmp/alertbot-review.XXXXXX)
git worktree add --detach "$STAGE/source" "$APPROVED_MAIN_SHA"
(cd "$STAGE/source" && /opt/smct-alert/venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v)
(cd "$STAGE/source" && /opt/smct-alert/venv/bin/python -m compileall -q engine services scripts tests)
# Standalone shadow reads no production state and cannot send Telegram.
(cd "$STAGE/source" && \
  SMCT_SIGNAL_STATE_FILE="$STAGE/signal.json" \
  SMCT_RUNTIME_STATE_FILE="$STAGE/runtime.json" \
  TREND_SNAPSHOT_STATE_FILE="$STAGE/trend.json" \
  SMCT_EARLY_OBSERVATION_STATE_FILE="$STAGE/early.sqlite3" \
  WEBHOOK_LOG_FILE="$STAGE/shadow.log" \
  /opt/smct-alert/venv/bin/python scripts/run_early_observation_shadow.py --shadow --once)

# Record the running source and make a coherent state backup while stopped.
OLD_HEAD=$(git rev-parse HEAD)
BACKUP="/opt/smct-alert-backups/$(date -u +%Y%m%dT%H%M%SZ)"
sudo install -d -m 700 "$BACKUP"
printf '%s\n' "$OLD_HEAD" | sudo tee "$BACKUP/previous-head" >/dev/null
sudo systemctl stop smct-scanner smct-alert smct-webhook
# State files must be under this directory; include any externally configured
# state locations in the backup according to the server's existing setup.
if test -d state; then sudo cp -a state "$BACKUP/state"; fi
# Restrict to an exact fast-forward. On any failure keep the scanner stopped.
git pull --ff-only origin main
test "$(git rev-parse HEAD)" = "$APPROVED_MAIN_SHA"
sudo systemctl restart smct-scanner smct-alert smct-webhook
sudo systemctl is-active smct-scanner smct-alert smct-webhook
sudo journalctl -u smct-scanner -n 50 --no-pager
# After inspection, this removes only the temporary Git worktree.
git worktree remove "$STAGE/source"
```

Default mode stays off. For sustained silent comparison use the standalone
runner above without `--once`, with a distinct shadow ledger/log location.
`SMCT_EARLY_OBSERVATION_MODE=shadow` on the resident scanner leaves existing
closed notifications active. After reviewing observations, set `live` only via
the server's existing service environment management and restart the scanner.
The one-shot runner always forces silent Shadow, even if the environment says live.

## Disable / rollback

To disable early delivery, set `SMCT_EARLY_OBSERVATION_MODE=off` through existing
service environment management and restart `smct-scanner`. Keep the ledger so
subsequent enablement does not replay recent notifications.

For source rollback, use the recorded `previous-head` from the backup. Avoid a
hard reset or deleting server files:

```bash
set -euo pipefail
cd /opt/smct-alert
BACKUP='/opt/smct-alert-backups/REPLACE_WITH_SELECTED_BACKUP'
OLD_HEAD=$(sudo cat "$BACKUP/previous-head")
[[ "$OLD_HEAD" =~ ^[0-9a-f]{40}$ ]]
test -z "$(git status --porcelain)"
sudo systemctl stop smct-scanner smct-alert smct-webhook
git switch --detach "$OLD_HEAD"
sudo systemctl restart smct-scanner smct-alert smct-webhook
sudo systemctl is-active smct-scanner smct-alert smct-webhook
```

No new formal state schema is introduced. Preserve the current formal state by
default to avoid replaying already-delivered closed alerts. Restore a saved
state only after checking the incident; stop its writers first. The early ledger
is additive and ignored by the previous source. Never copy or print `.env` or
server keys as part of this workflow.
