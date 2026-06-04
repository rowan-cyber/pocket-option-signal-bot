"""Confluence strategy.

The idea: no single indicator is reliable, so we combine several classic ones
and only act when a weighted majority agree AND the market is trending enough to
be worth trading. Each indicator casts a vote (+1 CALL / -1 PUT / 0 neutral)
with a weight; confidence is the share of the participating weight that points
the winning way, scaled by trend strength (ADX).

This is a transparent, configurable heuristic -- it does NOT guarantee wins.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import indicators as ind
from .signals import IndicatorVote, Signal


@dataclass
class StrategyParams:
    ema_fast: int = 9
    ema_slow: int = 21
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: float = 2.0
    adx_period: int = 14
    adx_min: float = 20.0  # below this the market is ranging -> filter out
    stoch_k: int = 14
    stoch_d: int = 3
    stoch_smooth: int = 3

    # Vote weights per indicator.
    w_ema: float = 1.5
    w_macd: float = 1.2
    w_rsi: float = 1.0
    w_bollinger: float = 1.0
    w_stoch: float = 0.8


# Enough candles for the slowest indicator (EMA slow + MACD slow + smoothing) to
# warm up. Below this we cannot trust the values.
def min_candles(params: StrategyParams) -> int:
    return max(params.ema_slow, params.macd_slow, params.bb_period, params.adx_period) + 30


class ConfluenceStrategy:
    """Combine indicators into a single directional signal."""

    def __init__(self, params: StrategyParams | None = None):
        self.params = params or StrategyParams()

    def evaluate(
        self,
        df: pd.DataFrame,
        asset: str,
        timeframe: int,
        expiry: int,
        live: bool,
    ) -> Signal | None:
        """Return a Signal for the latest candle, or None if no data/edge.

        ``df`` must have columns: open, high, low, close (volume optional).
        """
        p = self.params
        if df is None or len(df) < min_candles(p):
            return None

        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)

        ema_fast = ind.ema(close, p.ema_fast)
        ema_slow = ind.ema(close, p.ema_slow)
        rsi = ind.rsi(close, p.rsi_period)
        macd = ind.macd(close, p.macd_fast, p.macd_slow, p.macd_signal)
        bb = ind.bollinger_bands(close, p.bb_period, p.bb_std)
        adx = ind.adx(high, low, close, p.adx_period)
        stoch = ind.stochastic(high, low, close, p.stoch_k, p.stoch_d, p.stoch_smooth)

        i = -1  # latest closed candle
        last_close = float(close.iloc[i])
        adx_val = float(adx["adx"].iloc[i])

        # ADX DI lines give the primary trend direction that conditions how
        # oscillators (RSI, Stochastic) are interpreted. In a trending market
        # (ADX > adx_min), overbought/oversold readings reflect *momentum* in
        # the trend direction, NOT reversal signals. This is a standard
        # trend-following principle.
        votes: list[IndicatorVote] = []

        # 1) EMA trend: fast above slow -> uptrend.
        if ema_fast.iloc[i] > ema_slow.iloc[i]:
            votes.append(IndicatorVote("EMA", 1, p.w_ema, "EMA fast above slow (uptrend)"))
        elif ema_fast.iloc[i] < ema_slow.iloc[i]:
            votes.append(IndicatorVote("EMA", -1, p.w_ema, "EMA fast below slow (downtrend)"))
        else:
            votes.append(IndicatorVote("EMA", 0, p.w_ema, ""))

        # 2) MACD histogram: both direction and momentum.
        hist = float(macd["hist"].iloc[i])
        if hist > 0:
            votes.append(IndicatorVote("MACD", 1, p.w_macd, "MACD histogram positive"))
        elif hist < 0:
            votes.append(IndicatorVote("MACD", -1, p.w_macd, "MACD histogram negative"))
        else:
            votes.append(IndicatorVote("MACD", 0, p.w_macd, ""))

        # 3) RSI — trend-following interpretation. Since we only emit when
        #    ADX > min (trending), RSI acts as momentum confirmation:
        #    > 50 = bullish momentum, < 50 = bearish momentum.
        rsi_val = float(rsi.iloc[i])
        if rsi_val > 50:
            w = p.w_rsi if rsi_val > 55 else p.w_rsi * 0.5
            votes.append(IndicatorVote("RSI", 1, w, f"RSI bullish ({rsi_val:.0f})"))
        elif rsi_val < 50:
            w = p.w_rsi if rsi_val < 45 else p.w_rsi * 0.5
            votes.append(IndicatorVote("RSI", -1, w, f"RSI bearish ({rsi_val:.0f})"))
        else:
            votes.append(IndicatorVote("RSI", 0, p.w_rsi, ""))

        # 4) Bollinger %B — trend-following: price above middle band = bullish,
        #    below = bearish. Extreme bands confirm trend strength.
        pct_b = float(bb["pct_b"].iloc[i])
        if pct_b > 0.5:
            w = p.w_bollinger if pct_b > 0.7 else p.w_bollinger * 0.5
            votes.append(IndicatorVote("Bollinger", 1, w, f"Price above BB midline ({pct_b:.2f})"))
        elif pct_b < 0.5:
            w = p.w_bollinger if pct_b < 0.3 else p.w_bollinger * 0.5
            votes.append(IndicatorVote("Bollinger", -1, w, f"Price below BB midline ({pct_b:.2f})"))
        else:
            votes.append(IndicatorVote("Bollinger", 0, p.w_bollinger, ""))

        # 5) Stochastic K vs D — momentum direction.
        k = float(stoch["k"].iloc[i])
        d = float(stoch["d"].iloc[i])
        if k > d:
            votes.append(IndicatorVote("Stochastic", 1, p.w_stoch, "Stochastic K above D (bullish)"))
        elif k < d:
            votes.append(IndicatorVote("Stochastic", -1, p.w_stoch, "Stochastic K below D (bearish)"))
        else:
            votes.append(IndicatorVote("Stochastic", 0, p.w_stoch, ""))

        # --- Aggregate ---
        call_w = sum(v.weight for v in votes if v.direction > 0)
        put_w = sum(v.weight for v in votes if v.direction < 0)
        participating = call_w + put_w
        if participating == 0:
            return None

        if call_w > put_w:
            direction = "CALL"
            winning = call_w
        elif put_w > call_w:
            direction = "PUT"
            winning = put_w
        else:
            return None  # tie -> no edge

        agreement = winning / participating  # 0.5 .. 1.0
        # Trend-strength factor from ADX, capped at 1.0 (ADX 40+ = strong trend).
        trend_factor = min(adx_val / 40.0, 1.0) if adx_val == adx_val else 0.0
        # Confidence blends agreement (primary) with trend strength.
        confidence = 100.0 * (0.7 * agreement + 0.3 * trend_factor)

        # Filter out choppy/ranging markets entirely.
        if adx_val != adx_val or adx_val < p.adx_min:
            return None

        return Signal(
            asset=asset,
            direction=direction,
            confidence=round(confidence, 1),
            timeframe=timeframe,
            expiry=expiry,
            price=last_close,
            votes=votes,
            live=live,
        )
