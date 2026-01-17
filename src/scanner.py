"""
Scanner de productos de Vinted.
Busca nuevos productos y envía notificaciones.
"""
import asyncio
import logging
from typing import TYPE_CHECKING

from .vinted_client import VintedClient
from .database import Database

if TYPE_CHECKING:
    from .telegram_bot import TelegramBot

logger = logging.getLogger(__name__)


class VintedScanner:
    """Escanea Vinted en busca de nuevos productos según las alertas configuradas."""

    def __init__(
        self,
        vinted_client: VintedClient,
        database: Database,
        telegram_bot: "TelegramBot",
        scan_interval: int = 60,
    ):
        self.vinted = vinted_client
        self.db = database
        self.telegram = telegram_bot
        self.scan_interval = scan_interval
        self._running = False

    async def start(self) -> None:
        """Inicia el loop de escaneo."""
        self._running = True
        logger.info(f"Scanner iniciado. Intervalo: {self.scan_interval} segundos")

        while self._running:
            try:
                await self._scan_all_alerts()
            except Exception as e:
                logger.error(f"Error en el scanner: {e}")

            await asyncio.sleep(self.scan_interval)

    async def stop(self) -> None:
        """Detiene el scanner."""
        self._running = False
        logger.info("Scanner detenido")

    async def _scan_all_alerts(self) -> None:
        """Escanea todas las alertas activas."""
        alerts = await self.db.get_all_active_alerts()
        logger.debug(f"Escaneando {len(alerts)} alertas activas")

        for alert in alerts:
            try:
                await self._process_alert(alert)
                # Pequeña pausa entre alertas para no saturar la API
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Error procesando alerta {alert.id}: {e}")

        # Limpieza periódica de notificaciones antiguas
        await self.db.cleanup_old_notifications(days=7)

    async def _process_alert(self, alert) -> None:
        """Procesa una alerta individual."""
        logger.debug(f"Procesando alerta: {alert.name} (ID: {alert.id})")

        # Buscar productos según los filtros de la alerta
        items = await self.vinted.search(
            query=alert.query,
            catalog_ids=alert.get_catalog_ids(),
            brand_ids=alert.get_brand_ids(),
            size_ids=alert.get_size_ids(),
            material_ids=alert.get_material_ids(),
            color_ids=alert.get_color_ids(),
            status_ids=alert.get_status_ids(),
            price_from=alert.price_from,
            price_to=alert.price_to,
            order="newest_first",
            per_page=20,
        )

        if not items:
            logger.debug(f"No se encontraron productos para la alerta {alert.id}")
            return

        # Filtrar productos ya notificados
        new_items = []
        for item in items:
            if not await self.db.is_item_notified(alert.id, item.id):
                new_items.append(item)

        if not new_items:
            logger.debug(f"No hay productos nuevos para la alerta {alert.id}")
            return

        logger.info(f"Encontrados {len(new_items)} productos nuevos para alerta {alert.id}")

        # Enviar notificaciones
        for item in new_items:
            try:
                success = await self.telegram.send_notification(
                    user_id=alert.user_id,
                    item=item,
                    alert_name=alert.name,
                )
                if success:
                    await self.db.mark_item_notified(alert.id, item.id)
                    logger.debug(f"Notificación enviada para item {item.id}")
                # Pausa entre notificaciones
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Error enviando notificación para item {item.id}: {e}")
