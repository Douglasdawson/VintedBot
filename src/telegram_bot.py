"""
Bot de Telegram para gestionar alertas de Vinted.
Versión Premium con todas las funcionalidades.
"""
import json
import logging
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from .database import Database, Alert
from .subscriptions import SubscriptionManager, PlanType, PLANS
from .ai_assistant import AIAssistant

logger = logging.getLogger(__name__)

# Estados de la conversación para crear alertas
(
    ALERT_NAME,
    ALERT_QUERY,
    ALERT_PRICE_FROM,
    ALERT_PRICE_TO,
    ALERT_CATEGORIES,
    ALERT_BRANDS,
    ALERT_SIZES,
    ALERT_STATUS,
    ALERT_COLORS,
    ALERT_ADVANCED,
    ALERT_CONFIRM,
) = range(11)

# Diccionario para almacenar datos temporales de alertas en creación
user_alert_data: dict[int, dict] = {}

# Categorías principales de Vinted
CATEGORIES = {
    "Mujer": {
        "Ropa": 1904,
        "Zapatos": 16,
        "Bolsos": 11,
        "Accesorios": 1187,
    },
    "Hombre": {
        "Ropa": 2050,
        "Zapatos": 1231,
        "Bolsos": 1938,
        "Accesorios": 1939,
    },
    "Niños": {
        "Niña": 1193,
        "Niño": 1194,
        "Bebé": 1195,
    },
    "Hogar": {
        "Decoración": 1768,
        "Textil": 1769,
    },
    "Entretenimiento": {
        "Libros": 73,
        "Juegos": 1775,
        "Música": 76,
    },
}

# Estados del producto
PRODUCT_STATUS = {
    "Nuevo con etiquetas": 6,
    "Nuevo sin etiquetas": 1,
    "Muy bueno": 2,
    "Bueno": 3,
    "Satisfactorio": 4,
}

# Colores principales
COLORS = {
    "Negro": 1,
    "Gris": 3,
    "Blanco": 12,
    "Beige": 4,
    "Rojo": 7,
    "Rosa": 5,
    "Naranja": 11,
    "Amarillo": 10,
    "Verde": 9,
    "Azul": 2,
    "Morado": 6,
    "Marrón": 8,
    "Multicolor": 13,
}


class TelegramBot:
    """Gestiona el bot de Telegram."""

    def __init__(self, token: str, database: Database):
        self.token = token
        self.db = database
        self.application: Optional[Application] = None
        self.subscription_manager: Optional[SubscriptionManager] = None
        self.notification_manager = None
        self.statistics_manager = None
        self.ai_assistant: Optional[AIAssistant] = None

    def setup(self) -> Application:
        """Configura y devuelve la aplicación del bot."""
        self.application = Application.builder().token(self.token).build()
        self.subscription_manager = SubscriptionManager(self.db)

        # Handler para crear alertas (conversación)
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("nueva", self.cmd_new_alert)],
            states={
                ALERT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.alert_name)],
                ALERT_QUERY: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.alert_query),
                    CallbackQueryHandler(self.alert_skip_query, pattern="^skip_query$"),
                ],
                ALERT_PRICE_FROM: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.alert_price_from),
                    CallbackQueryHandler(self.alert_skip_price_from, pattern="^skip_price_from$"),
                ],
                ALERT_PRICE_TO: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.alert_price_to),
                    CallbackQueryHandler(self.alert_skip_price_to, pattern="^skip_price_to$"),
                ],
                ALERT_CATEGORIES: [
                    CallbackQueryHandler(self.alert_categories, pattern="^cat_"),
                    CallbackQueryHandler(self.alert_skip_categories, pattern="^skip_categories$"),
                ],
                ALERT_STATUS: [
                    CallbackQueryHandler(self.alert_status, pattern="^status_"),
                    CallbackQueryHandler(self.alert_skip_status, pattern="^skip_status$"),
                ],
                ALERT_COLORS: [
                    CallbackQueryHandler(self.alert_colors, pattern="^color_"),
                    CallbackQueryHandler(self.alert_skip_colors, pattern="^skip_colors$"),
                ],
                ALERT_ADVANCED: [
                    CallbackQueryHandler(self.alert_advanced, pattern="^adv_"),
                    CallbackQueryHandler(self.alert_skip_advanced, pattern="^skip_advanced$"),
                ],
                ALERT_CONFIRM: [
                    CallbackQueryHandler(self.alert_confirm, pattern="^confirm_"),
                ],
            },
            fallbacks=[CommandHandler("cancelar", self.cmd_cancel)],
        )

        # Registrar handlers
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("ayuda", self.cmd_help))
        self.application.add_handler(CommandHandler("alertas", self.cmd_list_alerts))
        self.application.add_handler(CommandHandler("plan", self.cmd_plan))
        self.application.add_handler(CommandHandler("planes", self.cmd_plans))
        self.application.add_handler(CommandHandler("stats", self.cmd_stats))
        self.application.add_handler(CommandHandler("config", self.cmd_config))
        self.application.add_handler(CommandHandler("sniper", self.cmd_sniper))

        # Comandos de IA
        self.application.add_handler(CommandHandler("buscar", self.cmd_ai_search))
        self.application.add_handler(CommandHandler("analizar", self.cmd_ai_analyze))
        self.application.add_handler(CommandHandler("chat", self.cmd_ai_chat))

        self.application.add_handler(conv_handler)
        self.application.add_handler(CallbackQueryHandler(self.callback_handler))

        # Handler para mensajes de texto (IA conversacional)
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message)
        )

        return self.application

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /start - Bienvenida al usuario."""
        user = update.effective_user
        await self.db.add_user(user.id, user.username, user.first_name)

        # Crear suscripción gratuita si no existe
        await self.subscription_manager.setup_tables()
        await self.subscription_manager.create_free_subscription(user.id)

        welcome_text = f"""
Hola {user.first_name}! Bienvenido al Bot de Alertas de Vinted.

Con este bot podrás:
- Crear alertas con lenguaje natural usando IA
- Recibir notificaciones instantáneas de nuevos productos
- Analizar si un producto es un chollo
- Detectar posibles defectos o falsificaciones
- Ver estadísticas y análisis de precios

*Comandos principales:*
/nueva - Crear alerta paso a paso
/buscar - Crear alerta con IA (ej: /buscar Nike Air Max negras talla 42)
/alertas - Ver y gestionar alertas
/analizar - Analizar un producto

*Más opciones:*
/plan /planes /stats /config /sniper /ayuda

O simplemente escríbeme lo que buscas y te ayudo.
        """
        await update.message.reply_text(welcome_text, parse_mode="Markdown")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /ayuda - Muestra ayuda detallada."""
        help_text = """
*Guía de uso del Bot de Vinted*

*Crear alertas con IA:*
Usa /buscar seguido de lo que buscas:
`/buscar zapatillas Nike negras talla 42 menos de 50€`

La IA interpretará tu búsqueda y creará la alerta.

*Crear alertas manual:*
Usa /nueva para crear una alerta paso a paso.

*Analizar productos:*
- /analizar [URL] - Analiza si es chollo y detecta defectos
- Envía una URL de Vinted para análisis automático

*Asistente IA:*
Escríbeme cualquier pregunta sobre Vinted o dime qué buscas.
Ejemplo: "Busco una chaqueta de invierno barata"

*Gestionar alertas:*
Usa /alertas para:
- Ver todas tus alertas
- Pausar/Activar alertas
- Eliminar alertas

*Planes:*
- /plan - Ver tu plan actual
- /planes - Ver planes y precios

*Funciones Premium:*
- /sniper - Modo sniper (escaneo cada 30s)
- /stats - Estadísticas detalladas
- /config - Configurar notificaciones
  - Resúmenes diarios
  - Alertas de bajada de precio
  - Horas de silencio

*Tips:*
- Sé específico en las búsquedas
- Usa filtros avanzados para mejores resultados
- Activa modo sniper para chollos
        """
        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def cmd_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /plan - Muestra el plan actual del usuario."""
        user_id = update.effective_user.id
        sub = await self.subscription_manager.get_subscription(user_id)
        plan = sub.plan

        message = f"*Tu Plan: {plan.name}*\n\n"
        message += plan.to_display_string()

        if sub.expires_at:
            message += f"\n\n📅 Expira: {sub.expires_at.strftime('%d/%m/%Y')}"
            message += f"\n⏳ Días restantes: {sub.days_remaining}"

        if plan.type != PlanType.PREMIUM:
            message += "\n\n_Actualiza tu plan para desbloquear más funciones_"
            keyboard = [[InlineKeyboardButton("📈 Ver planes", callback_data="show_plans")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)
        else:
            await update.message.reply_text(message, parse_mode="Markdown")

    async def cmd_plans(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /planes - Muestra los planes disponibles."""
        message = "*Planes Disponibles*\n\n"

        for plan_type, plan in PLANS.items():
            emoji = "🆓" if plan_type == PlanType.FREE else "⭐" if plan_type == PlanType.PRO else "💎"
            message += f"{emoji} *{plan.name}*\n"
            if plan.price_monthly > 0:
                message += f"💰 {plan.price_monthly}€/mes o {plan.price_yearly}€/año\n"
            else:
                message += "💰 Gratis\n"
            message += f"📊 {plan.max_alerts if plan.max_alerts > 0 else '∞'} alertas\n"
            message += f"⏱️ Escaneo cada {plan.scan_interval}s\n"
            features = []
            if plan.sniper_mode:
                features.append("Sniper")
            if plan.daily_summary:
                features.append("Resúmenes")
            if plan.price_alerts:
                features.append("Alertas precio")
            if plan.statistics:
                features.append("Estadísticas")
            if features:
                message += f"✨ {', '.join(features)}\n"
            message += "\n"

        keyboard = [
            [InlineKeyboardButton("⭐ Obtener Pro", callback_data="upgrade_pro")],
            [InlineKeyboardButton("💎 Obtener Premium", callback_data="upgrade_premium")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)

    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /stats - Muestra estadísticas del usuario."""
        user_id = update.effective_user.id

        # Verificar si tiene acceso a estadísticas
        sub = await self.subscription_manager.get_subscription(user_id)
        if not sub.plan.statistics and sub.plan.type != PlanType.FREE:
            await update.message.reply_text(
                "📊 Las estadísticas detalladas están disponibles en el plan Premium.\n"
                "Usa /planes para ver las opciones."
            )
            return

        # Estadísticas básicas para todos
        alerts = await self.db.get_alerts_by_user(user_id)
        active_alerts = len([a for a in alerts if a.is_active])

        message = "*📊 Tus Estadísticas*\n\n"
        message += f"📋 Total de alertas: {len(alerts)}\n"
        message += f"✅ Alertas activas: {active_alerts}\n"
        message += f"📦 Plan actual: {sub.plan.name}\n"

        if self.statistics_manager and sub.plan.statistics:
            stats = await self.statistics_manager.get_user_stats(user_id)
            message += f"\n*Notificaciones:*\n"
            message += f"📬 Total: {stats.total_notifications}\n"
            message += f"📅 Hoy: {stats.notifications_today}\n"
            message += f"📆 Esta semana: {stats.notifications_this_week}\n"
            message += f"📆 Este mes: {stats.notifications_this_month}\n"

            if stats.avg_price_found > 0:
                message += f"\n*Precios encontrados:*\n"
                message += f"📊 Promedio: {stats.avg_price_found}€\n"
                message += f"⬇️ Mínimo: {stats.min_price_found}€\n"
                message += f"⬆️ Máximo: {stats.max_price_found}€\n"

            if stats.most_active_alert:
                message += f"\n🏆 Alerta más activa: {stats.most_active_alert}"

        await update.message.reply_text(message, parse_mode="Markdown")

    async def cmd_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /config - Configura las notificaciones."""
        user_id = update.effective_user.id

        if not self.notification_manager:
            await update.message.reply_text("Configuración no disponible en este momento.")
            return

        prefs = await self.notification_manager.get_preferences(user_id)

        message = "*⚙️ Configuración de Notificaciones*\n\n"

        keyboard = [
            [InlineKeyboardButton(
                f"{'✅' if prefs['daily_summary_enabled'] else '❌'} Resumen diario",
                callback_data="config_toggle_summary"
            )],
            [InlineKeyboardButton(
                f"{'✅' if prefs['price_drop_enabled'] else '❌'} Alertas bajada precio",
                callback_data="config_toggle_pricedrop"
            )],
            [InlineKeyboardButton(
                f"{'✅' if prefs['sniper_mode_enabled'] else '❌'} Modo Sniper",
                callback_data="config_toggle_sniper"
            )],
            [InlineKeyboardButton(
                f"🕐 Hora resumen: {prefs['daily_summary_hour']}:00",
                callback_data="config_summary_hour"
            )],
            [InlineKeyboardButton(
                f"📉 Umbral bajada: {prefs['price_drop_threshold']}%",
                callback_data="config_drop_threshold"
            )],
        ]

        if prefs['quiet_hours_start'] is not None:
            quiet = f"{prefs['quiet_hours_start']}:00 - {prefs['quiet_hours_end']}:00"
        else:
            quiet = "No configuradas"
        keyboard.append([InlineKeyboardButton(f"🌙 Horas silencio: {quiet}", callback_data="config_quiet_hours")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)

    async def cmd_sniper(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /sniper - Activa/desactiva modo sniper."""
        user_id = update.effective_user.id

        # Verificar plan
        sub = await self.subscription_manager.get_subscription(user_id)
        if not sub.plan.sniper_mode:
            await update.message.reply_text(
                "🎯 El modo Sniper está disponible en los planes Pro y Premium.\n"
                "Usa /planes para ver las opciones."
            )
            return

        if self.notification_manager:
            prefs = await self.notification_manager.get_preferences(user_id)
            new_status = not prefs.get("sniper_mode_enabled", False)
            await self.notification_manager.update_preferences(user_id, sniper_mode_enabled=new_status)

            if new_status:
                await update.message.reply_text(
                    "🎯 *Modo Sniper ACTIVADO*\n\n"
                    "Tus alertas ahora se escanean cada 30 segundos.\n"
                    "Recibirás notificaciones prioritarias de nuevos productos.\n\n"
                    "Usa /sniper de nuevo para desactivar.",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    "🎯 Modo Sniper desactivado.\n"
                    "Tus alertas volverán al intervalo normal de escaneo."
                )
        else:
            await update.message.reply_text("Modo sniper no disponible en este momento.")

    async def cmd_list_alerts(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /alertas - Lista las alertas del usuario."""
        user_id = update.effective_user.id
        alerts = await self.db.get_alerts_by_user(user_id)

        if not alerts:
            await update.message.reply_text(
                "No tienes alertas configuradas.\nUsa /nueva para crear una."
            )
            return

        # Info del plan
        sub = await self.subscription_manager.get_subscription(user_id)
        plan = sub.plan
        limit_text = f" ({len(alerts)}/{plan.max_alerts})" if plan.max_alerts > 0 else ""

        text = f"*Tus alertas{limit_text}:*\n\n"
        keyboard = []

        for alert in alerts:
            status_emoji = "✅" if alert.is_active else "⏸️"
            text += f"{status_emoji} *{alert.name}*\n"
            if alert.query:
                text += f"   Búsqueda: _{alert.query}_\n"
            if alert.price_from or alert.price_to:
                price_text = f"   Precio: {alert.price_from or 0}€ - {alert.price_to or '∞'}€\n"
                text += price_text
            text += "\n"

            # Botones para cada alerta
            keyboard.append([
                InlineKeyboardButton(
                    f"{'⏸️' if alert.is_active else '▶️'} {alert.name[:15]}",
                    callback_data=f"toggle_{alert.id}"
                ),
                InlineKeyboardButton("📊", callback_data=f"stats_{alert.id}"),
                InlineKeyboardButton("🗑️", callback_data=f"delete_{alert.id}")
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

    async def cmd_new_alert(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Inicia el proceso de creación de una nueva alerta."""
        user_id = update.effective_user.id

        # Verificar límite de alertas
        alerts = await self.db.get_alerts_by_user(user_id)
        can_create, message = await self.subscription_manager.check_can_create_alert(user_id, len(alerts))

        if not can_create:
            await update.message.reply_text(f"⚠️ {message}\nUsa /planes para ver las opciones.")
            return ConversationHandler.END

        user_alert_data[user_id] = {}

        await update.message.reply_text(
            "*Nueva Alerta*\n\n"
            "Vamos a crear una nueva alerta paso a paso.\n\n"
            "Primero, escribe un *nombre* para identificar esta alerta:\n"
            "_Ejemplo: Zapatillas Nike baratas_",
            parse_mode="Markdown"
        )
        return ALERT_NAME

    async def alert_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Guarda el nombre de la alerta."""
        user_id = update.effective_user.id
        user_alert_data[user_id]["name"] = update.message.text

        keyboard = [[InlineKeyboardButton("⏭️ Omitir", callback_data="skip_query")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "*Palabras clave de búsqueda*\n\n"
            "Escribe las palabras clave para buscar:\n"
            "_Ejemplo: Nike Air Max_\n\n"
            "O pulsa Omitir para buscar en toda la categoría.",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return ALERT_QUERY

    async def alert_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Guarda la query de búsqueda."""
        user_id = update.effective_user.id
        user_alert_data[user_id]["query"] = update.message.text
        return await self._ask_price_from(update)

    async def alert_skip_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Omite la query de búsqueda."""
        await update.callback_query.answer()
        user_id = update.effective_user.id
        user_alert_data[user_id]["query"] = None
        return await self._ask_price_from(update)

    async def _ask_price_from(self, update: Update) -> int:
        """Pregunta por el precio mínimo."""
        keyboard = [[InlineKeyboardButton("⏭️ Sin mínimo", callback_data="skip_price_from")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message = update.callback_query.message if update.callback_query else update.message
        await message.reply_text(
            "*Precio mínimo*\n\n"
            "Escribe el precio mínimo en euros:\n"
            "_Ejemplo: 10_",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return ALERT_PRICE_FROM

    async def alert_price_from(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Guarda el precio mínimo."""
        user_id = update.effective_user.id
        try:
            price = float(update.message.text.replace(",", ".").replace("€", "").strip())
            user_alert_data[user_id]["price_from"] = price
        except ValueError:
            await update.message.reply_text("Por favor, introduce un número válido.")
            return ALERT_PRICE_FROM
        return await self._ask_price_to(update)

    async def alert_skip_price_from(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Omite el precio mínimo."""
        await update.callback_query.answer()
        user_id = update.effective_user.id
        user_alert_data[user_id]["price_from"] = None
        return await self._ask_price_to(update)

    async def _ask_price_to(self, update: Update) -> int:
        """Pregunta por el precio máximo."""
        keyboard = [[InlineKeyboardButton("⏭️ Sin máximo", callback_data="skip_price_to")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message = update.callback_query.message if update.callback_query else update.message
        await message.reply_text(
            "*Precio máximo*\n\n"
            "Escribe el precio máximo en euros:\n"
            "_Ejemplo: 50_",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return ALERT_PRICE_TO

    async def alert_price_to(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Guarda el precio máximo."""
        user_id = update.effective_user.id
        try:
            price = float(update.message.text.replace(",", ".").replace("€", "").strip())
            user_alert_data[user_id]["price_to"] = price
        except ValueError:
            await update.message.reply_text("Por favor, introduce un número válido.")
            return ALERT_PRICE_TO
        return await self._ask_categories(update)

    async def alert_skip_price_to(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Omite el precio máximo."""
        await update.callback_query.answer()
        user_id = update.effective_user.id
        user_alert_data[user_id]["price_to"] = None
        return await self._ask_categories(update)

    async def _ask_categories(self, update: Update) -> int:
        """Pregunta por las categorías."""
        keyboard = []
        for main_cat, subcats in CATEGORIES.items():
            row = []
            for subcat_name, subcat_id in subcats.items():
                row.append(InlineKeyboardButton(
                    f"{main_cat}: {subcat_name}",
                    callback_data=f"cat_{subcat_id}"
                ))
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)

        keyboard.append([InlineKeyboardButton("⏭️ Todas las categorías", callback_data="skip_categories")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        message = update.callback_query.message if update.callback_query else update.message
        await message.reply_text(
            "*Categoría*\n\n"
            "Selecciona una categoría o pulsa para buscar en todas:",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return ALERT_CATEGORIES

    async def alert_categories(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Guarda la categoría seleccionada."""
        await update.callback_query.answer()
        user_id = update.effective_user.id
        cat_id = int(update.callback_query.data.split("_")[1])
        user_alert_data[user_id]["catalog_ids"] = [cat_id]
        return await self._ask_status(update)

    async def alert_skip_categories(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Omite las categorías."""
        await update.callback_query.answer()
        user_id = update.effective_user.id
        user_alert_data[user_id]["catalog_ids"] = None
        return await self._ask_status(update)

    async def _ask_status(self, update: Update) -> int:
        """Pregunta por el estado del producto."""
        keyboard = []
        for status_name, status_id in PRODUCT_STATUS.items():
            keyboard.append([InlineKeyboardButton(status_name, callback_data=f"status_{status_id}")])
        keyboard.append([InlineKeyboardButton("⏭️ Cualquier estado", callback_data="skip_status")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.callback_query.message.reply_text(
            "*Estado del producto*\n\n"
            "Selecciona el estado deseado:",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return ALERT_STATUS

    async def alert_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Guarda el estado seleccionado."""
        await update.callback_query.answer()
        user_id = update.effective_user.id
        status_id = int(update.callback_query.data.split("_")[1])
        user_alert_data[user_id]["status_ids"] = [status_id]
        return await self._ask_colors(update)

    async def alert_skip_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Omite el estado."""
        await update.callback_query.answer()
        user_id = update.effective_user.id
        user_alert_data[user_id]["status_ids"] = None
        return await self._ask_colors(update)

    async def _ask_colors(self, update: Update) -> int:
        """Pregunta por los colores."""
        keyboard = []
        row = []
        for color_name, color_id in COLORS.items():
            row.append(InlineKeyboardButton(color_name, callback_data=f"color_{color_id}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("⏭️ Cualquier color", callback_data="skip_colors")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.callback_query.message.reply_text(
            "*Color*\n\n"
            "Selecciona un color o cualquier color:",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return ALERT_COLORS

    async def alert_colors(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Guarda el color seleccionado."""
        await update.callback_query.answer()
        user_id = update.effective_user.id
        color_id = int(update.callback_query.data.split("_")[1])
        user_alert_data[user_id]["color_ids"] = [color_id]
        return await self._ask_advanced(update)

    async def alert_skip_colors(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Omite el color."""
        await update.callback_query.answer()
        user_id = update.effective_user.id
        user_alert_data[user_id]["color_ids"] = None
        return await self._ask_advanced(update)

    async def _ask_advanced(self, update: Update) -> int:
        """Pregunta por filtros avanzados."""
        user_id = update.effective_user.id

        # Verificar si tiene acceso a filtros avanzados
        sub = await self.subscription_manager.get_subscription(user_id)
        if not sub.plan.advanced_filters:
            return await self._show_confirm(update)

        keyboard = [
            [InlineKeyboardButton("✅ Solo vendedores verificados", callback_data="adv_verified")],
            [InlineKeyboardButton("📦 Solo envío gratis", callback_data="adv_freeship")],
            [InlineKeyboardButton("⭐ Reputación mínima 4.5", callback_data="adv_rating")],
            [InlineKeyboardButton("⏭️ Sin filtros avanzados", callback_data="skip_advanced")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.callback_query.message.reply_text(
            "*Filtros Avanzados* ⭐\n\n"
            "Selecciona filtros adicionales:",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return ALERT_ADVANCED

    async def alert_advanced(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Guarda filtros avanzados seleccionados."""
        await update.callback_query.answer()
        user_id = update.effective_user.id
        option = update.callback_query.data.split("_")[1]

        if "advanced_filters" not in user_alert_data[user_id]:
            user_alert_data[user_id]["advanced_filters"] = {}

        if option == "verified":
            user_alert_data[user_id]["advanced_filters"]["verified_seller_only"] = True
        elif option == "freeship":
            user_alert_data[user_id]["advanced_filters"]["free_shipping_only"] = True
        elif option == "rating":
            user_alert_data[user_id]["advanced_filters"]["min_seller_rating"] = 4.5

        return await self._show_confirm(update)

    async def alert_skip_advanced(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Omite filtros avanzados."""
        await update.callback_query.answer()
        return await self._show_confirm(update)

    async def _show_confirm(self, update: Update) -> int:
        """Muestra resumen y pide confirmación."""
        user_id = update.effective_user.id
        data = user_alert_data[user_id]

        summary = f"*Resumen de la alerta:*\n\n"
        summary += f"*Nombre:* {data.get('name', 'Sin nombre')}\n"
        if data.get("query"):
            summary += f"*Búsqueda:* {data['query']}\n"
        if data.get("price_from") or data.get("price_to"):
            summary += f"*Precio:* {data.get('price_from', 0)}€ - {data.get('price_to', '∞')}€\n"
        if data.get("catalog_ids"):
            summary += f"*Categoría:* Configurada\n"
        if data.get("status_ids"):
            summary += f"*Estado:* Configurado\n"
        if data.get("color_ids"):
            summary += f"*Color:* Configurado\n"
        if data.get("advanced_filters"):
            summary += f"*Filtros avanzados:* ✅\n"

        keyboard = [
            [
                InlineKeyboardButton("✅ Confirmar", callback_data="confirm_yes"),
                InlineKeyboardButton("❌ Cancelar", callback_data="confirm_no"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.callback_query.message.reply_text(
            summary + "\n¿Confirmas la creación de esta alerta?",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return ALERT_CONFIRM

    async def alert_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Confirma o cancela la creación de la alerta."""
        await update.callback_query.answer()
        user_id = update.effective_user.id
        action = update.callback_query.data.split("_")[1]

        if action == "yes":
            data = user_alert_data[user_id]
            advanced = data.get("advanced_filters", {})

            alert = Alert(
                id=None,
                user_id=user_id,
                name=data.get("name", "Alerta sin nombre"),
                query=data.get("query"),
                catalog_ids=json.dumps(data.get("catalog_ids")) if data.get("catalog_ids") else None,
                brand_ids=json.dumps(data.get("brand_ids")) if data.get("brand_ids") else None,
                size_ids=json.dumps(data.get("size_ids")) if data.get("size_ids") else None,
                material_ids=json.dumps(data.get("material_ids")) if data.get("material_ids") else None,
                color_ids=json.dumps(data.get("color_ids")) if data.get("color_ids") else None,
                status_ids=json.dumps(data.get("status_ids")) if data.get("status_ids") else None,
                price_from=data.get("price_from"),
                price_to=data.get("price_to"),
                is_active=True,
            )
            alert_id = await self.db.add_alert(alert)

            # Guardar filtros avanzados si existen
            if advanced:
                await self.db._connection.execute("""
                    CREATE TABLE IF NOT EXISTS alert_advanced_filters (
                        alert_id INTEGER PRIMARY KEY,
                        verified_seller_only INTEGER DEFAULT 0,
                        free_shipping_only INTEGER DEFAULT 0,
                        min_seller_rating REAL,
                        min_seller_reviews INTEGER,
                        excluded_sellers TEXT,
                        country_codes TEXT,
                        FOREIGN KEY (alert_id) REFERENCES alerts(id) ON DELETE CASCADE
                    )
                """)
                await self.db._connection.execute("""
                    INSERT OR REPLACE INTO alert_advanced_filters
                    (alert_id, verified_seller_only, free_shipping_only, min_seller_rating)
                    VALUES (?, ?, ?, ?)
                """, (
                    alert_id,
                    1 if advanced.get("verified_seller_only") else 0,
                    1 if advanced.get("free_shipping_only") else 0,
                    advanced.get("min_seller_rating"),
                ))
                await self.db._connection.commit()

            await update.callback_query.message.reply_text(
                f"✅ Alerta *{alert.name}* creada correctamente!\n\n"
                f"Recibirás notificaciones de nuevos productos que coincidan con tus criterios.\n"
                f"Usa /alertas para ver y gestionar tus alertas.",
                parse_mode="Markdown"
            )
        else:
            await update.callback_query.message.reply_text(
                "❌ Creación de alerta cancelada."
            )

        user_alert_data.pop(user_id, None)
        return ConversationHandler.END

    async def cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancela la operación actual."""
        user_id = update.effective_user.id
        user_alert_data.pop(user_id, None)
        await update.message.reply_text("Operación cancelada.")
        return ConversationHandler.END

    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Maneja callbacks de botones fuera de conversaciones."""
        query = update.callback_query
        await query.answer()

        data = query.data
        user_id = update.effective_user.id

        # Callbacks de IA
        if data.startswith("ai_confirm_"):
            if user_id in user_alert_data and user_alert_data[user_id].get("from_ai"):
                alert_data = user_alert_data[user_id]
                alert = Alert(
                    id=None,
                    user_id=user_id,
                    name=alert_data.get("name", "Alerta IA"),
                    query=alert_data.get("query"),
                    price_from=alert_data.get("price_from"),
                    price_to=alert_data.get("price_to"),
                    is_active=True,
                )
                await self.db.add_alert(alert)
                user_alert_data.pop(user_id, None)
                await query.message.reply_text(
                    f"✅ Alerta *{alert.name}* creada con IA!\n"
                    f"Usa /alertas para verla.",
                    parse_mode="Markdown"
                )
            else:
                await query.message.reply_text("❌ No hay datos de alerta pendientes.")
            return

        elif data == "ai_cancel":
            user_alert_data.pop(user_id, None)
            await query.message.reply_text("❌ Cancelado.")
            return

        elif data.startswith("toggle_"):
            alert_id = int(data.split("_")[1])
            new_status = await self.db.toggle_alert(alert_id)
            status_text = "activada" if new_status else "pausada"
            await query.message.reply_text(f"Alerta {status_text} correctamente.")

        elif data.startswith("delete_"):
            alert_id = int(data.split("_")[1])
            keyboard = [
                [
                    InlineKeyboardButton("✅ Sí, eliminar", callback_data=f"confirm_delete_{alert_id}"),
                    InlineKeyboardButton("❌ No", callback_data="cancel_delete"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(
                "¿Estás seguro de que quieres eliminar esta alerta?",
                reply_markup=reply_markup
            )

        elif data.startswith("confirm_delete_"):
            alert_id = int(data.split("_")[2])
            await self.db.delete_alert(alert_id)
            await query.message.reply_text("Alerta eliminada correctamente.")

        elif data == "cancel_delete":
            await query.message.reply_text("Eliminación cancelada.")

        elif data.startswith("stats_"):
            alert_id = int(data.split("_")[1])
            if self.statistics_manager:
                stats = await self.statistics_manager.get_alert_stats(alert_id)
                if stats:
                    message = f"*📊 Estadísticas: {stats.alert_name}*\n\n"
                    message += f"📬 Total matches: {stats.total_matches}\n"
                    message += f"📅 Hoy: {stats.matches_today}\n"
                    message += f"📆 Esta semana: {stats.matches_this_week}\n"
                    if stats.avg_price > 0:
                        message += f"\n💰 Precio promedio: {stats.avg_price}€\n"
                        message += f"⬇️ Mínimo: {stats.min_price}€\n"
                        message += f"⬆️ Máximo: {stats.max_price}€\n"
                    await query.message.reply_text(message, parse_mode="Markdown")
                else:
                    await query.message.reply_text("No hay estadísticas disponibles para esta alerta.")
            else:
                await query.message.reply_text("Estadísticas no disponibles.")

        elif data == "show_plans":
            # Mostrar planes
            await self.cmd_plans(update, context)

        elif data.startswith("upgrade_"):
            plan = data.split("_")[1]
            plan_type = PlanType.PRO if plan == "pro" else PlanType.PREMIUM
            plan_info = PLANS[plan_type]

            message = f"*Actualizar a {plan_info.name}*\n\n"
            message += f"💰 Precio: {plan_info.price_monthly}€/mes\n"
            message += f"💰 Anual: {plan_info.price_yearly}€/año (ahorra 2 meses)\n\n"
            message += "Para completar el pago, contacta con el administrador.\n"
            message += "_Sistema de pago automático próximamente._"

            await query.message.reply_text(message, parse_mode="Markdown")

        elif data.startswith("config_toggle_"):
            option = data.replace("config_toggle_", "")
            if self.notification_manager:
                prefs = await self.notification_manager.get_preferences(user_id)
                if option == "summary":
                    await self.notification_manager.update_preferences(
                        user_id, daily_summary_enabled=not prefs["daily_summary_enabled"]
                    )
                elif option == "pricedrop":
                    await self.notification_manager.update_preferences(
                        user_id, price_drop_enabled=not prefs["price_drop_enabled"]
                    )
                elif option == "sniper":
                    sub = await self.subscription_manager.get_subscription(user_id)
                    if sub.plan.sniper_mode:
                        await self.notification_manager.update_preferences(
                            user_id, sniper_mode_enabled=not prefs["sniper_mode_enabled"]
                        )
                    else:
                        await query.message.reply_text("Modo Sniper disponible en planes Pro y Premium.")
                        return

                await query.message.reply_text("✅ Configuración actualizada.")

    async def send_notification(self, user_id: int, item, alert_name: str) -> bool:
        """Envía una notificación de nuevo producto al usuario."""
        try:
            # Verificar horas de silencio
            if self.notification_manager:
                if await self.notification_manager.is_quiet_hours(user_id):
                    return False

            message = (
                f"🔔 *Nueva coincidencia para:* {alert_name}\n\n"
                f"*{item.title}*\n"
                f"💰 *Precio:* {item.price} {item.currency}\n"
            )
            if item.brand:
                message += f"🏷️ *Marca:* {item.brand}\n"
            if item.size:
                message += f"📏 *Talla:* {item.size}\n"
            message += f"👤 *Vendedor:* {item.user_login}\n"

            # Info adicional del vendedor si está disponible
            if item.user and item.user.feedback_reputation > 0:
                message += f"⭐ *Valoración:* {item.user.feedback_reputation:.1f} ({item.user.feedback_count} reseñas)\n"

            if item.free_shipping:
                message += f"📦 *Envío gratis*\n"

            message += f"\n🔗 [Ver en Vinted]({item.url})"

            if item.photo_url:
                await self.application.bot.send_photo(
                    chat_id=user_id,
                    photo=item.photo_url,
                    caption=message,
                    parse_mode="Markdown"
                )
            else:
                await self.application.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode="Markdown",
                    disable_web_page_preview=False
                )
            return True
        except Exception as e:
            logger.error(f"Error enviando notificación a {user_id}: {e}")
            return False

    # ==================== COMANDOS DE IA ====================

    async def cmd_ai_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /buscar - Crea una alerta usando lenguaje natural con IA."""
        user_id = update.effective_user.id

        if not self.ai_assistant or not self.ai_assistant.is_available:
            await update.message.reply_text(
                "🤖 El asistente de IA no está disponible.\n"
                "Usa /nueva para crear una alerta manualmente."
            )
            return

        # Obtener el texto después del comando
        if context.args:
            search_text = " ".join(context.args)
        else:
            await update.message.reply_text(
                "🔍 *Búsqueda con IA*\n\n"
                "Escribe qué buscas después del comando:\n"
                "`/buscar zapatillas Nike negras talla 42 menos de 50€`\n\n"
                "La IA interpretará tu búsqueda y creará la alerta automáticamente.",
                parse_mode="Markdown"
            )
            return

        await update.message.reply_text("🤖 Analizando tu búsqueda...")

        # Verificar límite de alertas
        alerts = await self.db.get_alerts_by_user(user_id)
        can_create, message = await self.subscription_manager.check_can_create_alert(user_id, len(alerts))
        if not can_create:
            await update.message.reply_text(f"⚠️ {message}")
            return

        # Parsear con IA
        parsed = await self.ai_assistant.parse_natural_language_alert(search_text)

        if not parsed or parsed.confidence < 0.3:
            await update.message.reply_text(
                "❌ No pude entender tu búsqueda.\n"
                "Intenta ser más específico o usa /nueva para crear la alerta manualmente."
            )
            return

        # Mostrar lo que entendió la IA
        summary = f"🤖 *Entendí esto:*\n\n"
        summary += f"*Nombre:* {parsed.name}\n"
        if parsed.query:
            summary += f"*Búsqueda:* {parsed.query}\n"
        if parsed.price_from or parsed.price_to:
            summary += f"*Precio:* {parsed.price_from or 0}€ - {parsed.price_to or '∞'}€\n"
        if parsed.brand:
            summary += f"*Marca:* {parsed.brand}\n"
        if parsed.size:
            summary += f"*Talla:* {parsed.size}\n"
        if parsed.color:
            summary += f"*Color:* {parsed.color}\n"
        if parsed.status:
            summary += f"*Estado:* {parsed.status}\n"

        summary += f"\n_Confianza: {int(parsed.confidence * 100)}%_"

        keyboard = [
            [
                InlineKeyboardButton("✅ Crear alerta", callback_data=f"ai_confirm_{user_id}"),
                InlineKeyboardButton("❌ Cancelar", callback_data="ai_cancel"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Guardar datos para confirmación
        user_alert_data[user_id] = {
            "name": parsed.name,
            "query": parsed.query,
            "price_from": parsed.price_from,
            "price_to": parsed.price_to,
            "from_ai": True,
        }

        await update.message.reply_text(summary, parse_mode="Markdown", reply_markup=reply_markup)

    async def cmd_ai_analyze(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /analizar - Analiza un producto de Vinted."""
        if not self.ai_assistant or not self.ai_assistant.is_available:
            await update.message.reply_text(
                "🤖 El asistente de IA no está disponible en este momento."
            )
            return

        # Verificar si hay URL
        if not context.args:
            await update.message.reply_text(
                "🔍 *Analizar producto*\n\n"
                "Envía una URL de Vinted para analizar:\n"
                "`/analizar https://www.vinted.es/items/123456`\n\n"
                "O simplemente pega la URL y la analizaré automáticamente.",
                parse_mode="Markdown"
            )
            return

        url = context.args[0]

        # Verificar que es una URL de Vinted
        if "vinted" not in url.lower():
            await update.message.reply_text("⚠️ Por favor, envía una URL válida de Vinted.")
            return

        await update.message.reply_text("🔍 Analizando producto...")

        # TODO: Implementar obtención de datos del producto desde la URL
        # Por ahora, mostramos un mensaje de ejemplo
        await update.message.reply_text(
            "🤖 *Análisis del producto*\n\n"
            "Para un análisis completo, necesito obtener los datos del producto.\n"
            "Esta función estará disponible próximamente.\n\n"
            "_Mientras tanto, puedo analizar productos que me envíes por notificación._",
            parse_mode="Markdown"
        )

    async def cmd_ai_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /chat - Inicia una conversación con el asistente IA."""
        if not self.ai_assistant or not self.ai_assistant.is_available:
            await update.message.reply_text(
                "🤖 El asistente de IA no está disponible en este momento."
            )
            return

        if context.args:
            question = " ".join(context.args)
            response = await self.ai_assistant.smart_chat_response(question)
            await update.message.reply_text(f"🤖 {response}")
        else:
            await update.message.reply_text(
                "🤖 *Asistente de Vinted*\n\n"
                "Puedes preguntarme:\n"
                "• Consejos para encontrar chollos\n"
                "• Cómo usar el bot\n"
                "• Tips de compra segura\n"
                "• Cualquier duda sobre Vinted\n\n"
                "Escribe tu pregunta después del comando:\n"
                "`/chat ¿cómo encontrar las mejores ofertas?`",
                parse_mode="Markdown"
            )

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Maneja mensajes de texto que no son comandos."""
        if not update.message or not update.message.text:
            return

        text = update.message.text.strip()
        user_id = update.effective_user.id

        # Detectar URLs de Vinted para análisis automático
        if "vinted" in text.lower() and ("http" in text.lower() or "www" in text.lower()):
            if self.ai_assistant and self.ai_assistant.is_available:
                await update.message.reply_text(
                    "🔍 Detecté una URL de Vinted. Usa /analizar para analizar el producto."
                )
            return

        # Si tiene IA disponible, usar asistente conversacional
        if self.ai_assistant and self.ai_assistant.is_available:
            # Detectar si parece una búsqueda
            search_keywords = ["busco", "quiero", "necesito", "encuentra", "buscar", "alertar"]
            is_search = any(keyword in text.lower() for keyword in search_keywords)

            if is_search:
                # Intentar crear alerta con IA
                parsed = await self.ai_assistant.parse_natural_language_alert(text)
                if parsed and parsed.confidence > 0.5:
                    # Verificar límite de alertas
                    alerts = await self.db.get_alerts_by_user(user_id)
                    can_create, msg = await self.subscription_manager.check_can_create_alert(user_id, len(alerts))

                    if can_create:
                        summary = f"🤖 *¿Quieres crear esta alerta?*\n\n"
                        summary += f"*{parsed.name}*\n"
                        if parsed.query:
                            summary += f"Búsqueda: _{parsed.query}_\n"
                        if parsed.price_from or parsed.price_to:
                            summary += f"Precio: {parsed.price_from or 0}€ - {parsed.price_to or '∞'}€\n"

                        keyboard = [
                            [
                                InlineKeyboardButton("✅ Sí, crear", callback_data=f"ai_confirm_{user_id}"),
                                InlineKeyboardButton("❌ No", callback_data="ai_cancel"),
                            ]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)

                        user_alert_data[user_id] = {
                            "name": parsed.name,
                            "query": parsed.query,
                            "price_from": parsed.price_from,
                            "price_to": parsed.price_to,
                            "from_ai": True,
                        }

                        await update.message.reply_text(summary, parse_mode="Markdown", reply_markup=reply_markup)
                        return

            # Respuesta general del asistente
            response = await self.ai_assistant.smart_chat_response(text)
            await update.message.reply_text(f"🤖 {response}")
