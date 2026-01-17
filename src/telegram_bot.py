"""
Bot de Telegram para gestionar alertas de Vinted.
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
    ALERT_CONFIRM,
) = range(10)

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

    def setup(self) -> Application:
        """Configura y devuelve la aplicación del bot."""
        self.application = Application.builder().token(self.token).build()

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
        self.application.add_handler(conv_handler)
        self.application.add_handler(CallbackQueryHandler(self.callback_handler))

        return self.application

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /start - Bienvenida al usuario."""
        user = update.effective_user
        await self.db.add_user(user.id, user.username, user.first_name)

        welcome_text = f"""
Hola {user.first_name}! Bienvenido al Bot de Alertas de Vinted.

Con este bot podrás:
- Crear alertas personalizadas con filtros completos
- Recibir notificaciones instantáneas de nuevos productos
- Gestionar todas tus alertas fácilmente

*Comandos disponibles:*
/nueva - Crear una nueva alerta
/alertas - Ver y gestionar tus alertas
/ayuda - Ver ayuda detallada
/cancelar - Cancelar operación actual
        """
        await update.message.reply_text(welcome_text, parse_mode="Markdown")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /ayuda - Muestra ayuda detallada."""
        help_text = """
*Guía de uso del Bot de Vinted*

*Crear alertas:*
Usa /nueva para crear una alerta paso a paso. Podrás configurar:
- Nombre de la alerta
- Palabras clave de búsqueda
- Rango de precios
- Categorías
- Estado del producto
- Colores

*Gestionar alertas:*
Usa /alertas para:
- Ver todas tus alertas
- Pausar/Activar alertas
- Eliminar alertas

*Notificaciones:*
Recibirás un mensaje cada vez que se publique un producto nuevo que coincida con tus criterios.

*Consejos:*
- Sé específico en las búsquedas para mejores resultados
- Usa rangos de precio para filtrar ofertas
- Puedes tener múltiples alertas activas
        """
        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def cmd_list_alerts(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando /alertas - Lista las alertas del usuario."""
        user_id = update.effective_user.id
        alerts = await self.db.get_alerts_by_user(user_id)

        if not alerts:
            await update.message.reply_text(
                "No tienes alertas configuradas.\nUsa /nueva para crear una."
            )
            return

        text = "*Tus alertas:*\n\n"
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
                    f"{'⏸️ Pausar' if alert.is_active else '▶️ Activar'} {alert.name}",
                    callback_data=f"toggle_{alert.id}"
                ),
                InlineKeyboardButton(f"🗑️ Eliminar", callback_data=f"delete_{alert.id}")
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

    async def cmd_new_alert(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Inicia el proceso de creación de una nueva alerta."""
        user_id = update.effective_user.id
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
        return await self._show_confirm(update)

    async def alert_skip_colors(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Omite el color."""
        await update.callback_query.answer()
        user_id = update.effective_user.id
        user_alert_data[user_id]["color_ids"] = None
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
        if data.startswith("toggle_"):
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

    async def send_notification(self, user_id: int, item, alert_name: str) -> bool:
        """Envía una notificación de nuevo producto al usuario."""
        try:
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
