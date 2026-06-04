"""Entry point: start the Pocket Option Telegram signal bot."""

from __future__ import annotations

from signalbot.bot.telegram_bot import SignalBot
from signalbot.config import Config
from signalbot.engine import SignalEngine
from signalbot.logger import get_logger, setup_logging
from signalbot.pocket.client import create_client


def main() -> None:
    config = Config()
    setup_logging(config.log_level)
    log = get_logger("run")

    if config.live_mode:
        log.info("SSID detected -> LIVE mode (real Pocket Option data).")
    else:
        log.info("No SSID -> DEMO mode (synthetic data). Set POCKET_OPTION_SSID for live.")

    client = create_client(config.pocket_ssid, is_demo=config.is_demo)
    engine = SignalEngine(config, client)
    bot = SignalBot(config, engine)
    bot.build()
    bot.run()


if __name__ == "__main__":
    main()
