"""
Scanner de productos de Vinted.
Busca nuevos productos y envía notificaciones.
Versión Premium con modo sniper y estadísticas.
"""
import asyncio
import logging
from typing import TYPE_CHECKING, Optional

from .vinted_client import VintedClient
from .database import Database

if TYPE_CHECKING:
    from .telegram_bot import TelegramBot
    from .subscriptions import SubscriptionManager
    from .statistics import StatisticsManager
    from .notifications import NotificationManager, SniperMode

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

        # Componentes opcionales (inyectados después)
        self.subscription_manager: Optional["SubscriptionManager"] = None
        self.statistics_manager: Optional["StatisticsManager"] = None
        self.notification_manager: Optional["NotificationManager"] = None
        self.sniper_mode: Optional["SniperMode"] = None

    async def start(self) -> None:
        """Inicia el loop de escaneo."""
        self._running = True
        logger.info(f"Scanner iniciado. Intervalo base: {self.scan_interval} segundos")

        while self._running:
            try:
                await self._scan_all_alerts()
            except Exception as e:
                logger.error(f"Error en el scanner: {e}")

            # Determinar intervalo de escaneo
            interval = await self._get_next_scan_interval()
            await asyncio.sleep(interval)

    async def stop(self) -> None:
        """Detiene el scanner."""
        self._running = False
        logger.info("Scanner detenido")

    async def _get_next_scan_interval(self) -> int:
        """Determina el intervalo hasta el próximo escaneo."""
        # Si hay usuarios con modo sniper activo, usar intervalo reducido
        if self.sniper_mode and self.sniper_mode.get_active_users():
            return self.sniper_mode.scan_interval

        return self.scan_interval

    async def _scan_all_alerts(self) -> None:
        """Escanea todas las alertas activas."""
        alerts = await self.db.get_all_active_alerts()
        logger.debug(f"Escaneando {len(alerts)} alertas activas")

        # Agrupar alertas por usuario para optimizar
        alerts_by_user: dict[int, list] = {}
        for alert in alerts:
            if alert.user_id not in alerts_by_user:
                alerts_by_user[alert.user_id] = []
            alerts_by_user[alert.user_id].append(alert)

        for user_id, user_alerts in alerts_by_user.items():
            try:
                # Verificar si el usuario tiene modo sniper activo
                is_sniper = self.sniper_mode and self.sniper_mode.is_active_for_user(user_id)

                # Obtener intervalo según plan del usuario
                user_interval = self.scan_interval
                if self.subscription_manager:
                    user_interval = await self.subscription_manager.get_user_scan_interval(user_id)

                for alert in user_alerts:
                    await self._process_alert(alert, is_sniper)
                    # Pequeña pausa entre alertas
                    await asyncio.sleep(1 if is_sniper else 2)

            except Exception as e:
                logger.error(f"Error procesando alertas del usuario {user_id}: {e}")

        # Limpieza periódica
        await self.db.cleanup_old_notifications(days=7)

    async def _process_alert(self, alert, is_sniper: bool = False) -> None:
        """Procesa una alerta individual."""
        logger.debug(f"Procesando alerta: {alert.name} (ID: {alert.id})")

        # Obtener filtros avanzados si existen
        advanced_filters = await self._get_advanced_filters(alert.id)

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
            per_page=20 if not is_sniper else 10,  # Menos resultados en modo sniper para rapidez
            **advanced_filters,
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

        logger.info(f"Encontrados {len(new_items)} productos nuevos para alerta '{alert.name}'")

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

                    # Registrar para estadísticas
                    if self.statistics_manager:
                        await self.statistics_manager.record_match(
                            alert_id=alert.id,
                            item_id=item.id,
                            price=item.price,
                            currency=item.currency,
                        )
                        await self.statistics_manager.update_daily_stats(
                            user_id=alert.user_id,
                            price=item.price,
                        )

                    # Registrar para resumen diario
                    if self.notification_manager:
                        await self.notification_manager.record_daily_item(
                            user_id=alert.user_id,
                            alert_id=alert.id,
                            alert_name=alert.name,
                            item_id=item.id,
                            title=item.title,
                            price=item.price,
                            url=item.url,
                        )

                # Pausa entre notificaciones (más corta en modo sniper)
                await asyncio.sleep(0.3 if is_sniper else 0.5)

            except Exception as e:
                logger.error(f"Error enviando notificación para item {item.id}: {e}")

    async def _get_advanced_filters(self, alert_id: int) -> dict:
        """Obtiene los filtros avanzados de una alerta."""
        try:
            cursor = await self.db._connection.execute("""
                SELECT verified_seller_only, free_shipping_only, min_seller_rating,
                       min_seller_reviews, excluded_sellers, country_codes
                FROM alert_advanced_filters WHERE alert_id = ?
            """, (alert_id,))
            row = await cursor.fetchone()

            if not row:
                return {}

            filters = {}
            if row[0]:  # verified_seller_only
                filters["verified_seller_only"] = True
            if row[1]:  # free_shipping_only
                filters["free_shipping_only"] = True
            if row[2]:  # min_seller_rating
                filters["min_seller_rating"] = row[2]
            if row[3]:  # min_seller_reviews
                filters["min_seller_reviews"] = row[3]
            if row[4]:  # excluded_sellers (JSON)
                import json
                filters["excluded_sellers"] = json.loads(row[4])
            if row[5]:  # country_codes (JSON)
                import json
                filters["country_codes"] = json.loads(row[5])

            return filters

        except Exception:
            return {}
