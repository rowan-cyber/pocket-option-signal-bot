"""Telegram bot wiring: commands, subscriber management and the auto-push loop."""

from __future__ import annotations

from html import escape

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from ..config import Config
from ..engine import SignalEngine
from ..logger import get_logger
from ..pocket import assets as asset_utils
from . import formatting

log = get_logger(__name__)

HELP_TEXT = (
    "<b>Commands</b>\n"
    "/start – welcome &amp; subscribe\n"
    "/help – this help\n"
    "/status – bot mode &amp; settings\n"
    "/scan – run an immediate scan now\n"
    "/signals on|off – toggle auto-push for this chat\n"
    "/watch &lt;ASSET&gt; – add an asset (e.g. /watch EURUSD_otc)\n"
    "/unwatch &lt;ASSET&gt; – remove an asset\n"
    "/assets [otc|real] – list available assets\n"
    "/settings – view strategy thresholds\n"
    "/chatid – show this chat's id"
)


class SignalBot:
    def __init__(self, config: Config, engine: SignalEngine):
        self.config = config
        self.engine = engine
        # Chats that receive auto-pushed signals.
        self.subscribers: set[int] = set()
        for cid in config.chat_ids:
            try:
                self.subscribers.add(int(cid))
            except ValueError:
                log.warning("Ignoring invalid TELEGRAM_CHAT_IDS entry: %r", cid)
        # Whether a fresh /start auto-subscribes the chat (admin intent).
        self.autostart = config.autostart_signals
        self.app: Application | None = None

    @property
    def auto_running(self) -> bool:
        """Auto-push is active whenever at least one chat is subscribed."""
        return bool(self.subscribers)

    # ----- lifecycle -----
    def build(self) -> Application:
        self.config.validate_for_telegram()
        app = Application.builder().token(self.config.telegram_bot_token).build()
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("scan", self.cmd_scan))
        app.add_handler(CommandHandler("signals", self.cmd_signals))
        app.add_handler(CommandHandler("watch", self.cmd_watch))
        app.add_handler(CommandHandler("unwatch", self.cmd_unwatch))
        app.add_handler(CommandHandler("assets", self.cmd_assets))
        app.add_handler(CommandHandler("settings", self.cmd_settings))
        app.add_handler(CommandHandler("chatid", self.cmd_chatid))
        app.post_init = self._post_init
        app.post_shutdown = self._post_shutdown
        self.app = app
        return app

    async def _post_init(self, app: Application) -> None:
        ok = await self.engine.connect()
        if not ok and self.engine.is_live:
            log.error("Engine failed to connect to Pocket Option; check SSID.")
        if app.job_queue is not None:
            app.job_queue.run_repeating(
                self._auto_scan_job,
                interval=self.config.scan_interval,
                first=5,
                name="auto_scan",
            )
        log.info("Bot ready. Live=%s, auto-push=%s", self.engine.is_live, self.auto_running)

    async def _post_shutdown(self, app: Application) -> None:
        await self.engine.disconnect()

    # ----- helpers -----
    async def _reply(self, update: Update, text: str) -> None:
        if not update.message:
            return
        try:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        except Exception as exc:
            log.warning("Failed to send reply: %s", exc)

    # ----- commands -----
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        if self.autostart:
            self.subscribers.add(chat_id)
            sub_line = (
                "You're subscribed to auto-pushed CALL/PUT signals based on a "
                "confluence of indicators applied to Pocket Option market data."
            )
        else:
            sub_line = (
                "Auto-push is off by default here. Send <b>/signals on</b> to "
                "start receiving CALL/PUT signals, or <b>/scan</b> for a one-off."
            )
        await self._reply(
            update,
            "👋 <b>Welcome to the Pocket Option Signal Bot!</b>\n\n"
            + sub_line
            + "\n\n"
            + HELP_TEXT
            + "\n\n"
            + formatting.DISCLAIMER,
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._reply(update, HELP_TEXT)

    async def cmd_chatid(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._reply(update, f"This chat id: <code>{update.effective_chat.id}</code>")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._reply(
            update,
            formatting.format_status(
                live=self.engine.is_live,
                running=self.auto_running,
                config=self.config,
                subscribers=len(self.subscribers),
            ),
        )

    async def cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        p = self.engine.strategy.params
        text = (
            "<b>Strategy parameters</b>\n"
            f"EMA: {p.ema_fast}/{p.ema_slow}\n"
            f"RSI: {p.rsi_period} (OB {p.rsi_overbought:.0f} / OS {p.rsi_oversold:.0f})\n"
            f"MACD: {p.macd_fast}/{p.macd_slow}/{p.macd_signal}\n"
            f"Bollinger: {p.bb_period}, {p.bb_std}σ\n"
            f"ADX: {p.adx_period} (min trend {p.adx_min:.0f})\n"
            f"Stochastic: {p.stoch_k}/{p.stoch_d}/{p.stoch_smooth}\n\n"
            f"Min confidence to push: {self.config.min_confidence:.0f}%"
        )
        await self._reply(update, text)

    async def cmd_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._reply(update, "🔍 Scanning… this can take a few seconds.")
        signals = await self.engine.scan(apply_cooldown=False)
        await self._reply(update, formatting.format_signal_list(signals))

    async def cmd_signals(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        arg = (context.args[0].lower() if context.args else "")
        chat_id = update.effective_chat.id
        if arg == "on":
            self.subscribers.add(chat_id)
            await self._reply(update, "✅ Auto-push enabled for this chat.")
        elif arg == "off":
            self.subscribers.discard(chat_id)
            await self._reply(update, "🛑 Auto-push disabled for this chat.")
        else:
            await self._reply(update, "Usage: /signals on  |  /signals off")

    async def cmd_watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await self._reply(update, "Usage: /watch EURUSD_otc")
            return
        asset = asset_utils.normalize(context.args[0])
        if not asset_utils.is_known_asset(asset):
            await self._reply(
                update,
                f"❓ Unknown asset <code>{escape(asset)}</code>. Try /assets to see valid names.",
            )
            return
        if asset in self.config.assets:
            await self._reply(update, f"Already watching <b>{asset}</b>.")
            return
        self.config.assets.append(asset)
        await self._reply(update, f"➕ Now watching <b>{asset}</b>.")

    async def cmd_unwatch(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await self._reply(update, "Usage: /unwatch EURUSD_otc")
            return
        asset = asset_utils.normalize(context.args[0])
        if asset in self.config.assets:
            self.config.assets.remove(asset)
            await self._reply(update, f"➖ Stopped watching <b>{escape(asset)}</b>.")
        else:
            await self._reply(update, f"Not watching <code>{escape(asset)}</code>.")

    async def cmd_assets(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        arg = (context.args[0].lower() if context.args else "")
        names = asset_utils.list_assets(
            otc_only=(arg == "otc"), real_only=(arg == "real")
        )
        shown = ", ".join(names[:60])
        more = "" if len(names) <= 60 else f"\n… and {len(names) - 60} more"
        await self._reply(update, f"<b>Assets ({len(names)})</b>\n{shown}{more}")

    # ----- auto-push job -----
    async def _auto_scan_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.subscribers:
            return
        try:
            signals = await self.engine.scan(apply_cooldown=True)
        except Exception as exc:
            log.exception("auto scan failed: %s", exc)
            return
        if not signals:
            return
        text = formatting.format_signal_list(signals)
        for chat_id in list(self.subscribers):
            try:
                await context.bot.send_message(
                    chat_id=chat_id, text=text, parse_mode=ParseMode.HTML
                )
            except Exception as exc:
                log.warning("Failed to push to %s: %s", chat_id, exc)

    def run(self) -> None:
        app = self.app or self.build()
        log.info("Starting Telegram polling…")
        app.run_polling(allowed_updates=["message"])
