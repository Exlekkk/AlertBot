# Alert Copy Rules

## Core rule

- Double emoji = formal 1H trade alert.
- Single emoji = non-formal observation or future 15m entry-location reminder.
- 15m remains shadow-only until explicitly enabled.

## 1H formal trade alerts

Use double emoji and full context.

Allowed full-context titles:

- `📈 BTC 1H 试多观察 📈`
- `📉 BTC 1H 试空观察 📉`
- `📈 BTC 1H 多头确认 📈`
- `📉 BTC 1H 空头确认 📉`

Full-context sections:

- status
- zone
- 4H background
- momentum and temperature
- risk level
- conclusion

## 1H secondary confirmation

Still formal, but intentionally minimal.

Allowed titles:

- `✅ BTC 1H 二次确认：承接成立 ✅`
- `✅ BTC 1H 二次确认：承压成立 ✅`

Body format:

- risk level only

Do not include status, zone, momentum, heat, or conclusion in secondary-confirmation copy.

## 1H single-emoji observations

Single-emoji observations are non-formal reminders.

Allowed titles:

- `📍 BTC 1H 关键区观察`
- `📍 BTC 1H 上方关键区观察`
- `📍 BTC 1H 下方关键区观察`

Allowed sections only:

- status
- zone
- risk point

Do not add 4H background, momentum/temperature, or conclusion to single-emoji observations.

## Removed public alert titles

Do not send standalone Telegram alerts for:

- `⚠️ BTC 1H 多头失效`
- `⚠️ BTC 1H 空头失效`

Internal invalidation/risk-state tracking may still exist, but these titles are not part of the public alert copy family.

## 15m prealert

15m is only an entry-location reminder.

Allowed future titles:

- `📍 BTC 15m 做空预警`
- `📍 BTC 15m 做多预警`

15m copy format:

- status
- zone
- risk point, with risk level and handling merged together

Meaning:

- not an official 1H formal trade alert;
- not a direction call by itself;
- just asks the trader to check whether there is a long/short entry location.

15m prealerts remain shadow-only unless explicitly enabled later.
