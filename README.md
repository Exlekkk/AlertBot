# AlertBot (FastAPI + Telegram + SMCT Scanner)

## 当前能力
- 保留原有 FastAPI `/webhook` 接口（含 secret 校验、日志、冷却去重）。
- 新增独立实时盯盘引擎：每 60 秒扫描 Binance `BTCUSDT` 的 `15m/1h/4h`。
- 命中信号后自动推送 Telegram（不依赖 TradingView 手工告警）。

## 目录
- `app.py`：FastAPI webhook 入口
- `config.py`：环境变量配置
- `services/telegram.py`：消息格式与发送
- `services/logger.py`：日志初始化
- `engine/market_data.py`：Binance K线拉取
- `engine/indicators.py`：EMA/ATR/20均量/MACD
- `engine/structure.py`：pivot/BOS/MSS/FVG简化
- `engine/signals.py`：A/B/C 信号判定（v1近似版）
- `engine/scanner.py`：扫描主循环
- `engine/cooldown.py`：冷却去重
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

## 已实现 / TODO
### 已实现
- Binance 公共行情获取（BTCUSDT，15m/1h/4h）
- EMA10/20/120/169, ATR, 20均量, MACD柱体
- 4h/1h 趋势分类（bull/bear/neutral）
- 15m pivot / BOS / MSS 基础识别
- A_LONG / A_SHORT
- B_PULLBACK_LONG / B_PULLBACK_SHORT（近似）
- C_LEFT_LONG / C_LEFT_SHORT（近似）
- 优先级 `A > B > C`，每轮只推一个
- 冷却去重（symbol + timeframe + signal）

### TODO
- 更完整的 FVG 区间管理与“未回补”状态跟踪
- A/B/C 的更细粒度过滤（压制区/需求区/插针噪声）
- 更严格的 MSS 阶段状态机
- 横盘过滤阈值参数化
