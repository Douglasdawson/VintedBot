#!/usr/bin/env python3
"""
Vinted Alert Bot - Bot de alertas para productos de Vinted.
Recibe notificaciones en Telegram de productos recién publicados.
"""
import asyncio
import logging
import os
import signal
import sys
from dotenv import load_dotenv

from src.database import Database
from src.vinted_client import VintedClient
from src.telegram_bot import TelegramBot
from src.scanner import VintedScanner

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


class VintedAlertBot:
    """Clase principal que orquesta todos los componentes del bot."""

    def __init__(self):
        load_dotenv()

        # Configuración
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.vinted_domain = os.getenv("VINTED_DOMAIN", "es")
        self.scan_interval = int(os.getenv("SCAN_INTERVAL_SECONDS", "60"))

        if not self.telegram_token:
            raise ValueError("TELEGRAM_BOT_TOKEN no configurado en .env")

        # Componentes
        self.db: Database = None
        self.vinted: VintedClient = None
        self.telegram: TelegramBot = None
        self.scanner: VintedScanner = None

    async def setup(self) -> None:
        """Inicializa todos los componentes."""
        logger.info("Iniciando Vinted Alert Bot...")

        # Base de datos
        self.db = Database("vinted_bot.db")
        await self.db.connect()
        logger.info("Base de datos conectada")

        # Cliente de Vinted
        self.vinted = VintedClient(domain=self.vinted_domain)
        logger.info(f"Cliente Vinted configurado para: {self.vinted_domain}")

        # Bot de Telegram
        self.telegram = TelegramBot(self.telegram_token, self.db)
        self.telegram.setup()
        logger.info("Bot de Telegram configurado")

        # Scanner
        self.scanner = VintedScanner(
            vinted_client=self.vinted,
            database=self.db,
            telegram_bot=self.telegram,
            scan_interval=self.scan_interval,
        )
        logger.info(f"Scanner configurado con intervalo de {self.scan_interval}s")

    async def run(self) -> None:
        """Ejecuta el bot."""
        await self.setup()

        # Iniciar el bot de Telegram
        await self.telegram.application.initialize()
        await self.telegram.application.start()
        await self.telegram.application.updater.start_polling(drop_pending_updates=True)

        logger.info("Bot de Telegram iniciado")
        logger.info("Iniciando scanner de productos...")

        # Ejecutar el scanner en paralelo
        try:
            await self.scanner.start()
        except asyncio.CancelledError:
            logger.info("Scanner cancelado")

    async def shutdown(self) -> None:
        """Cierra todos los componentes de forma ordenada."""
        logger.info("Cerrando Vinted Alert Bot...")

        if self.scanner:
            await self.scanner.stop()

        if self.telegram and self.telegram.application:
            await self.telegram.application.updater.stop()
            await self.telegram.application.stop()
            await self.telegram.application.shutdown()

        if self.vinted:
            await self.vinted.close()

        if self.db:
            await self.db.close()

        logger.info("Bot cerrado correctamente")


async def main() -> None:
    """Función principal."""
    bot = VintedAlertBot()

    # Configurar manejo de señales para cierre limpio
    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info("Señal de cierre recibida")
        asyncio.create_task(bot.shutdown())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Interrupción de teclado")
    finally:
        await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
