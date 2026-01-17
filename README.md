# VintedBot Premium

Bot de alertas premium para Vinted con sistema de suscripciones, notificaciones avanzadas y estadísticas detalladas.

## Características

### Plan Gratuito
- 1 alerta activa
- Escaneo cada 1 hora
- Filtros básicos (búsqueda, precio, categoría, estado, color)

### Plan Pro (4.99€/mes)
- 10 alertas activas
- Escaneo cada 60 segundos
- Modo Sniper (escaneo cada 30s)
- Resúmenes diarios
- Alertas de bajada de precio
- Filtros avanzados (vendedor verificado, envío gratis, reputación)
- Notificaciones prioritarias

### Plan Premium (9.99€/mes)
- Alertas ilimitadas
- Escaneo cada 30 segundos
- Todas las funciones Pro
- Estadísticas detalladas
- Historial de precios
- Análisis de tendencias

## Funcionalidades

### Alertas Personalizadas
- Búsqueda por palabras clave
- Filtro de precio mínimo/máximo
- Categorías (Mujer, Hombre, Niños, Hogar, Entretenimiento)
- Estado del producto (Nuevo, Muy bueno, Bueno, etc.)
- Colores
- Marcas y tallas

### Filtros Avanzados (Pro/Premium)
- Solo vendedores verificados
- Solo envío gratis
- Reputación mínima del vendedor
- Número mínimo de reseñas
- Excluir vendedores específicos
- Filtrar por país

### Notificaciones
- Notificaciones instantáneas con foto
- Información del vendedor (valoración, reseñas)
- Indicador de envío gratis
- Enlace directo al producto
- Modo silencio (horas de descanso)

### Modo Sniper (Pro/Premium)
- Escaneo cada 30 segundos
- Notificaciones prioritarias
- Ideal para chollos y productos muy buscados

### Estadísticas (Premium)
- Total de notificaciones (hoy, semana, mes)
- Precios encontrados (promedio, mínimo, máximo)
- Alerta más activa
- Estadísticas por alerta
- Tendencias de precios

## Comandos del Bot

| Comando | Descripción |
|---------|-------------|
| `/start` | Iniciar el bot |
| `/nueva` | Crear una nueva alerta |
| `/alertas` | Ver y gestionar alertas |
| `/plan` | Ver tu plan actual |
| `/planes` | Ver planes disponibles |
| `/stats` | Ver estadísticas |
| `/config` | Configurar notificaciones |
| `/sniper` | Activar/desactivar modo sniper |
| `/ayuda` | Ver ayuda detallada |
| `/cancelar` | Cancelar operación |

## Instalación

### Requisitos
- Python 3.10 o superior
- Token de bot de Telegram (de [@BotFather](https://t.me/BotFather))

### Pasos

1. **Clonar el repositorio**
```bash
git clone https://github.com/tu-usuario/VintedBot.git
cd VintedBot
```

2. **Crear entorno virtual**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

4. **Configurar variables de entorno**
```bash
cp .env.example .env
```

Edita `.env`:
```env
TELEGRAM_BOT_TOKEN=tu_token_de_telegram
VINTED_DOMAIN=es
SCAN_INTERVAL_SECONDS=60
```

5. **Ejecutar**
```bash
python main.py
```

## Dominios Soportados

| Código | País |
|--------|------|
| es | España |
| fr | Francia |
| de | Alemania |
| it | Italia |
| nl | Países Bajos |
| be | Bélgica |
| pt | Portugal |
| pl | Polonia |
| lt | Lituania |
| cz | República Checa |
| at | Austria |
| uk | Reino Unido |

## Estructura del Proyecto

```
VintedBot/
├── main.py                 # Script principal
├── requirements.txt        # Dependencias
├── .env.example           # Plantilla de configuración
├── .gitignore
└── src/
    ├── __init__.py
    ├── vinted_client.py   # Cliente API de Vinted
    ├── database.py        # Gestión de base de datos
    ├── telegram_bot.py    # Bot de Telegram
    ├── scanner.py         # Scanner de productos
    ├── subscriptions.py   # Sistema de suscripciones
    ├── statistics.py      # Sistema de estadísticas
    └── notifications.py   # Notificaciones avanzadas
```

## Arquitectura

```
┌─────────────────┐     ┌─────────────────┐
│   Telegram Bot  │────▶│    Database     │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│     Scanner     │────▶│  Vinted Client  │
└────────┬────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│  Subscriptions  │     │   Statistics    │
└─────────────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐
│  Notifications  │
│  (Sniper Mode)  │
└─────────────────┘
```

## Monetización

El bot incluye un sistema de planes preparado para monetización:

1. **Plan Gratuito**: Funcionalidades básicas para captar usuarios
2. **Plan Pro**: Para usuarios que quieren más alertas y velocidad
3. **Plan Premium**: Para usuarios avanzados y revendedores

Para activar pagos, integrar con:
- Stripe
- PayPal
- Crypto (opcional)

## Personalización

### Añadir más categorías

Edita `CATEGORIES` en `src/telegram_bot.py`:

```python
CATEGORIES = {
    "Tu Categoría": {
        "Subcategoría": ID_VINTED,
    },
}
```

### Cambiar planes

Edita `PLANS` en `src/subscriptions.py`:

```python
PLANS = {
    PlanType.PRO: Plan(
        max_alerts=10,
        scan_interval=60,
        price_monthly=4.99,
        # ...
    ),
}
```

## Licencia

MIT

## Soporte

Para soporte o preguntas, contacta con el administrador del bot.
