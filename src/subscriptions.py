"""
Sistema de suscripciones y planes para el bot.
"""
import logging
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class PlanType(Enum):
    """Tipos de planes disponibles."""
    FREE = "free"
    PRO = "pro"
    PREMIUM = "premium"


@dataclass
class Plan:
    """Configuración de un plan de suscripción."""
    type: PlanType
    name: str
    max_alerts: int
    scan_interval: int  # segundos
    sniper_mode: bool
    daily_summary: bool
    price_alerts: bool
    advanced_filters: bool
    statistics: bool
    priority_notifications: bool
    price_monthly: float  # EUR
    price_yearly: float  # EUR

    def to_display_string(self) -> str:
        """Genera descripción del plan para mostrar."""
        features = []
        features.append(f"📊 Máximo {self.max_alerts} alertas" if self.max_alerts > 0 else "📊 Alertas ilimitadas")
        features.append(f"⏱️ Escaneo cada {self.scan_interval} segundos")

        if self.sniper_mode:
            features.append("🎯 Modo Sniper activado")
        if self.daily_summary:
            features.append("📬 Resúmenes diarios")
        if self.price_alerts:
            features.append("💰 Alertas de bajada de precio")
        if self.advanced_filters:
            features.append("🔍 Filtros avanzados")
        if self.statistics:
            features.append("📈 Estadísticas detalladas")
        if self.priority_notifications:
            features.append("🔔 Notificaciones prioritarias")

        return "\n".join(features)


# Definición de planes
PLANS = {
    PlanType.FREE: Plan(
        type=PlanType.FREE,
        name="Gratuito",
        max_alerts=2,
        scan_interval=300,  # 5 minutos
        sniper_mode=False,
        daily_summary=False,
        price_alerts=False,
        advanced_filters=False,
        statistics=False,
        priority_notifications=False,
        price_monthly=0,
        price_yearly=0,
    ),
    PlanType.PRO: Plan(
        type=PlanType.PRO,
        name="Pro",
        max_alerts=10,
        scan_interval=60,  # 1 minuto
        sniper_mode=True,
        daily_summary=True,
        price_alerts=True,
        advanced_filters=True,
        statistics=False,
        priority_notifications=True,
        price_monthly=4.99,
        price_yearly=49.99,
    ),
    PlanType.PREMIUM: Plan(
        type=PlanType.PREMIUM,
        name="Premium",
        max_alerts=-1,  # Ilimitado
        scan_interval=30,  # 30 segundos
        sniper_mode=True,
        daily_summary=True,
        price_alerts=True,
        advanced_filters=True,
        statistics=True,
        priority_notifications=True,
        price_monthly=9.99,
        price_yearly=99.99,
    ),
}


@dataclass
class Subscription:
    """Representa la suscripción de un usuario."""
    user_id: int
    plan_type: PlanType
    started_at: datetime
    expires_at: Optional[datetime]
    is_active: bool
    payment_id: Optional[str] = None

    @property
    def plan(self) -> Plan:
        """Obtiene el plan asociado."""
        return PLANS[self.plan_type]

    @property
    def is_expired(self) -> bool:
        """Verifica si la suscripción ha expirado."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    @property
    def days_remaining(self) -> int:
        """Días restantes de suscripción."""
        if self.expires_at is None:
            return -1  # Infinito
        delta = self.expires_at - datetime.now()
        return max(0, delta.days)


class SubscriptionManager:
    """Gestiona las suscripciones de usuarios."""

    def __init__(self, database):
        self.db = database

    async def setup_tables(self) -> None:
        """Crea las tablas necesarias para suscripciones."""
        await self.db._connection.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER PRIMARY KEY,
                plan_type TEXT NOT NULL DEFAULT 'free',
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                payment_id TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        await self.db._connection.execute("""
            CREATE TABLE IF NOT EXISTS payment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                currency TEXT DEFAULT 'EUR',
                plan_type TEXT NOT NULL,
                payment_method TEXT,
                payment_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        await self.db._connection.commit()

    async def get_subscription(self, user_id: int) -> Subscription:
        """Obtiene la suscripción de un usuario (o crea una gratuita)."""
        cursor = await self.db._connection.execute("""
            SELECT user_id, plan_type, started_at, expires_at, is_active, payment_id
            FROM subscriptions WHERE user_id = ?
        """, (user_id,))
        row = await cursor.fetchone()

        if row:
            return Subscription(
                user_id=row[0],
                plan_type=PlanType(row[1]),
                started_at=datetime.fromisoformat(row[2]) if row[2] else datetime.now(),
                expires_at=datetime.fromisoformat(row[3]) if row[3] else None,
                is_active=bool(row[4]),
                payment_id=row[5],
            )

        # Crear suscripción gratuita por defecto
        return await self.create_free_subscription(user_id)

    async def create_free_subscription(self, user_id: int) -> Subscription:
        """Crea una suscripción gratuita para un usuario."""
        now = datetime.now()
        await self.db._connection.execute("""
            INSERT OR REPLACE INTO subscriptions (user_id, plan_type, started_at, is_active)
            VALUES (?, 'free', ?, 1)
        """, (user_id, now.isoformat()))
        await self.db._connection.commit()

        return Subscription(
            user_id=user_id,
            plan_type=PlanType.FREE,
            started_at=now,
            expires_at=None,
            is_active=True,
        )

    async def upgrade_subscription(
        self,
        user_id: int,
        plan_type: PlanType,
        months: int = 1,
        payment_id: Optional[str] = None,
    ) -> Subscription:
        """Actualiza la suscripción de un usuario."""
        now = datetime.now()
        expires_at = now + timedelta(days=30 * months)

        await self.db._connection.execute("""
            INSERT OR REPLACE INTO subscriptions
            (user_id, plan_type, started_at, expires_at, is_active, payment_id)
            VALUES (?, ?, ?, ?, 1, ?)
        """, (user_id, plan_type.value, now.isoformat(), expires_at.isoformat(), payment_id))
        await self.db._connection.commit()

        return Subscription(
            user_id=user_id,
            plan_type=plan_type,
            started_at=now,
            expires_at=expires_at,
            is_active=True,
            payment_id=payment_id,
        )

    async def cancel_subscription(self, user_id: int) -> bool:
        """Cancela la suscripción (la mantiene activa hasta que expire)."""
        await self.db._connection.execute("""
            UPDATE subscriptions SET is_active = 0 WHERE user_id = ?
        """, (user_id,))
        await self.db._connection.commit()
        return True

    async def check_can_create_alert(self, user_id: int, current_alerts: int) -> tuple[bool, str]:
        """Verifica si el usuario puede crear más alertas."""
        sub = await self.get_subscription(user_id)
        plan = sub.plan

        if sub.is_expired:
            return False, "Tu suscripción ha expirado. Renueva para seguir creando alertas."

        if plan.max_alerts != -1 and current_alerts >= plan.max_alerts:
            return False, f"Has alcanzado el límite de {plan.max_alerts} alertas del plan {plan.name}. Actualiza tu plan para crear más."

        return True, ""

    async def get_user_scan_interval(self, user_id: int) -> int:
        """Obtiene el intervalo de escaneo según el plan del usuario."""
        sub = await self.get_subscription(user_id)
        if sub.is_expired:
            return PLANS[PlanType.FREE].scan_interval
        return sub.plan.scan_interval

    async def record_payment(
        self,
        user_id: int,
        amount: float,
        plan_type: PlanType,
        payment_method: str,
        payment_id: str,
        status: str = "completed",
    ) -> None:
        """Registra un pago en el historial."""
        await self.db._connection.execute("""
            INSERT INTO payment_history
            (user_id, amount, plan_type, payment_method, payment_id, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, amount, plan_type.value, payment_method, payment_id, status))
        await self.db._connection.commit()

    async def get_expiring_subscriptions(self, days: int = 3) -> list[Subscription]:
        """Obtiene suscripciones que expiran pronto."""
        threshold = (datetime.now() + timedelta(days=days)).isoformat()
        cursor = await self.db._connection.execute("""
            SELECT user_id, plan_type, started_at, expires_at, is_active, payment_id
            FROM subscriptions
            WHERE expires_at IS NOT NULL
            AND expires_at <= ?
            AND is_active = 1
            AND plan_type != 'free'
        """, (threshold,))
        rows = await cursor.fetchall()

        return [Subscription(
            user_id=row[0],
            plan_type=PlanType(row[1]),
            started_at=datetime.fromisoformat(row[2]) if row[2] else datetime.now(),
            expires_at=datetime.fromisoformat(row[3]) if row[3] else None,
            is_active=bool(row[4]),
            payment_id=row[5],
        ) for row in rows]
