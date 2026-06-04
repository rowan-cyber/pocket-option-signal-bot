import numpy as np

from signalbot.strategy.confluence import ConfluenceStrategy, min_candles
from tests.conftest import make_ohlc


def _eval(close):
    df = make_ohlc(close)
    strat = ConfluenceStrategy()
    return strat.evaluate(df, asset="EURUSD_otc", timeframe=60, expiry=60, live=False)


def _zigzag_trend(up: bool, rng, n: int = 160) -> np.ndarray:
    """Build a realistic trending series with pullbacks (zigzag), not monotonic.

    This keeps RSI/Stochastic oscillating rather than pegged at extremes.
    """
    t = np.arange(n, dtype=float)
    slope = 0.0008 if up else -0.0008
    base = (1.10 if up else 1.25) + slope * t
    cycles = 0.005 * np.sin(t * 2 * np.pi / 25)  # 25-bar oscillation
    noise = rng.normal(0, 0.001, n)
    return base + cycles + noise


def test_returns_none_with_insufficient_data():
    strat = ConfluenceStrategy()
    df = make_ohlc(np.linspace(1.0, 1.1, 10))
    assert strat.evaluate(df, asset="X", timeframe=60, expiry=60, live=False) is None


def test_min_candles_positive():
    assert min_candles(ConfluenceStrategy().params) > 30


def test_strong_uptrend_is_call():
    rng = np.random.default_rng(42)
    close = _zigzag_trend(up=True, rng=rng)
    sig = _eval(close)
    assert sig is not None
    assert sig.direction == "CALL"
    assert 0 <= sig.confidence <= 100


def test_strong_downtrend_is_put():
    rng = np.random.default_rng(42)
    close = _zigzag_trend(up=False, rng=rng)
    sig = _eval(close)
    assert sig is not None
    assert sig.direction == "PUT"


def test_uptrend_and_downtrend_disagree():
    close_up = _zigzag_trend(up=True, rng=np.random.default_rng(42))
    close_dn = _zigzag_trend(up=False, rng=np.random.default_rng(42))
    sig_up = _eval(close_up)
    sig_dn = _eval(close_dn)
    if sig_up is not None and sig_dn is not None:
        assert sig_up.direction != sig_dn.direction


def test_flat_choppy_market_filtered_out():
    rng = np.random.default_rng(3)
    close = 1.0 + rng.normal(0, 0.0003, 150)
    sig = _eval(close)
    assert sig is None


def test_signal_has_votes():
    rng = np.random.default_rng(42)
    sig = _eval(_zigzag_trend(up=True, rng=rng))
    assert sig is not None
    assert len(sig.votes) > 0
    assert all(v.name for v in sig.votes)
