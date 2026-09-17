"""Main application entry point for Bybit Futures Signal Engine."""

import asyncio
import signal

from app.config import settings
from app.database.repository import DatabaseRepository
from app.exchange.bybit import BybitAdapter
from app.market_data.provider import LiveMarketDataProvider
from app.market_data.ranking import UniverseSelector
from app.market_data.rest import BybitRestClient
from app.market_data.websocket import BybitWsClient
from app.telegram.bot import TelegramNotifier
from app.utils.logging import setup_logger

logger = setup_logger("signal_engine.main", level=settings.LOG_LEVEL)

TIMEFRAMES = ["5", "15", "60", "240"]  # 5m, 15m, 1h, 4h


class Application:
    """Orchestrates the entire signal engine lifecycle."""

    def __init__(self):
        self.is_running = False
        self.rest_client = BybitRestClient(
            base_url=settings.BYBIT_REST_URL,
            api_key=settings.BYBIT_API_KEY,
            api_secret=settings.BYBIT_API_SECRET,
        )
        self.exchange = BybitAdapter(self.rest_client)
        self.db = DatabaseRepository(settings.DATABASE_URL)
        self.market_provider = LiveMarketDataProvider(max_buffer_size=2500)
        self.ws_client = BybitWsClient(ws_url=settings.BYBIT_WS_URL)
        self.notifier = TelegramNotifier(
            bot_token=settings.TELEGRAM_BOT_TOKEN,
            chat_id=settings.TELEGRAM_CHAT_ID,
            cooldown_minutes=settings.SIGNAL_COOLDOWN_MINUTES,
        )
        self.active_symbols: list[str] = []
        self._periodic_tasks: list[asyncio.Task] = []

    async def initialize(self) -> None:
        """Initializes database schema and verifies configurations."""
        logger.info("Initializing Bybit Futures Signal Engine...")
        await self.db.init_db()

    async def select_universe(self) -> list[str]:
        """Runs dynamic ranking to select the TOP N liquid symbols."""
        logger.info(f"Selecting TOP {settings.TOP_SYMBOLS} USDT Perpetual pairs...")
        ranking_cfg = settings.load_ranking_config()
        selector = UniverseSelector(self.rest_client, ranking_cfg)
        top_candidates = await selector.select_top_symbols(top_n=settings.TOP_SYMBOLS)

        self.active_symbols = [c["symbol"] for c in top_candidates]
        await self.db.save_symbols(top_candidates)
        logger.info(f"Active Universe ({len(self.active_symbols)} pairs): {', '.join(self.active_symbols)}")
        return self.active_symbols

    async def bootstrap_history(self) -> None:
        """
        Deep bootstrap of historical closed candles for each active pair and timeframe.
        Paginates backwards to ensure at least BOOTSTRAP_CANDLE_COUNT bars.
        """
        logger.info(
            f"Starting historical bootstrap ({settings.BOOTSTRAP_CANDLE_COUNT} candles/TF) "
            f"for {len(self.active_symbols)} symbols..."
        )

        semaphore = asyncio.Semaphore(5)

        async def fetch_symbol_tf(symbol: str, tf: str):
            async with semaphore:
                try:
                    candles = await self.rest_client.get_historical_klines_paginated(
                        symbol=symbol,
                        interval=tf,
                        total_candles=settings.BOOTSTRAP_CANDLE_COUNT,
                    )
                    self.market_provider.bootstrap_candles(symbol, tf, candles)
                    await self.db.save_candles(symbol, tf, candles)
                except Exception as e:
                    logger.error(f"Error bootstrapping history for {symbol} TF={tf}: {e}")

        tasks = [
            fetch_symbol_tf(sym, tf)
            for sym in self.active_symbols
            for tf in TIMEFRAMES
        ]
        await asyncio.gather(*tasks)
        logger.info("Historical candle bootstrap completed successfully.")

    def setup_websocket_handlers(self) -> None:
        """Binds incoming WebSocket stream events to the market data provider and engine."""

        async def handle_kline(symbol: str, interval: str, candle: dict):
            # Only closed candles are used for technical indicators and structure!
            is_new_bar = self.market_provider.update_candle(symbol, interval, candle)
            if is_new_bar and candle.get("is_closed"):
                await self.db.save_candles(symbol, interval, [candle])
                logger.debug(f"New closed bar: {symbol} TF={interval} C={candle['close']}")
                # Future step hook: trigger feature engine and scoring here

        def handle_ticker(symbol: str, ticker: dict):
            self.market_provider.update_ticker(symbol, ticker)

        def handle_liquidation(symbol: str, liq: dict):
            logger.debug(f"Public Liquidation: {symbol} side={liq.get('side')} size={liq.get('size')} price={liq.get('price')}")

        self.ws_client.on_kline(handle_kline)
        self.ws_client.on_ticker(handle_ticker)
        self.ws_client.on_liquidation(handle_liquidation)

    async def start_streaming(self) -> None:
        """Builds topic list and launches the WebSocket client."""
        topics = []
        for sym in self.active_symbols:
            for tf in TIMEFRAMES:
                topics.append(f"kline.{tf}.{sym}")
            topics.append(f"tickers.{sym}")
            topics.append(f"allLiquidation.{sym}")

        logger.info(f"Subscribing to {len(topics)} WebSocket topics...")
        self.setup_websocket_handlers()
        await self.ws_client.start()
        await self.ws_client.subscribe(topics)

    async def _periodic_universe_refresh(self) -> None:
        """Periodically recalibrates the top symbols universe."""
        interval_secs = settings.TOP_REFRESH_INTERVAL_HOURS * 3600
        while self.is_running:
            try:
                await asyncio.sleep(interval_secs)
                logger.info("Periodic universe refresh triggered...")
                await self.select_universe()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error during periodic universe refresh: {e}")

    async def run(self) -> None:
        """Runs the complete application."""
        self.is_running = True
        await self.initialize()
        await self.select_universe()
        await self.bootstrap_history()
        await self.start_streaming()

        refresh_task = asyncio.create_task(self._periodic_universe_refresh(), name="universe_refresh")
        self._periodic_tasks.append(refresh_task)

        logger.info("Bybit Futures Signal Engine is running 24/7. Waiting for market events...")
        while self.is_running:
            await asyncio.sleep(1)

    async def shutdown(self) -> None:
        """Gracefully shuts down all components."""
        logger.info("Initiating graceful shutdown...")
        self.is_running = False
        for t in self._periodic_tasks:
            t.cancel()
        await self.ws_client.stop()
        await self.rest_client.close()
        logger.info("Engine successfully shut down.")


async def main():
    app = Application()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(app.shutdown()))
        except NotImplementedError:
            pass

    try:
        await app.run()
    except (asyncio.CancelledError, KeyboardInterrupt):
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
