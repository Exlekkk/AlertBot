# PR #42 — 15m supply reject + small M-top → formal short trial

- **Merged tip:** `b343966` (was homepage last-commit with Chinese subject)
- **Rollback tip:** `fefc93f2c2df62a5fb8c55951f7beb0b304b529b`
- **Status:** merged 2026-10-29

## Business lock (CN)

1. 反例 Asia/Shanghai 2026-10-29 ~04:00 BTCUSDT.P 触~81759 后下杀，15m 典型小 M 顶应优先试空；现行 `fefc93f` 因 1H nearest-IFVG 未触（实为 wick 触上沿但 nearest-to-close 抢走下沿）+ RAR 空向扣分 → 正式试空 0。
2. 多 IFVG 时优先上沿拒收语义；15m 上方 IFVG/供给带拒收 + 小 M 顶进入正式空向。
3. RAR 仍走 score/互通（有 15m M 顶时可 cap adverse），禁止 `rar_regime_blocks_*` 硬闸。
4. AR 仍低权；#40 触达闸 / 禁 orphan range、#41 反例回归保持。

## Implementation touchpoints

- `key_zones`: enumerate all active inverted IFVG; upper `rejected_below` beats lower inside
- `structure`: `detect_small_m_top` + `build_structure_15m_context`
- `trial_decision`: wick-touch IFVG lean; `m15_supply_reject_m_top` high-weight catalyst
- `scanner`: closed 15m → `evidence.structure_15m`
