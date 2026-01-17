"""
Cliente asíncrono para interactuar con la API de Vinted.
"""
import aiohttp
import asyncio
import logging
from typing import Optional
from dataclasses import dataclass, field

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
class VintedUser:
    """Representa un vendedor de Vinted."""
    id: int
    login: str
    photo_url: Optional[str] = None
    feedback_reputation: float = 0.0
    feedback_count: int = 0
    is_verified: bool = False
    country_code: Optional[str] = None
    city: Optional[str] = None


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
    # Campos avanzados
    user: Optional[VintedUser] = None
    total_price: Optional[float] = None  # Precio con envío
    shipping_price: Optional[float] = None
    free_shipping: bool = False
    favourite_count: int = 0
    view_count: int = 0
    description: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None

    @classmethod
    def from_api_response(cls, data: dict, domain: str) -> "VintedItem":
        """Crea un VintedItem desde la respuesta de la API."""
        photo_url = None
        if data.get("photo") and data["photo"].get("url"):
            photo_url = data["photo"]["url"]
        elif data.get("photos") and len(data["photos"]) > 0:
            photo_url = data["photos"][0].get("url")

        # Extraer información del usuario/vendedor
        user_data = data.get("user", {})
        user = None
        if isinstance(user_data, dict) and user_data:
            user = VintedUser(
                id=user_data.get("id", 0),
                login=user_data.get("login", "desconocido"),
                photo_url=user_data.get("photo", {}).get("url") if user_data.get("photo") else None,
                feedback_reputation=float(user_data.get("feedback_reputation", 0) or 0),
                feedback_count=int(user_data.get("feedback_count", 0) or 0),
                is_verified=user_data.get("verification", {}).get("email", {}).get("valid", False) if user_data.get("verification") else False,
                country_code=user_data.get("country_code"),
                city=user_data.get("city"),
            )

        # Extraer precio con envío
        price_val = data.get("price", {})
        if isinstance(price_val, dict):
            price = float(price_val.get("amount", 0))
            currency = price_val.get("currency_code", "EUR")
        else:
            price = float(price_val or 0)
            currency = "EUR"

        # Precio total con envío
        total_price_data = data.get("total_item_price", {})
        total_price = float(total_price_data.get("amount", 0)) if isinstance(total_price_data, dict) else None

        # Precio de envío
        service_fee = data.get("service_fee", {})
        shipping_price = float(service_fee.get("amount", 0)) if isinstance(service_fee, dict) else None

        return cls(
            id=data["id"],
            title=data.get("title", "Sin título"),
            price=price,
            currency=currency,
            brand=data.get("brand_title") or data.get("brand"),
            size=data.get("size_title") or data.get("size"),
            url=f"https://{domain}/items/{data['id']}",
            photo_url=photo_url,
            user_login=user.login if user else "desconocido",
            is_visible=data.get("is_visible", True),
            created_at=data.get("created_at_ts", ""),
            status=data.get("status"),
            user=user,
            total_price=total_price,
            shipping_price=shipping_price,
            free_shipping=data.get("is_free_shipping", False),
            favourite_count=int(data.get("favourite_count", 0) or 0),
            view_count=int(data.get("view_count", 0) or 0),
            description=data.get("description"),
            country=data.get("country"),
            city=data.get("city"),
        )

    def matches_advanced_filters(
        self,
        min_seller_rating: Optional[float] = None,
        min_seller_reviews: Optional[int] = None,
        verified_seller_only: bool = False,
        free_shipping_only: bool = False,
        max_total_price: Optional[float] = None,
        excluded_sellers: Optional[list[str]] = None,
        country_codes: Optional[list[str]] = None,
    ) -> bool:
        """Verifica si el item cumple con los filtros avanzados."""
        # Filtro de vendedor excluido
        if excluded_sellers and self.user_login.lower() in [s.lower() for s in excluded_sellers]:
            return False

        # Filtro de reputación mínima del vendedor
        if min_seller_rating is not None and self.user:
            if self.user.feedback_reputation < min_seller_rating:
                return False

        # Filtro de mínimo de reseñas
        if min_seller_reviews is not None and self.user:
            if self.user.feedback_count < min_seller_reviews:
                return False

        # Filtro de vendedor verificado
        if verified_seller_only and self.user:
            if not self.user.is_verified:
                return False

        # Filtro de envío gratis
        if free_shipping_only and not self.free_shipping:
            return False

        # Filtro de precio total máximo (con envío)
        if max_total_price is not None and self.total_price:
            if self.total_price > max_total_price:
                return False

        # Filtro de país
        if country_codes and self.user:
            if self.user.country_code and self.user.country_code.upper() not in [c.upper() for c in country_codes]:
                return False

        return True


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
        # Filtros avanzados (se aplican post-búsqueda)
        min_seller_rating: Optional[float] = None,
        min_seller_reviews: Optional[int] = None,
        verified_seller_only: bool = False,
        free_shipping_only: bool = False,
        max_total_price: Optional[float] = None,
        excluded_sellers: Optional[list[str]] = None,
        country_codes: Optional[list[str]] = None,
    ) -> list[VintedItem]:
        """
        Busca artículos en Vinted con filtros completos.

        Args:
            query: Texto de búsqueda
            catalog_ids: IDs de categorías
            brand_ids: IDs de marcas
            size_ids: IDs de tallas
            material_ids: IDs de materiales
            color_ids: IDs de colores
            status_ids: IDs de estados (6=nuevo con etiquetas, 1=nuevo sin etiquetas, 2=muy bueno, 3=bueno, 4=satisfactorio)
            price_from: Precio mínimo
            price_to: Precio máximo
            currency: Moneda (EUR, GBP, etc.)
            order: Orden (newest_first, price_low_to_high, price_high_to_low, relevance)
            per_page: Resultados por página (máx 96)
            page: Número de página

            # Filtros avanzados (Premium)
            min_seller_rating: Reputación mínima del vendedor (0-5)
            min_seller_reviews: Número mínimo de reseñas del vendedor
            verified_seller_only: Solo vendedores verificados
            free_shipping_only: Solo productos con envío gratis
            max_total_price: Precio máximo incluyendo envío
            excluded_sellers: Lista de vendedores a excluir
            country_codes: Lista de códigos de país permitidos

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
                vinted_items = [VintedItem.from_api_response(item, self.domain) for item in items]

                # Aplicar filtros avanzados
                has_advanced_filters = any([
                    min_seller_rating, min_seller_reviews, verified_seller_only,
                    free_shipping_only, max_total_price, excluded_sellers, country_codes
                ])

                if has_advanced_filters:
                    vinted_items = [
                        item for item in vinted_items
                        if item.matches_advanced_filters(
                            min_seller_rating=min_seller_rating,
                            min_seller_reviews=min_seller_reviews,
                            verified_seller_only=verified_seller_only,
                            free_shipping_only=free_shipping_only,
                            max_total_price=max_total_price,
                            excluded_sellers=excluded_sellers,
                            country_codes=country_codes,
                        )
                    ]

                return vinted_items

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

    async def get_user_items(self, user_id: int, per_page: int = 20) -> list[VintedItem]:
        """Obtiene los artículos de un vendedor específico."""
        session = await self._get_session()
        url = f"{self.api_url}/users/{user_id}/items"

        try:
            async with session.get(url, params={"per_page": per_page}) as response:
                if response.status == 200:
                    data = await response.json()
                    items = data.get("items", [])
                    return [VintedItem.from_api_response(item, self.domain) for item in items]
                return []
        except Exception as e:
            logger.error(f"Error obteniendo items del usuario {user_id}: {e}")
            return []

    async def close(self) -> None:
        """Cierra la sesión HTTP."""
        if self._session and not self._session.closed:
            await self._session.close()
