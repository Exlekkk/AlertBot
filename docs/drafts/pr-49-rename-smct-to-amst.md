# PR#49 Draft: rename SMCT display and host paths to AMST

## Locks (user nodded via L · Finance)

七项已锁口径：

1. `SMCT_*` 键名改 `AMST_*`，双读：先读 `AMST_*`，未设或空串再回退 `SMCT_*`。涉及 `ENV_FILE`、`SIGNAL_STATE_FILE`、`RUNTIME_STATE_FILE`、`REPO_ROOT`、`ABNORMAL_VOLUME_WEAK_ENABLED`。文档预备名 `SMCT_15M_WEAK_*` 改为 `AMST_15M_WEAK_*`，不借机接线。无 SMCT 前缀的键键名不改，只换默认路径前缀。
2. 类名 `SMCTScanner` → `AMSTScanner`，logger `smct_scanner` → `amst_scanner`，健康检查 `AMST Alert Bot is running`，unit Description 中 SMCT → AMST。测试、脚本、`legacy_quarantine/apply_refactor.py` 一并改。
3. 仓名保持 `Exlekkk/AlertBot`；CLONE 目录不改。
4. 以后上机浸泡期：symlink `/opt/smct-alert` → `/opt/amst-alert`。
5. 旧 `smct-*` unit：`disable` + `mask`，先不删文件。
6. 切换窗口只改四个路径键的值，且 `WEBHOOK_LOG_FILE` 两处都改；本窗口不去重、不重组 env 文件。本 PR **不写、不发上机脚本**。
7. 新 scanner 继续带 early drop-in。仓内 `systemd/amst-scanner.service.d/90-alertbot-early-shadow.conf` 同时写 `AMST_EARLY_OBSERVATION_MODE=shadow` 与 `SMCT_EARLY_OBSERVATION_MODE=shadow`。不把 early 源码、测试或 rollout 文档加进公开仓。

不夹策略逻辑，不改权重，不改 formal / bull-gate / M/W，不与 #48 捆刀。

## Baseline / rollback

- **Content tip**: `f76fe9569d7b79d02b255db803de882df5d028e6`
- **Stack base / LIVE tip**: `2c258488727d3af66d1fba8b74ebc0818e7961a1`（#48 tip-detach）
- **Rollback label**: `8e3dbea`（`8e3dbead13eebe32731984bcaa3d77f6fcdb31cf`，#35）
- 更名回滚是搬回目录 + 恢复旧 unit / cron / env 副本，**不是**把 tip 滚到 `8e3dbea`
- **tip-detach** Draft：不要合入 `main`；L + 用户点头前不上机、不改 LIVE

## Code

- `config.py` — `env_amst_then_smct()`；默认安装根 `/opt/amst-alert`；锁文件 `/tmp/amst-tg-ops-poll.lock`
- `engine/scanner.py` / `scripts/run_scanner.py` / `app.py` — 类名、logger、健康检查
- `systemd/amst-*.service` — 三个原模板改名；补齐 `amst-alert` / `amst-webhook`（LIVE unit 蓝本，scanner 含 `PYTHONPATH`）
- `systemd/amst-scanner.service.d/90-alertbot-early-shadow.conf` — 双键兼容
- 测试：`tests/test_amst_env.py`（并更新既有引用）

## Acceptance

- 新键生效，旧键在新键未设或空串时仍生效；新键非空时覆盖旧键
- 公开可见文案不再使用 SMCT 作为现行显示名（剩余 SMCT 仅双读回退、历史说明、drop-in 兼容旧键）
- `python3 -m unittest discover -s tests -p 'test_*.py' -q` 全绿（193）

## Homepage hygiene

PR title + any future squash subject: **short English only**. Detail stays in this file + `reports/bot_changes.csv`.
