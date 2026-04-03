[Uploading README_alertbot_full.md…]()
# AlertBot

AlertBot 是一个面向 **Binance / BTCUSDT** 的实盘扫描与 Telegram 播报系统，目标不是机械喊单，而是把 **结构、趋势、节奏、异动** 整合成可执行的盘中提醒。

当前项目同时包含两条能力线：

1. **Webhook 接口**：接收外部请求并做基础处理。
2. **Scanner 引擎**：定时拉取行情、计算指标、识别 A / B / C / X，并推送到 Telegram。

---

## 1. 项目定位

AlertBot 的定位不是自动下单，也不是简单量价报警器。

它的职责是：

- 在盘中提供 **提前 / 进行时 / 结构化** 的交易机会提醒
- 区分 **A / B / C** 三类正常节奏信号
- 区分 **X** 类异常驱动信号
- 对重复、冲突、低质量信号做发布层控制
- 将最终结果推送到 Telegram，供人工判断和执行

---

## 2. 当前信号体系

### A 类
趋势里的主力执行信号。

特点：
- 服务于趋势推进
- 要求更干净、更连续
- 可以在同一段趋势中多次出现
- 重点是 **纯度**，不是单纯数量少

### B 类
修复 / 回踩 / 反弹延续信号。

特点：
- 服务于趋势中的修复段
- 用来识别“修复后继续”的位置
- 不是 A 的降级替代品

### C 类
左侧预警信号。

特点：
- 用于提前观察
- 更偏观察与准备
- 不是用来补 A/B 的空缺

### X 类
独立于 ABC 的异常驱动模块。

特点：
- 不处理正常结构节奏
- 处理非正常波动、突发事件、盘口异动、消息催化
- 当前已改为更偏 **多维异动侦测**，而不是单纯量能二极管

---

## 3. 当前原则

### ABC 原则
- A / B / C 三个分类器各自独立完整
- 不允许通过 A↔B↔C 的降级、升级、补位来掩盖识别问题
- 不从别的桶里“舀水”补当前这个桶
- 使用三个独立分类器的质量增强机制

### 发布层原则
- 最终 Telegram 播报不能互相打架
- 同一时间窗内要保持主叙事一致性
- 低热度环境下控制播报密度
- 不把分类器独立，误解为“消息可以群殴式同时发”

### X 原则
- X 独立于 ABC
- X 不是高优先级版 ABC
- X 关注的是“异常事件”，不是普通结构波动

---

## 4. 目录结构

```text
AlertBot/
├─ app.py                         # FastAPI 入口
├─ config.py                      # 环境变量与配置
├─ README.md                      # 项目说明
├─ requirements.txt               # Python 依赖
├─ .env.example                   # 环境变量示例
│
├─ engine/
│  ├─ abnormal.py                 # X 类异常侦测
│  ├─ cooldown.py                 # 去重、状态记忆、发布层控制
│  ├─ indicators.py               # EMA / ATR / 量能 / MACD 等指标计算
│  ├─ market_data.py              # Binance 行情拉取
│  ├─ scanner.py                  # 主扫描流程
│  ├─ signals.py                  # A / B / C 分类器主逻辑
│  └─ structure.py                # BOS / MSS / FVG / Sweep 等结构识别
│
├─ services/
│  ├─ logger.py                   # 日志初始化
│  └─ telegram.py                 # Telegram 文案格式化与发送
│
├─ scripts/
│  ├─ run_bihourly_report.py      # 2h 系统检测报告
│  └─ run_scanner.py              # 扫描器启动入口
│
├─ systemd/
│  └─ smct-scanner.service        # systemd 服务样例
│
└─ tests/
   └─ test_state_and_message.py   # 当前状态与文案测试
```

---

## 5. 运行流程

### 行情流程
1. 拉取 Binance 多周期 K 线
2. 计算指标与结构事件
3. 识别 A / B / C / X 候选
4. 进入发布层做去重、冲突控制、密度控制
5. 生成 Telegram 文案并发送

### 时间框架职责
- **4h**：背景层
- **1h**：主判断层
- **15m**：触发层

这套职责划分是当前执行逻辑的基础，不建议随意打乱。

---

## 6. 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

复制环境变量：

```bash
cp .env.example .env
```

或按你的服务器目录放置：

```bash
cp .env.example /opt/smct-alert/.env
```

---

## 7. 环境变量

最常用的配置包括：

- `TELEGRAM_BOT_TOKEN`：Telegram Bot Token
- `TELEGRAM_CHAT_ID`：目标聊天 / 群组 ID
- `WEBHOOK_SECRET`：Webhook 校验密钥
- `BINANCE_BASE_URL`：Binance API 地址
- `SMCT_SIGNAL_STATE_FILE`：状态文件路径

### X 模块新增
- `X_NEWS_FEED_FILE`：本地消息源 JSON 文件路径
- `X_NEWS_TTL_MINUTES`：消息有效期

示例：

```bash
X_NEWS_FEED_FILE=/opt/smct-alert/config/x_news_feed.json
X_NEWS_TTL_MINUTES=180
```

---

## 8. 启动方式

### 手动启动 scanner

```bash
python scripts/run_scanner.py
```

### 手动启动 FastAPI

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

### systemd 启动 scanner

```bash
sudo cp systemd/smct-scanner.service /etc/systemd/system/smct-scanner.service
sudo systemctl daemon-reload
sudo systemctl enable --now smct-scanner.service
sudo systemctl status smct-scanner.service --no-pager
```

---

## 9. 服务器更新命令

```bash
cd /opt/smct-alert && \
 git fetch origin && \
 git reset --hard origin/main && \
 sudo systemctl restart smct-scanner.service && \
 systemctl status smct-scanner.service --no-pager
```

---

## 10. X 消息源格式

本地 `x_news_feed.json` 示例：

```json
[
  {
    "headline": "US jobs data stronger than expected",
    "direction": "short",
    "driver": "macro",
    "score": 78,
    "symbols": ["BTC", "BTCUSDT"],
    "timestamp": "2026-04-03T14:00:00+08:00",
    "ttl_minutes": 180
  }
]
```

字段说明：
- `headline`：新闻标题
- `direction`：消息偏向，`long / short / mixed`
- `driver`：驱动类型，`macro / policy / exchange / etf / liquidity / other`
- `score`：消息权重
- `symbols`：关联标的
- `timestamp`：发布时间
- `ttl_minutes`：消息存活时间

---

## 11. 当前改造重点

近期主要在做三件事：

### A / B / C
- 保持三分类器独立
- 提高 A 的纯度
- 提高 B 的修复质量
- 提高 C 的预警有效性
- 发布层减少互相打架与乱切叙事

### TAI 冰点区
- 当 15m TAI 进入低热度区时，降低低质量机会密度
- 保持“精准 + 提前 + 进行时”，而不是群发噪音

### X
- 从“量能二极管”改成多维异动侦测
- 增加消息面增强能力
- 输出更像异常事件说明，而不是单一 breakout 标签

---

## 12. 测试

运行测试：

```bash
python -m pytest tests/test_state_and_message.py -q
```

当前测试主要覆盖：
- 去重逻辑
- 文案字段
- 发布层基础行为

后续建议继续补：
- X 消息源解析测试
- 低 TAI 发布密度测试
- 同段主叙事一致性测试

---

## 13. 已知边界

当前项目仍然不是全自动策略执行器，主要边界包括：

- 不自动下单
- 不管理仓位
- 不做收益统计
- systemd 日志默认不一定输出完整 Telegram 播报文本
- X 的新闻能力当前依赖本地消息文件，不是实时在线新闻抓取

---

## 14. 后续方向

- 完善 X 的消息源接入
- 增加 TG 播报本地落盘，便于服务器直接回看历史
- 更完整的阶段状态机
- 更严格的低热度预算控制
- 更清晰的“主叙事进行时”维护

---

## 15. 一句话说明

AlertBot 不是简单报警器。

它的目标是：
**用结构、节奏、热度、异动，把盘中真正值得看的机会整理成可执行的 Telegram 播报。**
