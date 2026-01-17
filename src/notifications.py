"""
Sistema de notificaciones mejoradas.
Incluye modo sniper, resúmenes diarios y alertas de bajada de precio.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .telegram_bot import TelegramBot
    from .database import Database

logger = logging.getLogger(__name__)


@dataclass
class PriceDropAlert:
    """Alerta de bajada de precio."""
    item_id: int
    title: str
    old_price: float
    new_price: float
    drop_percentage: float
    url: str
    photo_url: Optional[str]


@dataclass
class DailySummary:
    """Resumen diario de actividad."""
    user_id: int
    date: str
    total_matches: int
    alerts_with_matches: list[tuple[str, int]]  # (nombre_alerta, num_matches)
    avg_price: float
    best_deal: Optional[tuple[str, float, str]]  # (título, precio, url)


class NotificationManager:
    """Gestiona las notificaciones avanzadas."""

    def __init__(self, database: "Database", telegram_bot: "TelegramBot"):
        self.db = database
        self.telegram = telegram_bot
        self._price_watch: dict[int, dict] = {}  # item_id -> {price, last_check}

    async def setup_tables(self) -> None:
        """Crea las tablas necesarias para notificaciones avanzadas."""
        await self.db._connection.execute("""
            CREATE TABLE IF NOT EXISTS watched_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                title TEXT,
                initial_price REAL NOT NULL,
                current_price REAL NOT NULL,
                lowest_price REAL NOT NULL,
                url TEXT,
                photo_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, item_id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        await self.db._connection.execute("""
            CREATE TABLE IF NOT EXISTS notification_preferences (
                user_id INTEGER PRIMARY KEY,
                daily_summary_enabled INTEGER DEFAULT 1,
                daily_summary_hour INTEGER DEFAULT 20,
                price_drop_enabled INTEGER DEFAULT 1,
                price_drop_threshold REAL DEFAULT 10.0,
                sniper_mode_enabled INTEGER DEFAULT 0,
                quiet_hours_start INTEGER,
                quiet_hours_end INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        await self.db._connection.execute("""
            CREATE TABLE IF NOT EXISTS daily_summary_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date DATE NOT NULL,
                alert_id INTEGER NOT NULL,
                alert_name TEXT,
                item_id INTEGER NOT NULL,
                title TEXT,
                price REAL,
                url TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        await self.db._connection.commit()

    async def get_preferences(self, user_id: int) -> dict:
        """Obtiene las preferencias de notificación de un usuario."""
        cursor = await self.db._connection.execute("""
            SELECT daily_summary_enabled, daily_summary_hour, price_drop_enabled,
                   price_drop_threshold, sniper_mode_enabled, quiet_hours_start, quiet_hours_end
            FROM notification_preferences WHERE user_id = ?
        """, (user_id,))
        row = await cursor.fetchone()

        if row:
            return {
                "daily_summary_enabled": bool(row[0]),
                "daily_summary_hour": row[1],
                "price_drop_enabled": bool(row[2]),
                "price_drop_threshold": row[3],
                "sniper_mode_enabled": bool(row[4]),
                "quiet_hours_start": row[5],
                "quiet_hours_end": row[6],
            }

        # Valores por defecto
        return {
            "daily_summary_enabled": True,
            "daily_summary_hour": 20,
            "price_drop_enabled": True,
            "price_drop_threshold": 10.0,
            "sniper_mode_enabled": False,
            "quiet_hours_start": None,
            "quiet_hours_end": None,
        }

    async def update_preferences(self, user_id: int, **kwargs) -> None:
        """Actualiza las preferencias de notificación."""
        # Obtener preferencias actuales
        prefs = await self.get_preferences(user_id)
        prefs.update(kwargs)

        await self.db._connection.execute("""
            INSERT INTO notification_preferences
            (user_id, daily_summary_enabled, daily_summary_hour, price_drop_enabled,
             price_drop_threshold, sniper_mode_enabled, quiet_hours_start, quiet_hours_end)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                daily_summary_enabled = excluded.daily_summary_enabled,
                daily_summary_hour = excluded.daily_summary_hour,
                price_drop_enabled = excluded.price_drop_enabled,
                price_drop_threshold = excluded.price_drop_threshold,
                sniper_mode_enabled = excluded.sniper_mode_enabled,
                quiet_hours_start = excluded.quiet_hours_start,
                quiet_hours_end = excluded.quiet_hours_end
        """, (
            user_id,
            1 if prefs["daily_summary_enabled"] else 0,
            prefs["daily_summary_hour"],
            1 if prefs["price_drop_enabled"] else 0,
            prefs["price_drop_threshold"],
            1 if prefs["sniper_mode_enabled"] else 0,
            prefs["quiet_hours_start"],
            prefs["quiet_hours_end"],
        ))
        await self.db._connection.commit()

    async def is_quiet_hours(self, user_id: int) -> bool:
        """Verifica si estamos en horas de silencio para el usuario."""
        prefs = await self.get_preferences(user_id)
        start = prefs.get("quiet_hours_start")
        end = prefs.get("quiet_hours_end")

        if start is None or end is None:
            return False

        current_hour = datetime.now().hour

        if start <= end:
            return start <= current_hour < end
        else:  # Cruce de medianoche
            return current_hour >= start or current_hour < end

    async def add_watched_item(
        self,
        user_id: int,
        item_id: int,
        title: str,
        price: float,
        url: str,
        photo_url: Optional[str] = None,
    ) -> bool:
        """Añade un producto a la lista de seguimiento de precios."""
        try:
            await self.db._connection.execute("""
                INSERT INTO watched_items
                (user_id, item_id, title, initial_price, current_price, lowest_price, url, photo_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, item_id) DO UPDATE SET
                    current_price = excluded.current_price,
                    last_checked = CURRENT_TIMESTAMP
            """, (user_id, item_id, title, price, price, price, url, photo_url))
            await self.db._connection.commit()
            return True
        except Exception as e:
            logger.error(f"Error añadiendo item vigilado: {e}")
            return False

    async def check_price_drops(self, vinted_client) -> list[tuple[int, PriceDropAlert]]:
        """Comprueba bajadas de precio en productos vigilados."""
        alerts = []

        cursor = await self.db._connection.execute("""
            SELECT w.user_id, w.item_id, w.title, w.current_price, w.lowest_price,
                   w.url, w.photo_url, np.price_drop_threshold
            FROM watched_items w
            LEFT JOIN notification_preferences np ON w.user_id = np.user_id
            WHERE w.last_checked < datetime('now', '-1 hour')
        """)
        rows = await cursor.fetchall()

        for row in rows:
            user_id, item_id, title, current_price, lowest_price, url, photo_url, threshold = row
            threshold = threshold or 10.0

            # Obtener precio actual del item
            item = await vinted_client.get_item(item_id)
            if not item:
                continue

            new_price = item.price

            # Actualizar precio en BD
            await self.db._connection.execute("""
                UPDATE watched_items
                SET current_price = ?, lowest_price = MIN(lowest_price, ?), last_checked = CURRENT_TIMESTAMP
                WHERE user_id = ? AND item_id = ?
            """, (new_price, new_price, user_id, item_id))

            # Verificar si hay bajada significativa
            if new_price < current_price:
                drop_percentage = ((current_price - new_price) / current_price) * 100

                if drop_percentage >= threshold:
                    alert = PriceDropAlert(
                        item_id=item_id,
                        title=title,
                        old_price=current_price,
                        new_price=new_price,
                        drop_percentage=round(drop_percentage, 1),
                        url=url,
                        photo_url=photo_url,
                    )
                    alerts.append((user_id, alert))

        await self.db._connection.commit()
        return alerts

    async def send_price_drop_notification(self, user_id: int, alert: PriceDropAlert) -> bool:
        """Envía una notificación de bajada de precio."""
        if await self.is_quiet_hours(user_id):
            return False

        message = (
            f"📉 *BAJADA DE PRECIO*\n\n"
            f"*{alert.title}*\n\n"
            f"💰 Antes: ~{alert.old_price}€~\n"
            f"🔥 Ahora: *{alert.new_price}€*\n"
            f"📊 Bajada: *-{alert.drop_percentage}%*\n\n"
            f"🔗 [Ver en Vinted]({alert.url})"
        )

        try:
            if alert.photo_url:
                await self.telegram.application.bot.send_photo(
                    chat_id=user_id,
                    photo=alert.photo_url,
                    caption=message,
                    parse_mode="Markdown",
                )
            else:
                await self.telegram.application.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode="Markdown",
                )
            return True
        except Exception as e:
            logger.error(f"Error enviando notificación de bajada de precio: {e}")
            return False

    async def record_daily_item(
        self,
        user_id: int,
        alert_id: int,
        alert_name: str,
        item_id: int,
        title: str,
        price: float,
        url: str,
    ) -> None:
        """Registra un item para el resumen diario."""
        today = datetime.now().date().isoformat()

        await self.db._connection.execute("""
            INSERT INTO daily_summary_items
            (user_id, date, alert_id, alert_name, item_id, title, price, url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, today, alert_id, alert_name, item_id, title, price, url))
        await self.db._connection.commit()

    async def generate_daily_summary(self, user_id: int) -> Optional[DailySummary]:
        """Genera el resumen diario para un usuario."""
        today = datetime.now().date().isoformat()

        # Obtener items del día
        cursor = await self.db._connection.execute("""
            SELECT alert_name, item_id, title, price, url
            FROM daily_summary_items
            WHERE user_id = ? AND date = ?
            ORDER BY price ASC
        """, (user_id, today))
        rows = await cursor.fetchall()

        if not rows:
            return None

        # Agrupar por alerta
        alerts_matches: dict[str, int] = {}
        prices = []
        best_deal = None

        for row in rows:
            alert_name, item_id, title, price, url = row
            alerts_matches[alert_name] = alerts_matches.get(alert_name, 0) + 1
            prices.append(price)

            if best_deal is None or price < best_deal[1]:
                best_deal = (title, price, url)

        return DailySummary(
            user_id=user_id,
            date=today,
            total_matches=len(rows),
            alerts_with_matches=list(alerts_matches.items()),
            avg_price=round(sum(prices) / len(prices), 2) if prices else 0,
            best_deal=best_deal,
        )

    async def send_daily_summary(self, user_id: int) -> bool:
        """Envía el resumen diario a un usuario."""
        summary = await self.generate_daily_summary(user_id)

        if not summary or summary.total_matches == 0:
            return False

        message = f"📊 *RESUMEN DEL DÍA*\n"
        message += f"_{summary.date}_\n\n"
        message += f"🔔 Total de coincidencias: *{summary.total_matches}*\n"
        message += f"💰 Precio medio: *{summary.avg_price}€*\n\n"

        message += "*Por alerta:*\n"
        for alert_name, count in summary.alerts_with_matches:
            message += f"  • {alert_name}: {count} productos\n"

        if summary.best_deal:
            title, price, url = summary.best_deal
            message += f"\n🏆 *Mejor oferta:*\n"
            message += f"_{title[:50]}..._\n" if len(title) > 50 else f"_{title}_\n"
            message += f"💰 *{price}€*\n"
            message += f"[Ver producto]({url})"

        try:
            await self.telegram.application.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
            return True
        except Exception as e:
            logger.error(f"Error enviando resumen diario: {e}")
            return False

    async def cleanup_old_data(self, days: int = 7) -> None:
        """Limpia datos antiguos de resúmenes."""
        threshold = (datetime.now() - timedelta(days=days)).date().isoformat()

        await self.db._connection.execute("""
            DELETE FROM daily_summary_items WHERE date < ?
        """, (threshold,))
        await self.db._connection.commit()


class SniperMode:
    """Modo sniper para escaneo rápido de productos."""

    def __init__(self, scan_interval: int = 30):
        self.scan_interval = scan_interval
        self._active_users: set[int] = set()
        self._running = False

    def activate_for_user(self, user_id: int) -> None:
        """Activa el modo sniper para un usuario."""
        self._active_users.add(user_id)
        logger.info(f"Modo sniper activado para usuario {user_id}")

    def deactivate_for_user(self, user_id: int) -> None:
        """Desactiva el modo sniper para un usuario."""
        self._active_users.discard(user_id)
        logger.info(f"Modo sniper desactivado para usuario {user_id}")

    def is_active_for_user(self, user_id: int) -> bool:
        """Verifica si el modo sniper está activo para un usuario."""
        return user_id in self._active_users

    def get_active_users(self) -> set[int]:
        """Obtiene los usuarios con modo sniper activo."""
        return self._active_users.copy()
