"""
Entry point.

Запускает Scanner в бесконечном цикле с авто-рестартом при падении.
Это нужно потому, что WebSocket Binance иногда дисконнектится — сервер
отрубает соединения старше 24 часов, бывают сетевые сбои и т.п.
Падение → пауза 10с → новый коннект.
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
