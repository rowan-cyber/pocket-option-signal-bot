"""Market data clients.

``LivePocketOptionClient`` wraps the unofficial ``pocketoptionapi_async`` SDK and
returns *real* Pocket Option candles. ``DemoMarketClient`` generates synthetic
candles so the full pipeline (strategy + Telegram) can be exercised without
credentials. Both expose the same async interface, so the rest of the app does
not care which one is in use.
"""

from __future__ import annotations

import abc
import random
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from ..logger import get_logger

log = get_logger(__name__)

_OHLC_COLS = ["open", "high", "low", "close", "volume"]


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Force a candle DataFrame into a canonical open/high/low/close/volume shape."""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=_OHLC_COLS)
    out = df.copy()
    out.columns = [str(c).lower() for c in out.columns]
    if "volume" not in out.columns:
        out["volume"] = 0.0
    missing = [c for c in ("open", "high", "low", "close") if c not in out.columns]
    if missing:
        raise ValueError(f"candle frame missing columns: {missing}")
    for col in _OHLC_COLS:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out[_OHLC_COLS].dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


class MarketDataClient(abc.ABC):
    """Common async interface for fetching candles."""

    is_live: bool = False

    @abc.abstractmethod
    async def connect(self) -> bool: ...

    @abc.abstractmethod
    async def disconnect(self) -> None: ...

    @abc.abstractmethod
    async def get_candles(self, asset: str, timeframe: int, count: int) -> pd.DataFrame: ...


class LivePocketOptionClient(MarketDataClient):
    """Real Pocket Option data through the unofficial async SDK."""

    is_live = True

    def __init__(self, ssid: str, is_demo: bool = True):
        self._ssid = ssid
        self._is_demo = is_demo
        self._client = None

    async def connect(self) -> bool:
        from pocketoptionapi_async import AsyncPocketOptionClient

        self._client = AsyncPocketOptionClient(
            self._ssid, is_demo=self._is_demo, enable_logging=False
        )
        ok = await self._client.connect()
        if ok:
            log.info("Connected to Pocket Option (demo=%s)", self._is_demo)
        else:
            log.error("Pocket Option connection returned False")
        return bool(ok)

    async def disconnect(self) -> None:
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception as exc:  # pragma: no cover - network teardown
                log.warning("Error during disconnect: %s", exc)

    async def get_candles(self, asset: str, timeframe: int, count: int) -> pd.DataFrame:
        if self._client is None:
            raise RuntimeError("client not connected; call connect() first")
        df = await self._client.get_candles_dataframe(
            asset=asset, timeframe=timeframe, count=count
        )
        return _normalize_df(df)

    async def get_balance(self) -> float | None:
        if self._client is None:
            return None
        try:
            bal = await self._client.get_balance()
            return float(getattr(bal, "balance", bal))
        except Exception as exc:  # pragma: no cover - network
            log.warning("get_balance failed: %s", exc)
            return None


class DemoMarketClient(MarketDataClient):
    """Synthetic candle generator for offline use.

    Maintains a per-asset random-walk price so repeated scans evolve over time
    and produce varied (but deterministic-per-seed) signals. Clearly NOT real
    market data -- every signal it produces is flagged ``live=False``.
    """

    is_live = False

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)
        self._np = np.random.default_rng(seed)
        self._last_price: dict[str, float] = {}

    async def connect(self) -> bool:
        log.warning(
            "No POCKET_OPTION_SSID set -> running in DEMO mode with synthetic data. "
            "Signals are for pipeline testing only, not real market data."
        )
        return True

    async def disconnect(self) -> None:
        return None

    def _base_price(self, asset: str) -> float:
        if asset not in self._last_price:
            if "JPY" in asset:
                self._last_price[asset] = self._rng.uniform(100, 150)
            elif "BTC" in asset:
                self._last_price[asset] = self._rng.uniform(20000, 60000)
            else:
                self._last_price[asset] = self._rng.uniform(0.8, 1.5)
        return self._last_price[asset]

    async def get_candles(self, asset: str, timeframe: int, count: int) -> pd.DataFrame:
        start = self._base_price(asset)
        # Geometric-ish random walk with occasional trend regimes.
        drift = self._np.normal(0, 0.0004)
        vol = abs(self._np.normal(0, 1)) * 0.0012 + 0.0004
        returns = self._np.normal(drift, vol, size=count)
        prices = start * np.cumprod(1 + returns)
        self._last_price[asset] = float(prices[-1])

        now = datetime.now(timezone.utc)
        rows = []
        for j in range(count):
            o = prices[j - 1] if j > 0 else prices[j] * (1 - returns[j])
            c = prices[j]
            wick = abs(self._np.normal(0, vol)) * c
            hi = max(o, c) + wick
            lo = min(o, c) - wick
            ts = now - timedelta(seconds=timeframe * (count - j))
            rows.append((ts, o, hi, lo, c, float(self._rng.randint(50, 500))))

        df = pd.DataFrame(rows, columns=["timestamp", *_OHLC_COLS])
        return _normalize_df(df)


def create_client(ssid: str, is_demo: bool = True) -> MarketDataClient:
    """Return a live client when an SSID is provided, else a demo client."""
    if ssid and ssid.strip():
        return LivePocketOptionClient(ssid.strip(), is_demo=is_demo)
    return DemoMarketClient()
