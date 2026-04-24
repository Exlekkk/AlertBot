[README.md](https://github.com/user-attachments/files/27037833/README.md)
[README_alertbot_full_en.md](https://github.com/user-attachments/files/26455856/README_alertbot_full_en.md)
# AlertBot

AlertBot is a Telegram-based market monitoring and signal delivery system built for fast-moving crypto execution, with BTCUSDT as the current primary instrument.

It is designed around a layered workflow instead of a single indicator trigger:

- **A** = primary trend execution signal
- **B** = repair / pullback / rebound-continuation signal
- **C** = early warning / left-side observation signal
- **X** = abnormal-event detection module, independent from A/B/C

The system is intended to stay aligned with a multi-timeframe execution model:

- **4h** = background layer
- **1h** = main judgment layer
- **15m** = trigger layer

## Core Goals

AlertBot is built to do four things well:

1. Detect structured opportunities rather than random noise
2. Send Telegram alerts in a way that is actionable
3. Keep message flow consistent instead of letting signals fight each other
4. Separate normal structure-based opportunities from abnormal event-driven movement

This project is **not** an auto-trading bot.  
It is a monitoring and alerting system. Entry, stop, take profit, and final execution remain manual.

---

## Signal Architecture

## A Signals

A signals are the main execution signals inside a trend segment.

They are meant to represent the **primary directional opportunity** when the market is already in a cleaner continuation state.

A should not be rare by definition.  
A should be **clean**.

What matters is:

- A should represent the main narrative of the trend
- A should not be a fake continuation
- A should not conflict with B/C in the same segment
- A should not be generated from low-quality rebound noise

Examples:

- `A_LONG`
- `A_SHORT`

---

## B Signals

B signals cover repair, pullback, rebound, and continuation-after-repair behavior.

They are not the same as trend continuation.  
They belong to the "working through structure" stage.

What B is supposed to do:

- Track valid pullbacks in a trend
- Track valid rebounds inside a broader directional environment
- Avoid low-quality repair signals that come from weak heat / weak structure

Examples:

- `B_PULLBACK_LONG`
- `B_PULLBACK_SHORT`

---

## C Signals

C signals are early warning signals.

They are used when the market is approaching a potentially important area but has not yet confirmed enough to become B or A.

C should:

- be early
- be selective
- avoid random noise
- avoid repeating too often inside the same anchor

Examples:

- `C_LEFT_LONG`
- `C_LEFT_SHORT`

---

## X Signals

X is fully independent from A/B/C.

It is used for **abnormal event detection**, not for normal structure execution.

X should detect situations such as:

- sudden breakout / breakdown
- abnormal volume spikes
- wick sweep / liquidity grab behavior
- dual-sided sweep and directional resolution
- news-driven or event-driven abnormal movement

X should work more like an **anomaly radar** than a binary switch.

Examples:

- `X_BREAKOUT_LONG`
- `X_BREAKOUT_SHORT`

---

## Design Principles

### 1. A / B / C are independent classifiers

A, B, and C must each improve their own quality logic independently.

The system should **not** hide recognition mistakes by reclassifying one bucket into another.

That means:

- do not "fix A" by downgrading it into B
- do not "fix B" by pushing it into C
- do not "borrow water from another bucket"

The correct approach is:

- improve A as A
- improve B as B
- improve C as C

### 2. Publishing must still stay coherent

Independent classifiers do **not** mean Telegram should publish conflicting messages at the same time.

The publishing layer should keep:

- directional conflict control
- single main narrative per active segment
- cleaner behavior in low-heat environments
- fewer contradictory alerts when 15m heat is near ice-point conditions

### 3. Multi-timeframe role separation remains fixed

The project uses:

- **4h** as background only
- **1h** as the main judgment layer
- **15m** as the trigger layer

Indicators are helpers, not replacements for structure.

---

## Main Components

### `engine/signals.py`
Generates A/B/C candidates.

Responsibilities:
- multi-timeframe interpretation
- structure-based candidate generation
- classifier-specific quality filters
- signal metadata generation

### `engine/cooldown.py`
Controls message repetition and publishing-state memory.

Responsibilities:
- classifier-aware deduplication
- anchor-aware repeat suppression
- publishing conflict control
- state persistence

### `engine/x_signals.py`
Generates X abnormal-event signals.

Responsibilities:
- abnormal movement detection
- price / volume / structure event scoring
- event-type classification

### `engine/abnormal.py`
Backward-compatible wrapper for older imports.

Responsibilities:
- forward old `detect_abnormal_signals(...)` calls to `engine.x_signals.detect_x_signals(...)`

### `engine/scanner.py`
Main scanning orchestration.

Responsibilities:
- fetch market data
- call A/B/C and X detection modules
- pass alerts into the delivery layer

### `services/telegram.py`
Formats and sends Telegram messages.

Responsibilities:
- convert signal objects into Telegram text
- deliver alerts to configured chats

### `tests/test_state_and_message.py`
Basic behavior and formatting tests.

Responsibilities:
- repetition logic checks
- message field checks
- state transition checks for published alerts

---

## Current Working Logic

In simplified form, the bot runs like this:

1. Pull market data
2. Build structure context
3. Generate A/B/C candidates
4. Generate X abnormal-event candidates
5. Resolve publishing conflicts
6. Send final Telegram message(s)
7. Save state

This keeps signal generation separate from publication control.

---

## X News Feed Support

Status: paused.

X currently runs as a price / volume / structure abnormal-event detector.
The optional news feed idea is kept as future documentation only, because no stable free API is currently selected.
Current code does not read the news-feed variables below.

Future design kept from the earlier plan:

Default path:

```bash
/opt/smct-alert/config/x_news_feed.json
```

Optional environment variables:

```bash
X_NEWS_FEED_FILE=/opt/smct-alert/config/x_news_feed.json
X_NEWS_TTL_MINUTES=180
```

Example feed format:

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

The X module does not rely on news alone.  
News is only one dimension inside abnormal-event detection.

---

## Project Structure

```text
AlertBot/
├── engine/
│   ├── abnormal.py
│   ├── cooldown.py
│   ├── indicators.py
│   ├── market_data.py
│   ├── scanner.py
│   ├── signals.py
│   └── structure.py
├── scripts/
├── services/
├── systemd/
├── tests/
│   └── test_state_and_message.py
├── .env.example
├── README.md
├── app.py
├── config.py
└── requirements.txt
```

---

## Environment Variables

Typical variables include:

```bash
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
SMCT_SIGNAL_STATE_FILE=/opt/smct-alert/signal_state.json
X_NEWS_FEED_FILE=/opt/smct-alert/config/x_news_feed.json
X_NEWS_TTL_MINUTES=180
```

Use `.env.example` as a reference.

---

## Deployment

Typical update flow on the server:

```bash
cd /opt/smct-alert && git fetch origin && git reset --hard origin/main && sudo systemctl restart smct-scanner.service && systemctl status smct-scanner.service --no-pager
```

To follow service output:

```bash
journalctl -u smct-scanner.service -f
```

---

## Current Priorities

The current development focus is:

- keep A clean without making it artificially scarce
- improve B/C quality in low-heat conditions
- stop contradictory Telegram publishing
- make X behave like an anomaly detector instead of a binary trigger
- keep A/B/C classifier logic independent

---

## What This Bot Is Not

This bot is not:

- an auto-execution engine
- a guaranteed entry system
- a replacement for discretionary execution
- a one-indicator strategy

It is a structured alerting system for discretionary trading.

---

## Future Direction

Potential next steps include:

- richer publishing-state control for live narrative consistency
- stronger low-heat filtering
- better abnormal-event clustering for X
- improved local event/news ingestion
- historical message storage for easier review and debugging
