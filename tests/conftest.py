import numpy as np
import pandas as pd


def make_ohlc(close: np.ndarray, wick: float | None = None) -> pd.DataFrame:
    """Build a simple OHLC frame from a close-price array.

    ``wick`` is the absolute amount added/subtracted from each candle to form
    the high and low.  When *None* (default) a proportional wick of 0.1 % of
    the mean close is used, which keeps the candle ranges realistic relative
    to the price level and step size.
    """
    close = np.asarray(close, dtype=float)
    if wick is None:
        wick = float(np.mean(np.abs(np.diff(close)))) * 0.5 + 1e-8
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - wick
    vol = np.full_like(close, 100.0)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol}
    )
