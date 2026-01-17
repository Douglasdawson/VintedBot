"""
Cliente asíncrono para interactuar con la API de Vinted.
"""
import aiohttp
import asyncio
import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

VINTED_DOMAINS = {
    "es": "www.vinted.es",
    "fr": "www.vinted.fr",
    "de": "www.vinted.de",
    "it": "www.vinted.it",
    "nl": "www.vinted.nl",
    "be": "www.vinted.be",
    "pt": "www.vinted.pt",
    "pl": "www.vinted.pl",
    "lt": "www.vinted.lt",
    "cz": "www.vinted.cz",
    "at": "www.vinted.at",
    "uk": "www.vinted.co.uk",
}


@dataclass
class VintedItem:
    """Representa un artículo de Vinted."""
    id: int
    title: str
    price: float
    currency: str
    brand: Optional[str]
    size: Optional[str]
    url: str
    photo_url: Optional[str]
    user_login: str
    is_visible: bool
    created_at: str
    status: Optional[str]

    @classmethod
    def from_api_response(cls, data: dict, domain: str) -> "VintedItem":
        """Crea un VintedItem desde la respuesta de la API."""
        photo_url = None
        if data.get("photo") and data["photo"].get("url"):
            photo_url = data["photo"]["url"]
        elif data.get("photos") and len(data["photos"]) > 0:
            photo_url = data["photos"][0].get("url")

        return cls(
            id=data["id"],
            title=data.get("title", "Sin título"),
            price=float(data.get("price", {}).get("amount", 0) if isinstance(data.get("price"), dict) else data.get("price", 0)),
            currency=data.get("price", {}).get("currency_code", "EUR") if isinstance(data.get("price"), dict) else "EUR",
            brand=data.get("brand_title") or data.get("brand"),
            size=data.get("size_title") or data.get("size"),
            url=f"https://{domain}/items/{data['id']}",
            photo_url=photo_url,
            user_login=data.get("user", {}).get("login", "desconocido") if isinstance(data.get("user"), dict) else "desconocido",
            is_visible=data.get("is_visible", True),
            created_at=data.get("created_at_ts", ""),
            status=data.get("status"),
        )


class VintedClient:
    """Cliente asíncrono para la API de Vinted."""

    def __init__(self, domain: str = "es"):
        self.domain = VINTED_DOMAINS.get(domain, VINTED_DOMAINS["es"])
        self.base_url = f"https://{self.domain}"
        self.api_url = f"{self.base_url}/api/v2"
        self._session: Optional[aiohttp.ClientSession] = None
        self._cookies: dict = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Obtiene o crea una sesión HTTP."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Referer": self.base_url,
                    "Origin": self.base_url,
                }
            )
        return self._session

    async def _refresh_cookies(self) -> None:
        """Refresca las cookies visitando la página principal."""
        session = await self._get_session()
        try:
            async with session.get(self.base_url) as response:
                if response.status == 200:
                    self._cookies = {c.key: c.value for c in session.cookie_jar}
                    logger.debug("Cookies refrescadas correctamente")
        except Exception as e:
            logger.error(f"Error refrescando cookies: {e}")

    async def search(
        self,
        query: Optional[str] = None,
        catalog_ids: Optional[list[int]] = None,
        brand_ids: Optional[list[int]] = None,
        size_ids: Optional[list[int]] = None,
        material_ids: Optional[list[int]] = None,
        color_ids: Optional[list[int]] = None,
        status_ids: Optional[list[int]] = None,
        price_from: Optional[float] = None,
        price_to: Optional[float] = None,
        currency: str = "EUR",
        order: str = "newest_first",
        per_page: int = 20,
        page: int = 1,
    ) -> list[VintedItem]:
        """
        Busca artículos en Vinted con filtros completos.

        Args:
            query: Texto de búsqueda
            catalog_ids: IDs de categorías (ej: [5, 1904] para ropa mujer, camisetas)
            brand_ids: IDs de marcas (ej: [53] para Zara)
            size_ids: IDs de tallas (ej: [206] para M)
            material_ids: IDs de materiales
            color_ids: IDs de colores (ej: [1] para negro)
            status_ids: IDs de estados (1=nuevo con etiquetas, 2=nuevo sin etiquetas, 3=muy bueno, 4=bueno, 5=satisfactorio)
            price_from: Precio mínimo
            price_to: Precio máximo
            currency: Moneda (EUR, GBP, etc.)
            order: Orden (newest_first, price_low_to_high, price_high_to_low, relevance)
            per_page: Resultados por página (máx 96)
            page: Número de página

        Returns:
            Lista de VintedItem
        """
        if not self._cookies:
            await self._refresh_cookies()

        params = {
            "per_page": min(per_page, 96),
            "page": page,
            "order": order,
            "currency": currency,
        }

        if query:
            params["search_text"] = query
        if catalog_ids:
            params["catalog_ids"] = ",".join(map(str, catalog_ids))
        if brand_ids:
            params["brand_ids"] = ",".join(map(str, brand_ids))
        if size_ids:
            params["size_ids"] = ",".join(map(str, size_ids))
        if material_ids:
            params["material_ids"] = ",".join(map(str, material_ids))
        if color_ids:
            params["color_ids"] = ",".join(map(str, color_ids))
        if status_ids:
            params["status_ids"] = ",".join(map(str, status_ids))
        if price_from is not None:
            params["price_from"] = price_from
        if price_to is not None:
            params["price_to"] = price_to

        session = await self._get_session()
        url = f"{self.api_url}/catalog/items"

        try:
            async with session.get(url, params=params) as response:
                if response.status == 401:
                    await self._refresh_cookies()
                    async with session.get(url, params=params) as retry_response:
                        data = await retry_response.json()
                elif response.status == 200:
                    data = await response.json()
                else:
                    logger.error(f"Error en búsqueda: {response.status}")
                    return []

                items = data.get("items", [])
                return [VintedItem.from_api_response(item, self.domain) for item in items]

        except Exception as e:
            logger.error(f"Error en búsqueda: {e}")
            return []

    async def get_item(self, item_id: int) -> Optional[VintedItem]:
        """Obtiene los detalles de un artículo específico."""
        session = await self._get_session()
        url = f"{self.api_url}/items/{item_id}"

        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    item_data = data.get("item", data)
                    return VintedItem.from_api_response(item_data, self.domain)
                return None
        except Exception as e:
            logger.error(f"Error obteniendo item {item_id}: {e}")
            return None

    async def close(self) -> None:
        """Cierra la sesión HTTP."""
        if self._session and not self._session.closed:
            await self._session.close()
