# 上机覆盖清单（雏形）— AMST 证据源重构

> 用户在阿里云自行 `git pull` / 复制文件后重启。本清单随 PR 迭代补全。  
> **不要**把 `.env` / Telegram token 提交进仓。

## 本刀涉及文件

| 路径 | 动作 |
|------|------|
| `docs/AMST_EVIDENCE_CONTRACTS_v1.md` | 新增（L 契约） |
| `docs/DEPLOY_CHECKLIST_AMST_EVIDENCE.md` | 新增（本清单） |
| `engine/auto_range.py` | 新增（Auto Range K 线近似） |
| `engine/sweep_hunter.py` | 新增（stub） |
| `engine/delta_profile.py` | 新增（stub，`candle_delta_proxy`） |
| `engine/ifvg.py` | 新增（stub） |
| `engine/range_lock.py` | 改：委托 Auto Range，保留旧字段 |
| `engine/trend_config.py` | 改：写入用户截图参数 |
| `engine/scanner.py` | 改：挂 evidence 包（不改告警哲学） |
| `tests/test_auto_range.py` | 新增 |
| `apply_refactor.py` | **移出主路径** → `legacy_quarantine/apply_refactor.py.DISABLED` |

## 建议重启

```bash
# 按你现有 systemd 名称调整
sudo systemctl restart smct-scanner
# 若还有 alert/webhook 服务：
# sudo systemctl restart smct-alert smct-webhook
sudo systemctl status smct-scanner --no-pager
```

## 验收观察

- 日志/decision 中可见 `evidence.auto_range.approx == true`
- `delta_profile.label == candle_delta_proxy`
- 同箱内不因上下沿触碰刷屏；单独 Breakout **不应**直接出试单
- 15m 影子仍不改 1H 文案/冷却

## 未完成（后续刀）

- Sweep / 3D Delta / IFVG 算法落地
- 剥 Dual Log / Dow / Inertial / 死路径
- Heatmap(1H 滤镜) / TAI(15m) 挂接
- OTE 参数对齐核对
- 最小 CI + replay 回归
