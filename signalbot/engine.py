"""Scanning engine: pull candles, run the strategy, emit signals.

Holds the cooldown state so the same asset+direction is not re-pushed too often.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .config import Config
from .logger import get_logger
from .pocket.client import MarketDataClient
from .strategy.confluence import ConfluenceStrategy
from .strategy.signals import Signal

log = get_logger(__name__)


class SignalEngine:
    def __init__(
        self,
        config: Config,
        client: MarketDataClient,
        strategy: ConfluenceStrategy | None = None,
    ):
        self.config = config
        self.client = client
        self.strategy = strategy or ConfluenceStrategy()
        # (asset, direction) -> last emit time
        self._last_emit: dict[tuple[str, str], datetime] = {}

    async def connect(self) -> bool:
        return await self.client.connect()

    async def disconnect(self) -> None:
        await self.client.disconnect()

    @property
    def is_live(self) -> bool:
        return self.client.is_live

    async def scan_asset(self, asset: str) -> Signal | None:
        """Evaluate one asset. Returns a Signal or None (no data / no edge)."""
        try:
            df = await self.client.get_candles(
                asset, self.config.timeframe, self.config.candle_count
            )
        except Exception as exc:
            log.warning("Failed to fetch candles for %s: %s", asset, exc)
            return None
        return self.strategy.evaluate(
            df,
            asset=asset,
            timeframe=self.config.timeframe,
            expiry=self.config.recommended_expiry(),
            live=self.is_live,
        )

    def _on_cooldown(self, sig: Signal, now: datetime) -> bool:
        key = (sig.asset, sig.direction)
        last = self._last_emit.get(key)
        if last is None:
            return False
        return (now - last).total_seconds() < self.config.signal_cooldown

    async def scan(
        self,
        assets: list[str] | None = None,
        min_confidence: float | None = None,
        apply_cooldown: bool = True,
    ) -> list[Signal]:
        """Scan a basket and return qualifying signals, best first."""
        assets = assets if assets is not None else self.config.assets
        threshold = self.config.min_confidence if min_confidence is None else min_confidence
        now = datetime.now(timezone.utc)
        results: list[Signal] = []

        for asset in assets:
            sig = await self.scan_asset(asset)
            if sig is None or sig.confidence < threshold:
                continue
            if apply_cooldown and self._on_cooldown(sig, now):
                continue
            results.append(sig)

        if apply_cooldown:
            for sig in results:
                self._last_emit[(sig.asset, sig.direction)] = now

        results.sort(key=lambda s: s.confidence, reverse=True)
        return results
