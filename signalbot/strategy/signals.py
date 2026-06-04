"""Signal data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class IndicatorVote:
    """A single indicator's contribution to the decision."""

    name: str
    direction: int  # +1 = CALL/up, -1 = PUT/down, 0 = neutral
    weight: float
    detail: str


@dataclass
class Signal:
    """A directional recommendation for one asset at one point in time."""

    asset: str
    direction: str  # "CALL" or "PUT"
    confidence: float  # 0-100
    timeframe: int  # seconds
    expiry: int  # suggested expiry seconds
    price: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    votes: list[IndicatorVote] = field(default_factory=list)
    live: bool = False

    @property
    def emoji(self) -> str:
        return "🟢⬆" if self.direction == "CALL" else "🔴⬇"

    def reasons(self) -> list[str]:
        """Human-readable reasons from indicators that agree with the call."""
        want = 1 if self.direction == "CALL" else -1
        agree = [v for v in self.votes if v.detail and v.direction == want]
        return [v.detail for v in agree]
