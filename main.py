#!/usr/bin/env python3
"""
Vinted Alert Bot - Bot de alertas para productos de Vinted.
Versión Premium con suscripciones, estadísticas y notificaciones avanzadas.
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
from src.subscriptions import SubscriptionManager
from src.statistics import StatisticsManager
from src.notifications import NotificationManager, SniperMode
from src.ai_assistant import AIAssistant

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
        self.subscription_manager: SubscriptionManager = None
        self.statistics_manager: StatisticsManager = None
        self.notification_manager: NotificationManager = None
        self.sniper_mode: SniperMode = None
        self.ai_assistant: AIAssistant = None

    async def setup(self) -> None:
        """Inicializa todos los componentes."""
        logger.info("Iniciando Vinted Alert Bot Premium...")

        # Base de datos
        self.db = Database("vinted_bot.db")
        await self.db.connect()
        logger.info("Base de datos conectada")

        # Cliente de Vinted
        self.vinted = VintedClient(domain=self.vinted_domain)
        logger.info(f"Cliente Vinted configurado para: {self.vinted_domain}")

        # Gestor de suscripciones
        self.subscription_manager = SubscriptionManager(self.db)
        await self.subscription_manager.setup_tables()
        logger.info("Sistema de suscripciones inicializado")

        # Gestor de estadísticas
        self.statistics_manager = StatisticsManager(self.db)
        await self.statistics_manager.setup_tables()
        logger.info("Sistema de estadísticas inicializado")

        # Bot de Telegram
        self.telegram = TelegramBot(self.telegram_token, self.db)
        self.telegram.setup()
        self.telegram.subscription_manager = self.subscription_manager
        self.telegram.statistics_manager = self.statistics_manager
        logger.info("Bot de Telegram configurado")

        # Gestor de notificaciones
        self.notification_manager = NotificationManager(self.db, self.telegram)
        await self.notification_manager.setup_tables()
        self.telegram.notification_manager = self.notification_manager
        logger.info("Sistema de notificaciones inicializado")

        # Modo Sniper
        self.sniper_mode = SniperMode(scan_interval=30)
        logger.info("Modo Sniper disponible")

        # Asistente IA (opcional - requiere OPENAI_API_KEY)
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            self.ai_assistant = AIAssistant(openai_key)
            self.telegram.ai_assistant = self.ai_assistant
            logger.info("Asistente IA inicializado")
        else:
            logger.warning("OPENAI_API_KEY no configurado - funciones IA deshabilitadas")

        # Scanner
        self.scanner = VintedScanner(
            vinted_client=self.vinted,
            database=self.db,
            telegram_bot=self.telegram,
            scan_interval=self.scan_interval,
        )
        # Inyectar dependencias adicionales al scanner
        self.scanner.subscription_manager = self.subscription_manager
        self.scanner.statistics_manager = self.statistics_manager
        self.scanner.notification_manager = self.notification_manager
        self.scanner.sniper_mode = self.sniper_mode
        logger.info(f"Scanner configurado con intervalo base de {self.scan_interval}s")

    async def run(self) -> None:
        """Ejecuta el bot."""
        await self.setup()

        # Iniciar el bot de Telegram
        await self.telegram.application.initialize()
        await self.telegram.application.start()
        await self.telegram.application.updater.start_polling(drop_pending_updates=True)

        logger.info("Bot de Telegram iniciado")
        logger.info("=" * 50)
        logger.info("Vinted Alert Bot Premium está funcionando!")
        logger.info("=" * 50)

        # Programar tareas periódicas
        asyncio.create_task(self._daily_tasks())
        asyncio.create_task(self._check_price_drops())

        # Ejecutar el scanner
        try:
            await self.scanner.start()
        except asyncio.CancelledError:
            logger.info("Scanner cancelado")

    async def _daily_tasks(self) -> None:
        """Ejecuta tareas diarias como envío de resúmenes y limpieza."""
        while True:
            try:
                # Esperar hasta las 20:00 (o la hora configurada por cada usuario)
                await asyncio.sleep(3600)  # Verificar cada hora

                # Limpiar datos antiguos
                await self.statistics_manager.cleanup_old_stats(days=90)
                await self.notification_manager.cleanup_old_data(days=7)
                await self.db.cleanup_old_notifications(days=7)

                logger.info("Tareas de limpieza completadas")

            except Exception as e:
                logger.error(f"Error en tareas diarias: {e}")

    async def _check_price_drops(self) -> None:
        """Verifica bajadas de precio periódicamente."""
        while True:
            try:
                await asyncio.sleep(1800)  # Cada 30 minutos

                alerts = await self.notification_manager.check_price_drops(self.vinted)
                for user_id, alert in alerts:
                    await self.notification_manager.send_price_drop_notification(user_id, alert)

                if alerts:
                    logger.info(f"Enviadas {len(alerts)} alertas de bajada de precio")

            except Exception as e:
                logger.error(f"Error verificando bajadas de precio: {e}")

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
