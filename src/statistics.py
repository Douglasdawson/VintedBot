"""
Sistema de estadísticas y análisis para el bot.
"""
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class UserStats:
    """Estadísticas de un usuario."""
    user_id: int
    total_alerts: int
    active_alerts: int
    total_notifications: int
    notifications_today: int
    notifications_this_week: int
    notifications_this_month: int
    avg_price_found: float
    min_price_found: float
    max_price_found: float
    most_active_alert: Optional[str]
    favorite_category: Optional[str]
    member_since: datetime


@dataclass
class AlertStats:
    """Estadísticas de una alerta específica."""
    alert_id: int
    alert_name: str
    total_matches: int
    matches_today: int
    matches_this_week: int
    avg_price: float
    min_price: float
    max_price: float
    last_match_at: Optional[datetime]
    created_at: datetime


@dataclass
class PriceHistory:
    """Historial de precio para un tipo de producto."""
    query: str
    avg_price: float
    min_price: float
    max_price: float
    price_trend: str  # "up", "down", "stable"
    sample_size: int


class StatisticsManager:
    """Gestiona las estadísticas del bot."""

    def __init__(self, database):
        self.db = database

    async def setup_tables(self) -> None:
        """Crea las tablas necesarias para estadísticas."""
        await self.db._connection.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                price REAL NOT NULL,
                currency TEXT DEFAULT 'EUR',
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (alert_id) REFERENCES alerts(id) ON DELETE CASCADE
            )
        """)

        await self.db._connection.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date DATE NOT NULL,
                notifications_count INTEGER DEFAULT 0,
                alerts_count INTEGER DEFAULT 0,
                avg_price REAL DEFAULT 0,
                UNIQUE(user_id, date),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        await self.db._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_history_alert ON price_history(alert_id)
        """)

        await self.db._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_daily_stats_user ON daily_stats(user_id, date)
        """)

        await self.db._connection.commit()

    async def record_match(self, alert_id: int, item_id: int, price: float, currency: str = "EUR") -> None:
        """Registra un match encontrado para estadísticas."""
        await self.db._connection.execute("""
            INSERT INTO price_history (alert_id, item_id, price, currency)
            VALUES (?, ?, ?, ?)
        """, (alert_id, item_id, price, currency))
        await self.db._connection.commit()

    async def update_daily_stats(self, user_id: int, price: float) -> None:
        """Actualiza las estadísticas diarias de un usuario."""
        today = datetime.now().date().isoformat()

        # Intentar actualizar o insertar
        await self.db._connection.execute("""
            INSERT INTO daily_stats (user_id, date, notifications_count, avg_price)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
                notifications_count = notifications_count + 1,
                avg_price = (avg_price * notifications_count + ?) / (notifications_count + 1)
        """, (user_id, today, price, price))
        await self.db._connection.commit()

    async def get_user_stats(self, user_id: int) -> UserStats:
        """Obtiene las estadísticas completas de un usuario."""
        now = datetime.now()
        today = now.date().isoformat()
        week_ago = (now - timedelta(days=7)).isoformat()
        month_ago = (now - timedelta(days=30)).isoformat()

        # Contar alertas
        cursor = await self.db._connection.execute("""
            SELECT COUNT(*), SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END)
            FROM alerts WHERE user_id = ?
        """, (user_id,))
        row = await cursor.fetchone()
        total_alerts = row[0] or 0
        active_alerts = row[1] or 0

        # Estadísticas de notificaciones
        cursor = await self.db._connection.execute("""
            SELECT COUNT(*) FROM notified_items ni
            JOIN alerts a ON ni.alert_id = a.id
            WHERE a.user_id = ?
        """, (user_id,))
        total_notifications = (await cursor.fetchone())[0] or 0

        # Notificaciones hoy
        cursor = await self.db._connection.execute("""
            SELECT notifications_count FROM daily_stats
            WHERE user_id = ? AND date = ?
        """, (user_id, today))
        row = await cursor.fetchone()
        notifications_today = row[0] if row else 0

        # Notificaciones esta semana
        cursor = await self.db._connection.execute("""
            SELECT SUM(notifications_count) FROM daily_stats
            WHERE user_id = ? AND date >= ?
        """, (user_id, week_ago[:10]))
        notifications_this_week = (await cursor.fetchone())[0] or 0

        # Notificaciones este mes
        cursor = await self.db._connection.execute("""
            SELECT SUM(notifications_count) FROM daily_stats
            WHERE user_id = ? AND date >= ?
        """, (user_id, month_ago[:10]))
        notifications_this_month = (await cursor.fetchone())[0] or 0

        # Estadísticas de precios
        cursor = await self.db._connection.execute("""
            SELECT AVG(ph.price), MIN(ph.price), MAX(ph.price)
            FROM price_history ph
            JOIN alerts a ON ph.alert_id = a.id
            WHERE a.user_id = ?
        """, (user_id,))
        row = await cursor.fetchone()
        avg_price = row[0] or 0
        min_price = row[1] or 0
        max_price = row[2] or 0

        # Alerta más activa
        cursor = await self.db._connection.execute("""
            SELECT a.name, COUNT(ni.id) as count
            FROM alerts a
            LEFT JOIN notified_items ni ON a.id = ni.alert_id
            WHERE a.user_id = ?
            GROUP BY a.id
            ORDER BY count DESC
            LIMIT 1
        """, (user_id,))
        row = await cursor.fetchone()
        most_active_alert = row[0] if row else None

        # Fecha de registro
        cursor = await self.db._connection.execute("""
            SELECT created_at FROM users WHERE id = ?
        """, (user_id,))
        row = await cursor.fetchone()
        member_since = datetime.fromisoformat(row[0]) if row and row[0] else now

        return UserStats(
            user_id=user_id,
            total_alerts=total_alerts,
            active_alerts=active_alerts,
            total_notifications=total_notifications,
            notifications_today=notifications_today,
            notifications_this_week=notifications_this_week,
            notifications_this_month=notifications_this_month,
            avg_price_found=round(avg_price, 2),
            min_price_found=round(min_price, 2),
            max_price_found=round(max_price, 2),
            most_active_alert=most_active_alert,
            favorite_category=None,  # TODO: implementar
            member_since=member_since,
        )

    async def get_alert_stats(self, alert_id: int) -> Optional[AlertStats]:
        """Obtiene las estadísticas de una alerta específica."""
        now = datetime.now()
        today = now.date().isoformat()
        week_ago = (now - timedelta(days=7)).isoformat()

        # Info de la alerta
        cursor = await self.db._connection.execute("""
            SELECT id, name, created_at FROM alerts WHERE id = ?
        """, (alert_id,))
        row = await cursor.fetchone()
        if not row:
            return None

        alert_name = row[1]
        created_at = datetime.fromisoformat(row[2]) if row[2] else now

        # Total de matches
        cursor = await self.db._connection.execute("""
            SELECT COUNT(*) FROM notified_items WHERE alert_id = ?
        """, (alert_id,))
        total_matches = (await cursor.fetchone())[0] or 0

        # Matches hoy
        cursor = await self.db._connection.execute("""
            SELECT COUNT(*) FROM notified_items
            WHERE alert_id = ? AND DATE(notified_at) = ?
        """, (alert_id, today))
        matches_today = (await cursor.fetchone())[0] or 0

        # Matches esta semana
        cursor = await self.db._connection.execute("""
            SELECT COUNT(*) FROM notified_items
            WHERE alert_id = ? AND notified_at >= ?
        """, (alert_id, week_ago))
        matches_this_week = (await cursor.fetchone())[0] or 0

        # Estadísticas de precios
        cursor = await self.db._connection.execute("""
            SELECT AVG(price), MIN(price), MAX(price)
            FROM price_history WHERE alert_id = ?
        """, (alert_id,))
        row = await cursor.fetchone()
        avg_price = row[0] or 0
        min_price = row[1] or 0
        max_price = row[2] or 0

        # Último match
        cursor = await self.db._connection.execute("""
            SELECT MAX(notified_at) FROM notified_items WHERE alert_id = ?
        """, (alert_id,))
        row = await cursor.fetchone()
        last_match_at = datetime.fromisoformat(row[0]) if row and row[0] else None

        return AlertStats(
            alert_id=alert_id,
            alert_name=alert_name,
            total_matches=total_matches,
            matches_today=matches_today,
            matches_this_week=matches_this_week,
            avg_price=round(avg_price, 2),
            min_price=round(min_price, 2),
            max_price=round(max_price, 2),
            last_match_at=last_match_at,
            created_at=created_at,
        )

    async def get_price_trend(self, alert_id: int, days: int = 7) -> Optional[PriceHistory]:
        """Analiza la tendencia de precios para una alerta."""
        threshold = (datetime.now() - timedelta(days=days)).isoformat()

        # Obtener historial de precios
        cursor = await self.db._connection.execute("""
            SELECT price, recorded_at FROM price_history
            WHERE alert_id = ? AND recorded_at >= ?
            ORDER BY recorded_at
        """, (alert_id, threshold))
        rows = await cursor.fetchall()

        if len(rows) < 2:
            return None

        prices = [row[0] for row in rows]
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        max_price = max(prices)

        # Calcular tendencia (comparar primera y segunda mitad)
        mid = len(prices) // 2
        first_half_avg = sum(prices[:mid]) / mid if mid > 0 else avg_price
        second_half_avg = sum(prices[mid:]) / (len(prices) - mid) if len(prices) > mid else avg_price

        if second_half_avg > first_half_avg * 1.05:
            trend = "up"
        elif second_half_avg < first_half_avg * 0.95:
            trend = "down"
        else:
            trend = "stable"

        # Obtener nombre de la alerta
        cursor = await self.db._connection.execute("""
            SELECT query, name FROM alerts WHERE id = ?
        """, (alert_id,))
        row = await cursor.fetchone()
        query = row[0] or row[1] if row else "Desconocido"

        return PriceHistory(
            query=query,
            avg_price=round(avg_price, 2),
            min_price=round(min_price, 2),
            max_price=round(max_price, 2),
            price_trend=trend,
            sample_size=len(prices),
        )

    async def cleanup_old_stats(self, days: int = 90) -> int:
        """Limpia estadísticas antiguas."""
        threshold = (datetime.now() - timedelta(days=days)).isoformat()

        cursor = await self.db._connection.execute("""
            DELETE FROM price_history WHERE recorded_at < ?
        """, (threshold,))
        price_deleted = cursor.rowcount

        cursor = await self.db._connection.execute("""
            DELETE FROM daily_stats WHERE date < ?
        """, (threshold[:10],))
        stats_deleted = cursor.rowcount

        await self.db._connection.commit()
        return price_deleted + stats_deleted
