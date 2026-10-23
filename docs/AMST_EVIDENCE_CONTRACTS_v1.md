# AlertBot AMST 证据源 Context 契约 v1

**日期**：2026-10-24（Asia/Shanghai）  
**作者**：L（业务口径）  
**执行**：P（代码 / PR）  
**仓库**：Exlekkk/AlertBot  
**用户点头**：是（群聊「写吧」）

---

## 0. 总原则（冻壳）

1. **时间层级不变**：4H 方向 → 1H 正式告警 → 15m 仅影子入场位。
2. **15m 永不改 1H**：不改方向、标题、结论、冷却、Telegram 文案、pending/二次确认状态。
3. **文案家族冻住**：双 emoji 正式试单/确认；单 emoji 观察；二次确认极简；不发独立失效告警。
4. **试单四层冻住**：市场阶段 → 结构/位置 → 加权证据 → 追价/风控/同箱反翻面。
5. **Selection edge > Activity edge**：宁可少报，不机械追突破。
6. **Tier 规则**：结构（Tier1）不被辅助滤镜推翻；滤镜不能单独触发正式告警。
7. **实现方式**：K 线近似翻译 Pine 决策语义；**禁止**把受许可 Pine 整文件塞进公开仓；凡近似须在字段/日志标明 `approx` / `candle_proxy`。
8. **交付**：GitHub PR + 上机覆盖清单（路径/片段，方便用户复制粘贴到阿里云）；不代登生产、不碰 `.env`。

---

## 1. 模块映射

| 角色 | 旧模块 | 新语义 |
|------|--------|--------|
| Range / Balance→Expansion | `range_lock.py` | Auto Range Detector |
| Liquidity sweep | `liquidity.py` + `ict_ob._ict_liquidity` | Liquidity Sweep Hunter |
| Volume / POC | `volume_profile.py` + chart FVG VP / HV Pivot | LuxAlgo 3D Delta Profile + POC |
| Imbalance / IFVG | `ict_ob.py` + `msb_ob.py` | Inversion FVG [ChartPrime] |
| OTE（保留） | `chart_indicators` OTE | 参数对齐，不定方向 |
| 滤镜 | `aux_filters` | RAR 保留；拆掉 Inertial；+ RSI Heatmap(1H+)；TAI 仅 15m |
| 壳 | `scanner` / `framework` / `trend_segments` / `key_zones` / `trial_decision` / `prealert_15m` / `trend_messages` | 只适配新 context 形状，不重写交易哲学 |

**删除/剥离（活路径）**：Dual Log、Dow/cycle（经 framework/trial/trend_matrix）、Inertial。  
**删除（死路径）**：`signals.py` / `x_signals.py` / `structure.py` / `abnormal.py` / ABCX telegram 格式。  
**危险残留**：`apply_refactor.py` — PR 内删除，勿当入口。

---

## 2. Auto Range Context 契约

**源**：Auto Range Detector [QuantAlgo]  
**参数（用户截图，非 Pine 默认）**：
- Scan Scaling = `Base + 2x + 3x`
- Base Scan Length = 20
- Boundary Basis = Percentile band 90
- Signal Timing = **Bar close**
- ATR Length = 200
- Compression Percentile = 40；Calibration Lookback = 500
- Min Rotation Rate = 0.18
- Touch = Wick reaches；Min Boundary Touches = **3**（默认 2）
- Touch Tolerance ATR = 0.1；Max Drift = 0.45；Min Containment = 0.7
- Anchoring = Extend to containment；Anchor Lookback = 300；Min Range Bars = 10
- Absorb Overshoot = on；Overshoot Tol ATR = 0.25
- Break Confirm = Close beyond；Breakout Buffer ATR = **0.25**（默认 0.15）
- Merge Deviations = on；Deviation Window = 6；Cooldown Bars = 5；Max Range Age = 0

**输出字段（建议）**：
```
auto_range: {
  state: "none" | "provisional" | "live" | "broken",
  high, low, mid, q25, q75,
  bars_held,
  height_pct,
  last_event: null | "breakout_up" | "breakout_down" | "deviation_up" | "deviation_down",
  event_bar_ts,
  approx: true
}
```

**业务语义**：
- **不是方向信号**；回答：是否 Balance，以及是否 Balance→Expansion。
- **Breakout** = 离开已确认 Range（Close beyond + buffer）；**不可单独追单**；须再叠 Liquidity / POC / RAR / 结构。
- **Deviation** = **Failed Value Migration / Failed Acceptance**  
  - 下破失败收回 = bullish deviation（lower prices rejected）  
  - 上破失败跌回 = bearish deviation（higher prices rejected）  
  - **不是机械反向信号**。
- 同箱噪音抑制可复用旧 range_lock 意图，但检测逻辑换 Auto Range。
- 正式试单：Range 内边缘试单仍允许（加权证据不对称时）；同箱反翻面仍要新结构信息。

---

## 3. Liquidity Sweep Hunter 契约

**源**：Liquidity Sweep Hunter [BigBeluga]  
**参数**：Length=**10**，Filter=**1**，sweep on，Max Line Width=4，Min/Max Transparency=0/60，Calculated bars=**700**  
（Pine 默认 5/0.5，以用户为准）

**输出字段（建议）**：
```
sweep: {
  side: "buy_side" | "sell_side" | null,  // 被扫的流动性侧
  level,
  swept: bool,
  reclaim_or_reject: "reclaim" | "reject" | "pending" | null,
  strength,  // 可用 volume filter 强度代理
  approx: true
}
```

**业务语义**：
- 只说明「哪里被扫 / 可能去拿流动性」，**不单独入场**。
- 与 Auto Range Deviation、IFVG reclaim 可联合加权。
- 替换旧 `liquidity.py` / ICT liquidity 代理；决策语言可保留 sweep/reclaim/reject。

---

## 4. 3D Delta Profile + POC 契约

**源**：LuxAlgo 3D Delta Profile  
**参数**：Length=200，Buckets=35，Value Area%=70，Alignment=Center，Placement=Right of Price，Width=0.5，DepthX=0.08，DepthY=0.5，Bounding box on，**Highlight High Volume Candles = OFF**，Anomaly Threshold=2.5

**输出字段（建议）**：
```
delta_profile: {
  poc,
  vah, val,
  value_area_pos: "above" | "inside" | "below",
  node_bias: "bull" | "bear" | "neutral",  // 桶内 +/- delta 代理
  label: "candle_delta_proxy",  // 禁止写成真实 footprint/order-book
  approx: true
}
```

**业务语义**：
- 回答：真实成交价值中心 / 接受区；与 Liquidity、IFVG、OTE 分工不同。
- **必须**标明 K 线近似，非真实 footprint / trade-delta feed。
- 正式试多/试空须看 value acceptance；LVN/薄区追逐降权。
- 替换旧 fixed-range VP / FVG VP / HV Pivot 决策路径。

---

## 5. Inversion FVG 契约

**源**：Inversion FVG [ChartPrime]  
**参数**：
- Display Mode = Both
- Min Candle Size %：**1H = 0.2**；**15m = 0.15**
- Max Zone Longevity = 500
- Calculated bars = 2000
- Show Only Inversion Zones = false

**输出字段（建议）**：
```
ifvg: {
  zones: [{ top, bottom, direction: 1|-1, inverted: bool, mitigated: bool, start_bar }],
  nearest_active,
  approx: true
}
```

**业务语义**：
- 失衡 / 反应区；**倒置后**才升权；不单独定方向、不单独触发。
- 替换整栈 `ict_ob` + `msb_ob`（含旧 OB/MSB 决策路径）；不要并行保留两套。

---

## 6. OTE（保留，参数对齐）

**源**：Smart Money Fibonacci OTE Engine [ChartPrime]  
**参数**：Pivot=10，OTE Upper=0.786，OTE Lower=0.618  

**语义**：仅 **entry-location**；结构方向已定后优化入场；**不定方向、不单独触发**。

---

## 7. 辅助滤镜

| 工具 | 周期 | 参数 | 权限 |
|------|------|------|------|
| RAR [LuxAlgo] | 1H 正式 + 可用 15m 影子 | Length=15，Power=1，Source=close | **高优先级滤镜**；力度/regime；不可单独告警 |
| RSI Core Levels Heatmap | **仅 1H+** | Max Active=5，RSI=14，Signal=14，midline squeeze on，dashboard off | 低于 RAR；50 reclaim/loss、背离、二次确认；不可单独告警 |
| TAI [Zeiierman] | **仅 15m** | Formation=**30**，History=**350**（非默认 20/252） | participation；不可单独告警；不进 1H 决策 |

**删除**：Inertial Stochastic（从 `aux_filters` 拆掉）。

---

## 8. 正式试单 / 二次确认（不变意图）

正式试单仍需：新鲜方向信息 + 有效箱体位置 + 可接受追价/风险 + 足够方向优势。  
二次确认：父告警后真实推进 + 全上下文重验；不可机械确认。  
同箱反翻面：要新结构信息。  
Pending 仅在 Telegram **成功送达**后写入。

---

## 9. 建议 PR 顺序

1. 冻壳 + 合并本契约文件（如 `docs/AMST_EVIDENCE_CONTRACTS_v1.md`）
2. 落地 4 个新 context builder（字段按上表）
3. 适配 `framework` / `trend_segments` / `key_zones` / `trial_decision` 读新字段
4. 剥 Dual Log / Dow / Inertial / 死路径；删 `apply_refactor.py`
5. 单测 + 既有 replay 窗口回归；最小 CI
6. 输出「上机覆盖清单」给用户复制

**分支建议**：`refactor/amst-evidence`（从 `main`）

---

## 10. 验收口径（业务）

- 1H 正式告警在 Auto Range live 箱内不因上下沿反复触碰而刷屏。
- Breakout/Deviation 事件可出现在决策证据里，但单独 Breakout **不会**直接出试单。
- 文案与 15m 影子隔离回归通过。
- 日志/字段可见 `approx` / `candle_delta_proxy` 标签。
- BTC 决策路径无 Dual Log / Dow / Inertial / 旧 VP / ICT+MSB 栈。

