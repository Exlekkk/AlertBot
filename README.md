
# AlertBot (FastAPI + Telegram + SMCT Scanner)

## 当前能力
- 保留 FastAPI `/webhook` 接口（含 secret 校验、日志、冷却去重）。
- 独立实时盯盘引擎：每 60 秒扫描 Binance `BTCUSDT` 的 `15m/1h/4h/1d`。
- 命中信号后自动推送 Telegram。
- `ABC` 负责正常结构节奏；`X` 负责非正常异动事件。

## 目录
- `app.py`：FastAPI webhook 入口
- `config.py`：环境变量配置
- `services/telegram.py`：消息格式与发送
- `services/logger.py`：日志初始化
- `engine/market_data.py`：Binance K线拉取
- `engine/indicators.py`：EMA/ATR/20均量/MACD
- `engine/structure.py`：pivot/BOS/MSS/FVG 简化
- `engine/signals.py`：A/B/C 正常结构信号
- `engine/abnormal.py`：X 异动侦测（价格 + 量能 + 结构 + 消息）
- `engine/scanner.py`：扫描主循环
- `engine/cooldown.py`：状态去重 / 发布层冲突控制
- `scripts/run_scanner.py`：扫描器启动入口
- `systemd/smct-scanner.service`：扫描器服务单元示例

## 安装
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example /opt/smct-alert/config/.env
```

## 运行
### webhook
```bash
uvicorn app:app --host 0.0.0.0 --port 80
```

### scanner（手动）
```bash
python scripts/run_scanner.py
```

## systemd（推荐独立服务）
```bash
sudo cp systemd/smct-scanner.service /etc/systemd/system/smct-scanner.service
sudo systemctl daemon-reload
sudo systemctl enable --now smct-scanner.service
sudo systemctl status smct-scanner.service --no-pager
```

## X 异动模块说明
### 定位
- `X` 独立于 `ABC`，不负责普通回踩 / 反弹 / 提前预警。
- `X` 只处理**非正常异动**：放量起爆/起跌、插针扫流动性、双边扫后选边、消息驱动异常。

### 判定方式
`X` 不再使用“绝对量能门槛二极管”。当前改为四维评分：
- `price score`：价格/波幅是否异常
- `volume score`：15m/1h 相对量能是否异常
- `structure score`：是否出现起爆/起跌、插针、双边扫流动性
- `news score`：是否有本地 news feed 的热点消息催化

### 本地消息面增强
可选创建：`/opt/smct-alert/config/x_news_feed.json`

示例：
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
- `direction`: `long` / `short` / `mixed`
- `driver`: `macro` / `policy` / `etf` / `exchange` / `news` 等
- `score`: 10~100，表示消息强度
- `symbols`: 允许填写 `BTC`、`BTCUSDT` 等
- `timestamp`: ISO 时间或 Unix 时间戳（秒/毫秒均可）
- `ttl_minutes`: 这条消息在 X 模块里的有效分钟数

环境变量：
- `X_NEWS_FEED_FILE`：自定义 news feed 路径
- `X_NEWS_TTL_MINUTES`：未提供 `ttl_minutes` 时的默认时效，默认 `180`

## 已实现
- Binance 公共行情获取（BTCUSDT，15m/1h/4h/1d）
- EMA10/20/120/169, ATR, 20均量, MACD 柱体
- 4h/1h 趋势分类（bull/bear/neutral）
- 15m pivot / BOS / MSS 基础识别
- A/B/C 正常结构信号
- X 异动模块：价格 + 量能 + 结构 + 消息 四维评分
- 状态去重与发布层冲突控制

## TODO
- 将本地 news feed 扩展为自动抓取新闻源/日历源
- 给 X 增加更细的事件类型标签（short squeeze / long squeeze / eventless spike）
- 给 Telegram 增加 X 的 driver / confidence 单独展示字段
- 增加 X 的专项单测
