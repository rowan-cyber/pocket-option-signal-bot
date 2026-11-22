"""Simple walk-forward backtest for the confluence strategy.

This is an *honest measuring tool*, not a profit promise. It replays historical
candles, asks the strategy for a signal at each step, then checks whether the
NEXT candle closed in the predicted direction (a simplified binary-option
outcome that ignores payout, spread and execution timing).

Usage:
    python -m scripts.backtest --asset EURUSD_otc --timeframe 60 --count 1000

With POCKET_OPTION_SSID set it backtests on real Pocket Option candles;
otherwise it uses synthetic demo data.
"""

from __future__ import annotations

import argparse
import asyncio

from signalbot.config import Config
from signalbot.logger import setup_logging
from signalbot.pocket.client import create_client
from signalbot.strategy.confluence import ConfluenceStrategy, min_candles


async def run(asset: str, timeframe: int, count: int, min_conf: float) -> None:
    config = Config()
    setup_logging(config.log_level)
    client = create_client(config.pocket_ssid, is_demo=config.is_demo)
    await client.connect()
    df = await client.get_candles(asset, timeframe, count)
    await client.disconnect()

    strat = ConfluenceStrategy()
    warmup = min_candles(strat.params)
    if len(df) <= warmup + 2:
        print(f"Not enough candles ({len(df)}) to backtest; need > {warmup + 2}.")
        return

    wins = losses = ties = trades = 0
    by_conf: dict[str, list[int]] = {"65-75": [], "75-85": [], "85+": []}

    for i in range(warmup, len(df) - 1):
        window = df.iloc[: i + 1]
        sig = strat.evaluate(window, asset, timeframe, timeframe, client.is_live)
        if sig is None or sig.confidence < min_conf:
            continue
        trades += 1
        entry = float(df["close"].iloc[i])
        nxt = float(df["close"].iloc[i + 1])
        won = (sig.direction == "CALL" and nxt > entry) or (
            sig.direction == "PUT" and nxt < entry
        )
        bucket = "85+" if sig.confidence >= 85 else "75-85" if sig.confidence >= 75 else "65-75"
        if nxt == entry:
            ties += 1
        elif won:
            wins += 1
            by_conf[bucket].append(1)
        else:
            losses += 1
            by_conf[bucket].append(0)

    decided = wins + losses
    mode = "LIVE" if client.is_live else "DEMO (synthetic)"
    print(f"\nBacktest {asset} | {mode} | tf={timeframe}s | candles={len(df)}")
    print(f"Signals: {trades} | Wins: {wins} | Losses: {losses} | Ties: {ties}")
    if decided:
        print(f"Win rate (excl. ties): {100 * wins / decided:.1f}%")
    for bucket, outcomes in by_conf.items():
        if outcomes:
            wr = 100 * sum(outcomes) / len(outcomes)
            print(f"  conf {bucket}%: {len(outcomes)} trades, {wr:.1f}% win rate")
    print(
        "\nNOTE: simplified next-candle outcome; ignores payout/spread/slippage. "
        "Past performance does not predict future results."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the confluence strategy.")
    parser.add_argument("--asset", default="EURUSD_otc")
    parser.add_argument("--timeframe", type=int, default=60)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--min-confidence", type=float, default=65.0)
    args = parser.parse_args()
    asyncio.run(run(args.asset, args.timeframe, args.count, args.min_confidence))


if __name__ == "__main__":
    main()
