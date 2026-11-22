"""Runtime configuration loaded from environment variables.

All trading parameters are configurable so the strategy can be tuned without
touching code. Nothing here promises profitability -- these are just knobs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Default basket of assets to scan. OTC pairs trade 24/7 which is convenient for
# demos and weekends; real pairs only return data during market hours.
DEFAULT_ASSETS = [
    "EURUSD_otc",
    "GBPUSD_otc",
    "USDJPY_otc",
    "AUDUSD_otc",
    "EURJPY_otc",
    "USDCAD_otc",
]


@dataclass
class Config:
    """Top level configuration object."""

    # --- Telegram ---
    telegram_bot_token: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
    )
    # Comma separated chat ids that auto-receive pushed signals.
    chat_ids: list[str] = field(
        default_factory=lambda: _split(os.getenv("TELEGRAM_CHAT_IDS", ""))
    )

    # --- Pocket Option ---
    # Full SSID auth string copied from the browser websocket frame, e.g.
    # 42["auth",{"session":"...","isDemo":1,"uid":123,"platform":1}]
    pocket_ssid: str = field(default_factory=lambda: os.getenv("POCKET_OPTION_SSID", ""))
    is_demo: bool = field(default_factory=lambda: _get_bool("POCKET_OPTION_DEMO", True))

    # --- Engine ---
    assets: list[str] = field(
        default_factory=lambda: _split(os.getenv("ASSETS", "")) or list(DEFAULT_ASSETS)
    )
    # Candle timeframe in seconds (60 = M1, 300 = M5, ...).
    timeframe: int = field(default_factory=lambda: int(os.getenv("TIMEFRAME", "60")))
    # Number of candles requested per scan.
    candle_count: int = field(default_factory=lambda: int(os.getenv("CANDLE_COUNT", "120")))
    # Seconds between automatic scans of the whole basket.
    scan_interval: int = field(default_factory=lambda: int(os.getenv("SCAN_INTERVAL", "60")))
    # Minimum confidence (0-100) required to emit/push a signal.
    min_confidence: float = field(
        default_factory=lambda: float(os.getenv("MIN_CONFIDENCE", "65"))
    )
    # Suppress repeat signals for the same asset+direction within this many seconds.
    signal_cooldown: int = field(
        default_factory=lambda: int(os.getenv("SIGNAL_COOLDOWN", "300"))
    )
    # Whether the auto-push loop starts enabled.
    autostart_signals: bool = field(
        default_factory=lambda: _get_bool("AUTOSTART_SIGNALS", True)
    )

    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    @property
    def live_mode(self) -> bool:
        """True when a Pocket Option SSID is configured (real platform data)."""
        return bool(self.pocket_ssid.strip())

    def recommended_expiry(self) -> int:
        """Suggested option expiry (seconds) given the candle timeframe."""
        # A common heuristic: expire after ~1-2 candles of the working timeframe.
        return max(self.timeframe, 60)

    def validate_for_telegram(self) -> None:
        if not self.telegram_bot_token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN is not set. Create a bot via @BotFather and "
                "put the token in your .env file."
            )
