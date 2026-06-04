# Pocket Option Telegram Signal Bot

A Telegram bot that pushes **directional trading signals (CALL / PUT)** built from
**real Pocket Option market data**. It connects to Pocket Option through the
community/unofficial [`pocketoptionapi-async`](https://github.com/ChipaDevTeam/PocketOptionAPI)
SDK, pulls candles for the assets you watch, runs a transparent **confluence of
technical indicators**, and sends a signal whenever a configurable confidence
threshold is cleared.

> ⚠️ **Read this first — honest disclaimer**
> - No strategy guarantees accuracy. Anyone promising guaranteed win-rates on
>   binary options is misleading you. This bot is an analysis/automation tool,
>   **not financial advice**.
> - Binary/digital options are **high-risk** and are **restricted or banned** in
>   several countries. Check your local laws.
> - The Pocket Option API used here is **unofficial / reverse-engineered**. It can
>   break at any time and may **violate Pocket Option's Terms of Service**, which
>   could get your account limited or banned. Use at your own risk.

## How it works

```
Pocket Option (real candles)            ┌───────────────────────────┐
        │  via unofficial SSID API      │  Confluence strategy      │
        ▼                               │  EMA · MACD · RSI ·       │
  MarketDataClient  ──► candles (df) ──►│  Bollinger · ADX · Stoch  │──► Signal
   (live or demo)                       │  weighted vote + ADX gate │   CALL/PUT
                                        └───────────────────────────┘     │ %conf
                                                                          ▼
                                                          Telegram bot (push + commands)
```

- **Trend gate**: signals are only produced when **ADX > 20** (a real,
  directional market). Choppy/ranging conditions are skipped.
- **Trend-following interpretation**: because we only act in trending markets,
  RSI / Stochastic / Bollinger are read as *momentum confirmation* in the trend
  direction rather than naive overbought/oversold reversal triggers.
- **Confidence** = 70 % weighted indicator agreement + 30 % trend strength (ADX).
- **Demo fallback**: with no SSID configured the bot runs on **synthetic data**
  so you can see the whole pipeline working. Demo signals are clearly labelled
  `[DEMO]` and must not be treated as real market analysis.

## Project layout

```
signalbot/
  config.py              # env-driven configuration
  engine.py              # scan loop: candles -> strategy -> signals (+cooldown)
  pocket/
    client.py            # LivePocketOptionClient (SSID) + DemoMarketClient
    assets.py            # Pocket Option asset universe helpers
  strategy/
    indicators.py        # EMA, RSI, MACD, Bollinger, ATR, ADX, Stochastic
    confluence.py        # weighted-vote confluence strategy
    signals.py           # Signal / IndicatorVote models
  bot/
    telegram_bot.py      # commands + auto-push job
    formatting.py        # message rendering
scripts/backtest.py      # honest walk-forward backtest / win-rate measurement
tests/                   # pytest suite (indicators, strategy, engine)
run.py                   # entry point
```

## Setup

```bash
git clone https://github.com/rowan-cyber/pocket-option-signal-bot.git
cd pocket-option-signal-bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then edit .env
python run.py
```

### 1. Telegram bot token
Create a bot with [@BotFather](https://t.me/botfather), copy the token into
`TELEGRAM_BOT_TOKEN` in `.env`. Start a chat with your bot and send `/start` to
subscribe (or use `/chatid` and put the id in `TELEGRAM_CHAT_IDS`).

### 2. Pocket Option SSID (for live data)
Live data needs your browser session string:
1. Log in to Pocket Option in your browser.
2. Open DevTools (`F12`) → **Network** → filter **WS** (WebSocket).
3. Find the frame that starts with `42["auth",{...}]`.
4. Copy the **whole** thing into `POCKET_OPTION_SSID` in `.env`, e.g.
   `42["auth",{"session":"...","isDemo":1,"uid":123456,"platform":1}]`
5. Set `POCKET_OPTION_DEMO=true` to use the demo balance, `false` for real.

Leave `POCKET_OPTION_SSID` blank to run in **demo (synthetic)** mode.

## Telegram commands

| Command | Description |
|---|---|
| `/start` | Subscribe this chat and show help |
| `/help` | List commands |
| `/status` | Mode (live/demo), auto-push state, settings |
| `/scan` | Run an immediate scan and return current signals |
| `/signals on` / `/signals off` | Toggle auto-push for this chat |
| `/watch <ASSET>` | Add an asset (e.g. `/watch EURUSD_otc`) |
| `/unwatch <ASSET>` | Remove an asset |
| `/assets [otc\|real]` | List available Pocket Option assets |
| `/settings` | Show strategy thresholds |
| `/chatid` | Show this chat's id |

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | – | BotFather token (required) |
| `TELEGRAM_CHAT_IDS` | – | Comma-separated chat ids for auto-push |
| `POCKET_OPTION_SSID` | – | Browser SSID auth string (blank = demo) |
| `POCKET_OPTION_DEMO` | `true` | Use demo balance vs real |
| `ASSETS` | OTC basket | Comma-separated assets to scan |
| `TIMEFRAME` | `60` | Candle seconds (60=M1, 300=M5…) |
| `CANDLE_COUNT` | `120` | Candles fetched per scan |
| `SCAN_INTERVAL` | `60` | Seconds between automatic scans |
| `MIN_CONFIDENCE` | `65` | Min confidence (0-100) to push |
| `SIGNAL_COOLDOWN` | `300` | Anti-spam cooldown per asset+direction |
| `AUTOSTART_SIGNALS` | `true` | Start auto-push on launch |

## Backtesting (measure, don't trust)

```bash
python -m scripts.backtest --asset EURUSD_otc --timeframe 60 --count 1500
```

Walks history forward and reports a simplified next-candle win-rate, broken down
by confidence bucket. It ignores payout, spread and slippage, so treat the number
as a rough relative gauge of the strategy — never a profit projection.

## Tests & lint

```bash
pytest -q
ruff check .
```

## Tuning the strategy

All thresholds and indicator weights live in `StrategyParams`
(`signalbot/strategy/confluence.py`). Raise `MIN_CONFIDENCE` for fewer/stronger
signals, increase `adx_min` to demand stronger trends, or re-weight indicators
(`w_ema`, `w_macd`, …) to favour trend-following vs momentum.

## License

MIT — see `LICENSE`.
