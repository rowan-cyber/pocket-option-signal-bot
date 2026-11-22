import numpy as np
import pandas as pd

from signalbot.strategy import indicators as ind
from tests.conftest import make_ohlc


def test_ema_matches_pandas_ewm():
    s = pd.Series([1.0, 2, 3, 4, 5, 6, 7, 8])
    expected = s.ewm(span=3, adjust=False).mean()
    pd.testing.assert_series_equal(ind.ema(s, 3), expected)


def test_rsi_bounds_and_uptrend():
    close = pd.Series(np.linspace(1.0, 2.0, 100))
    rsi = ind.rsi(close, 14).dropna()
    assert (rsi >= 0).all() and (rsi <= 100).all()
    # A monotonic uptrend should be strongly overbought.
    assert rsi.iloc[-1] > 70


def test_macd_columns_and_hist():
    close = pd.Series(np.linspace(1.0, 2.0, 100))
    macd = ind.macd(close)
    assert list(macd.columns) == ["macd", "signal", "hist"]
    # Steady uptrend -> MACD line above signal -> positive histogram.
    assert macd["hist"].iloc[-1] > 0


def test_bollinger_pct_b_range():
    close = pd.Series(np.linspace(1.0, 2.0, 100))
    bb = ind.bollinger_bands(close, 20, 2.0)
    assert {"middle", "upper", "lower", "width", "pct_b"} <= set(bb.columns)
    valid = bb.dropna()
    assert (valid["upper"] >= valid["lower"]).all()


def test_adx_high_for_strong_trend_low_for_flat():
    up = make_ohlc(np.linspace(1.0, 2.0, 120))
    flat = make_ohlc(1.0 + 0.0005 * np.sin(np.arange(120)))
    adx_up = ind.adx(up["high"], up["low"], up["close"], 14)["adx"].iloc[-1]
    adx_flat = ind.adx(flat["high"], flat["low"], flat["close"], 14)["adx"].iloc[-1]
    assert adx_up > adx_flat


def test_stochastic_range():
    close = pd.Series(np.linspace(1.0, 2.0, 100))
    df = make_ohlc(close.to_numpy())
    st = ind.stochastic(df["high"], df["low"], df["close"]).dropna()
    assert (st["k"] >= 0).all() and (st["k"] <= 100).all()
