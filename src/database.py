"""
Gestión de base de datos SQLite para alertas y productos notificados.
"""
import aiosqlite
import json
import logging
from typing import Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    """Representa una alerta de búsqueda configurada por el usuario."""
    id: Optional[int]
    user_id: int
    name: str
    query: Optional[str] = None
    catalog_ids: Optional[str] = None  # JSON string de lista
    brand_ids: Optional[str] = None
    size_ids: Optional[str] = None
    material_ids: Optional[str] = None
    color_ids: Optional[str] = None
    status_ids: Optional[str] = None
    price_from: Optional[float] = None
    price_to: Optional[float] = None
    is_active: bool = True

    def get_catalog_ids(self) -> Optional[list[int]]:
        if self.catalog_ids:
            return json.loads(self.catalog_ids)
        return None

    def get_brand_ids(self) -> Optional[list[int]]:
        if self.brand_ids:
            return json.loads(self.brand_ids)
        return None

    def get_size_ids(self) -> Optional[list[int]]:
        if self.size_ids:
            return json.loads(self.size_ids)
        return None

    def get_material_ids(self) -> Optional[list[int]]:
        if self.material_ids:
            return json.loads(self.material_ids)
        return None

    def get_color_ids(self) -> Optional[list[int]]:
        if self.color_ids:
            return json.loads(self.color_ids)
        return None

    def get_status_ids(self) -> Optional[list[int]]:
        if self.status_ids:
            return json.loads(self.status_ids)
        return None

    def to_display_string(self) -> str:
        """Genera una representación legible de la alerta."""
        parts = [f"*{self.name}*"]
        if self.query:
            parts.append(f"Buscar: _{self.query}_")
        if self.price_from or self.price_to:
            price_range = ""
            if self.price_from:
                price_range += f"{self.price_from}€"
            else:
                price_range += "0€"
            price_range += " - "
            if self.price_to:
                price_range += f"{self.price_to}€"
            else:
                price_range += "sin límite"
            parts.append(f"Precio: {price_range}")
        status = "Activa" if self.is_active else "Pausada"
        parts.append(f"Estado: {status}")
        return "\n".join(parts)


class Database:
    """Gestiona la base de datos SQLite."""

    def __init__(self, db_path: str = "vinted_bot.db"):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Conecta a la base de datos y crea las tablas si no existen."""
        self._connection = await aiosqlite.connect(self.db_path)
        await self._create_tables()

    async def _create_tables(self) -> None:
        """Crea las tablas necesarias."""
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                query TEXT,
                catalog_ids TEXT,
                brand_ids TEXT,
                size_ids TEXT,
                material_ids TEXT,
                color_ids TEXT,
                status_ids TEXT,
                price_from REAL,
                price_to REAL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS notified_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(alert_id, item_id),
                FOREIGN KEY (alert_id) REFERENCES alerts(id) ON DELETE CASCADE
            )
        """)

        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON alerts(user_id)
        """)

        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_notified_items_alert_id ON notified_items(alert_id)
        """)

        await self._connection.commit()

    async def add_user(self, user_id: int, username: Optional[str] = None, first_name: Optional[str] = None) -> None:
        """Añade o actualiza un usuario."""
        await self._connection.execute("""
            INSERT INTO users (id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
        """, (user_id, username, first_name))
        await self._connection.commit()

    async def add_alert(self, alert: Alert) -> int:
        """Añade una nueva alerta y devuelve su ID."""
        cursor = await self._connection.execute("""
            INSERT INTO alerts (user_id, name, query, catalog_ids, brand_ids, size_ids,
                              material_ids, color_ids, status_ids, price_from, price_to, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            alert.user_id, alert.name, alert.query, alert.catalog_ids, alert.brand_ids,
            alert.size_ids, alert.material_ids, alert.color_ids, alert.status_ids,
            alert.price_from, alert.price_to, 1 if alert.is_active else 0
        ))
        await self._connection.commit()
        return cursor.lastrowid

    async def get_alerts_by_user(self, user_id: int) -> list[Alert]:
        """Obtiene todas las alertas de un usuario."""
        cursor = await self._connection.execute("""
            SELECT id, user_id, name, query, catalog_ids, brand_ids, size_ids,
                   material_ids, color_ids, status_ids, price_from, price_to, is_active
            FROM alerts WHERE user_id = ?
        """, (user_id,))
        rows = await cursor.fetchall()
        return [Alert(
            id=row[0], user_id=row[1], name=row[2], query=row[3],
            catalog_ids=row[4], brand_ids=row[5], size_ids=row[6],
            material_ids=row[7], color_ids=row[8], status_ids=row[9],
            price_from=row[10], price_to=row[11], is_active=bool(row[12])
        ) for row in rows]

    async def get_all_active_alerts(self) -> list[Alert]:
        """Obtiene todas las alertas activas."""
        cursor = await self._connection.execute("""
            SELECT id, user_id, name, query, catalog_ids, brand_ids, size_ids,
                   material_ids, color_ids, status_ids, price_from, price_to, is_active
            FROM alerts WHERE is_active = 1
        """)
        rows = await cursor.fetchall()
        return [Alert(
            id=row[0], user_id=row[1], name=row[2], query=row[3],
            catalog_ids=row[4], brand_ids=row[5], size_ids=row[6],
            material_ids=row[7], color_ids=row[8], status_ids=row[9],
            price_from=row[10], price_to=row[11], is_active=bool(row[12])
        ) for row in rows]

    async def get_alert_by_id(self, alert_id: int) -> Optional[Alert]:
        """Obtiene una alerta por su ID."""
        cursor = await self._connection.execute("""
            SELECT id, user_id, name, query, catalog_ids, brand_ids, size_ids,
                   material_ids, color_ids, status_ids, price_from, price_to, is_active
            FROM alerts WHERE id = ?
        """, (alert_id,))
        row = await cursor.fetchone()
        if row:
            return Alert(
                id=row[0], user_id=row[1], name=row[2], query=row[3],
                catalog_ids=row[4], brand_ids=row[5], size_ids=row[6],
                material_ids=row[7], color_ids=row[8], status_ids=row[9],
                price_from=row[10], price_to=row[11], is_active=bool(row[12])
            )
        return None

    async def toggle_alert(self, alert_id: int) -> bool:
        """Activa/desactiva una alerta. Devuelve el nuevo estado."""
        cursor = await self._connection.execute("""
            UPDATE alerts SET is_active = NOT is_active WHERE id = ?
        """, (alert_id,))
        await self._connection.commit()

        cursor = await self._connection.execute("""
            SELECT is_active FROM alerts WHERE id = ?
        """, (alert_id,))
        row = await cursor.fetchone()
        return bool(row[0]) if row else False

    async def delete_alert(self, alert_id: int) -> bool:
        """Elimina una alerta."""
        cursor = await self._connection.execute("""
            DELETE FROM alerts WHERE id = ?
        """, (alert_id,))
        await self._connection.commit()
        return cursor.rowcount > 0

    async def is_item_notified(self, alert_id: int, item_id: int) -> bool:
        """Comprueba si un artículo ya fue notificado para una alerta."""
        cursor = await self._connection.execute("""
            SELECT 1 FROM notified_items WHERE alert_id = ? AND item_id = ?
        """, (alert_id, item_id))
        return await cursor.fetchone() is not None

    async def mark_item_notified(self, alert_id: int, item_id: int) -> None:
        """Marca un artículo como notificado para una alerta."""
        await self._connection.execute("""
            INSERT OR IGNORE INTO notified_items (alert_id, item_id)
            VALUES (?, ?)
        """, (alert_id, item_id))
        await self._connection.commit()

    async def cleanup_old_notifications(self, days: int = 7) -> int:
        """Limpia notificaciones antiguas para mantener la base de datos pequeña."""
        cursor = await self._connection.execute("""
            DELETE FROM notified_items
            WHERE notified_at < datetime('now', ?)
        """, (f'-{days} days',))
        await self._connection.commit()
        return cursor.rowcount

    async def close(self) -> None:
        """Cierra la conexión a la base de datos."""
        if self._connection:
            await self._connection.close()
