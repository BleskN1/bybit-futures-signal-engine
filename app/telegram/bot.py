"""Telegram bot for dispatching high-confidence qualified signals with anti-spam cooldown."""

from typing import Any

import httpx

from app.signal.models import SignalCandidate
from app.telegram.formatter import TelegramSignalFormatter
from app.utils.logging import setup_logger

logger = setup_logger("signal_engine.telegram")


class TelegramNotifier:
    """Async Telegram notification dispatcher supporting formatted signals, dry run, and anti-spam."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        cooldown_minutes: int = 20,
        dry_run: bool = False,
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.cooldown_seconds = cooldown_minutes * 60
        self.dry_run = dry_run
        # Map: (symbol, direction) -> last_sent_timestamp_seconds
        self._sent_signals: dict[tuple[str, str], float] = {}

    def is_cooling_down(self, symbol: str, direction: str, current_ts: float) -> bool:
        """Checks if identical symbol & direction signal was sent within cooldown."""
        last_sent = self._sent_signals.get((symbol, direction))
        if last_sent is None:
            return False
        return (current_ts - last_sent) < self.cooldown_seconds

    async def send_signal(self, signal: SignalCandidate | dict[str, Any]) -> bool:
        """Sends a formatted message to Telegram if credentials are provided."""
        if isinstance(signal, SignalCandidate):
            symbol = signal.symbol
            direction = signal.direction
            current_time = signal.as_of_timestamp / 1000.0
            text = TelegramSignalFormatter.format(signal)
            signal_id = signal.id
        else:
            symbol = signal["symbol"]
            direction = signal["direction"]
            current_time = signal.get("timestamp", 0) / 1000.0
            signal_id = signal.get("id", "legacy")
            text = signal.get("text", "")

        if self.is_cooling_down(symbol, direction, current_time):
            logger.info(f"Signal {symbol} {direction} suppressed by Telegram anti-spam window.")
            return False

        if self.dry_run:
            logger.info(f"[DRY RUN] Telegram alert generated for {symbol} {direction} (ID: {signal_id})")
            self._sent_signals[(symbol, direction)] = current_time
            return True

        if not self.bot_token or not self.chat_id:
            logger.info(f"Telegram not configured; signal {signal_id} ({symbol} {direction}) logged locally.")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    self._sent_signals[(symbol, direction)] = current_time
                    logger.info(f"Telegram alert sent successfully for {symbol} {direction}")
                    return True
                else:
                    logger.error(f"Failed to send Telegram message: {res.status_code} {res.text}")
                    return False
        except Exception as e:
            logger.error(f"Telegram dispatch error: {e}")
            return False
