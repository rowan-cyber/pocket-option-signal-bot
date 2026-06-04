"""Render signals and status into Telegram-friendly HTML messages."""

from __future__ import annotations

from ..strategy.signals import Signal

DISCLAIMER = (
    "⚠ <i>Educational analysis, not financial advice. Binary options are high "
    "risk; no signal is guaranteed. Trade responsibly.</i>"
)


def _fmt_tf(seconds: int) -> str:
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"M{seconds // 60}"
    return f"{seconds}s"


def format_signal(sig: Signal) -> str:
    mode = "LIVE" if sig.live else "DEMO"
    lines = [
        f"{sig.emoji} <b>{sig.direction}</b> — <b>{sig.asset}</b>  [{mode}]",
        "",
        f"📊 Direction: <b>{sig.direction}</b> ({'UP' if sig.direction == 'CALL' else 'DOWN'})",
        f"⏱ Timeframe: {_fmt_tf(sig.timeframe)}   |   Expiry: {_fmt_tf(sig.expiry)}",
        f"🎯 Confidence: <b>{sig.confidence:.0f}%</b>",
        f"💲 Price: {sig.price:.5f}",
    ]
    reasons = sig.reasons()
    if reasons:
        lines.append("")
        lines.append("💡 <b>Why:</b>")
        lines.extend(f"  • {r}" for r in reasons)
    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def format_signal_list(signals: list[Signal]) -> str:
    if not signals:
        return "No signals cleared the confidence threshold right now. 🔍"
    return "\n\n".join(format_signal(s) for s in signals)


def format_status(*, live: bool, running: bool, config, subscribers: int) -> str:
    mode = "🟢 LIVE (real Pocket Option data)" if live else "🟡 DEMO (synthetic data)"
    auto = "ON" if running else "OFF"
    return "\n".join(
        [
            "🤖 <b>Pocket Option Signal Bot</b>",
            "",
            f"Mode: {mode}",
            f"Auto-push: <b>{auto}</b>  (every {config.scan_interval}s)",
            f"Subscribers: {subscribers}",
            f"Timeframe: {_fmt_tf(config.timeframe)}",
            f"Min confidence: {config.min_confidence:.0f}%",
            f"Cooldown: {config.signal_cooldown}s",
            f"Watching {len(config.assets)} assets: "
            f"{', '.join(config.assets[:8])}{' …' if len(config.assets) > 8 else ''}",
        ]
    )
