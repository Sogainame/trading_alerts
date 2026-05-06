"""
Entry point для Trading Alerts v2.

Бесконечный цикл с автоматическим рестартом сканера при падении.
Это нужно потому что WebSocket Binance иногда дисконнектится по разным причинам
(сервер закрыл из-за idle, сетевой сбой, и т.д.).
"""
import asyncio
import logging

from src.scanner import Scanner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


async def main() -> None:
    while True:
        scanner = Scanner()
        try:
            await scanner.run()
        except KeyboardInterrupt:
            logging.info("Stopped by user.")
            break
        except Exception as e:
            logging.exception(f"Scanner crashed: {e}. Restarting in 10s...")
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
