# VintedBot

Bot de alertas para Vinted que te notifica en Telegram cuando se publican nuevos productos que coinciden con tus criterios de búsqueda.

## Características

- **Alertas personalizadas**: Crea múltiples alertas con diferentes criterios
- **Filtros completos**: Búsqueda por texto, precio, categoría, estado, color y más
- **Notificaciones instantáneas**: Recibe alertas en Telegram con foto y enlace directo
- **Gestión sencilla**: Activa, pausa o elimina alertas desde Telegram
- **Multi-dominio**: Compatible con Vinted de España, Francia, Alemania, Italia y más

## Requisitos

- Python 3.10 o superior
- Token de bot de Telegram (obtener de [@BotFather](https://t.me/BotFather))

## Instalación

1. **Clonar el repositorio**
```bash
git clone https://github.com/tu-usuario/VintedBot.git
cd VintedBot
```

2. **Crear entorno virtual**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# o
venv\Scripts\activate  # Windows
```

3. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

4. **Configurar variables de entorno**
```bash
cp .env.example .env
```

Edita `.env` y configura:
```env
TELEGRAM_BOT_TOKEN=tu_token_de_telegram
VINTED_DOMAIN=es
SCAN_INTERVAL_SECONDS=60
```

## Uso

1. **Iniciar el bot**
```bash
python main.py
```

2. **Interactuar con el bot en Telegram**
   - `/start` - Iniciar el bot
   - `/nueva` - Crear una nueva alerta
   - `/alertas` - Ver y gestionar tus alertas
   - `/ayuda` - Ver ayuda detallada
   - `/cancelar` - Cancelar operación actual

## Crear una alerta

Al usar `/nueva`, el bot te guiará paso a paso:

1. **Nombre**: Identificador para tu alerta (ej: "Zapatillas Nike")
2. **Búsqueda**: Palabras clave (opcional)
3. **Precio**: Rango mínimo y máximo (opcional)
4. **Categoría**: Mujer, Hombre, Niños, Hogar, etc. (opcional)
5. **Estado**: Nuevo, Muy bueno, Bueno, etc. (opcional)
6. **Color**: Negro, Blanco, Azul, etc. (opcional)

## Dominios soportados

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

## Estructura del proyecto

```
VintedBot/
├── main.py              # Script principal
├── requirements.txt     # Dependencias
├── .env.example         # Plantilla de configuración
├── .gitignore
└── src/
    ├── __init__.py
    ├── vinted_client.py # Cliente API de Vinted
    ├── database.py      # Gestión de base de datos
    ├── telegram_bot.py  # Bot de Telegram
    └── scanner.py       # Scanner de productos
```

## Notas

- El bot escanea productos cada 60 segundos por defecto (configurable)
- Los productos ya notificados no se vuelven a enviar
- Las notificaciones antiguas se limpian automáticamente después de 7 días

## Licencia

MIT
