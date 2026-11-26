# PR#48 Draft: swap formal liquidity sweep source

## Locks (user nodded via L · Finance)

- 流动性权重与此前完全一致：**2.0**（`sweep_sell_side_reclaim` / `sweep_buy_side_reject`）
- 权重栈不动：RAR / 流动性 / IFVG / POC 仍高于道氏和 Auto Range
- 15m 与 1H 图层独立：
  - **1H** 是活着还是结束的地图（`ended_levels` / `active_levels`）
  - **15m** 只看路径，写入 `path`，不回写 1H 地图
  - 15m 路径信号不能把已结束的 1H 线救活（不得重新进入 `active_levels`，也不得把 1H 的 `swept` / `recent_sweep_valid` 翻成有效）
- ▲/▼ 只作为证据，须同时满足：
  - 同一根扫过至少两层可见流动性带
  - 强度达到引擎阈值
  - 2 根内收回收盘（上沿：收盘跌回回收位以下；下沿：收盘站回回收位以上）
- **不能单独开 formal**：不进入 catalyst alignment，取消 `matching_fresh_event` 特赦
- 扫荡模块自带的目标 / 止损画线不进 AlertBot 报单；进出场位置仍走 OTE / IFVG / POC
- bull-gate、M/W 0.2（15m/1H/4H）、`formal_min` 等现有闸一律不动

## Baseline / rollback

- **Stack base / LIVE tip**: `de46e6d1fb887109a03ade7eb4bb9c5eb1965626`（#47 tip-detach：bull 闸 + M/W 15m/1H/4H 各 0.2）
- **Rollback label**: `8e3dbea`（#35）
- **tip-detach** Draft：不要合入 `main`；在 L + 用户点头前不上机

## Code

- `engine/sweep_hunter.py` — 按周期独立建图；`attach_path_context` 只挂路径
- `engine/scanner.py` — 1H 地图 + 独立 15m 路径后，再 `merge_sweep_into_liquidity`
- `engine/trial_decision.py` — 权重仍 2.0；扫荡标签退出 catalyst alignment / 不再构成 `matching_fresh_event`
- `engine/trend_config.py` — 检测用引擎常量（无画线进出场接线）
- 测试：`tests/test_liquidity_sweep_source.py`（并小幅对齐 `tests/test_evidence_proxies.py`）

## Acceptance

- 权重改前 = 改后 = 2.0
- 单层、强度不足、或 2 根内未收回：不记 evidence
- 已结束 1H 线不会因 15m 路径信号回到 `active_levels`，1H formal 标记不被路径翻盘
- 仅流动性证据时：`directional_catalyst` 为假，且出现 `formal_without_directional_catalyst`
- 扫荡上下文 / 合并结果 / formal 评估载荷均无目标 / 止损画线字段
- `python3 -m unittest discover -s tests -p 'test_*.py' -q` 全绿（183）

## Homepage hygiene

PR title + any future squash subject: **short English only**. Detail stays in this file + `reports/bot_changes.csv`.
