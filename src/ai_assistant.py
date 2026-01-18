"""
Módulo de IA para el bot de Vinted.
Incluye asistente conversacional, búsqueda semántica, detector de chollos y análisis de descripciones.
"""
import json
import logging
import os
from typing import Optional
from dataclasses import dataclass
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


@dataclass
class AlertFromNaturalLanguage:
    """Alerta extraída de lenguaje natural."""
    name: str
    query: Optional[str] = None
    price_from: Optional[float] = None
    price_to: Optional[float] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    status: Optional[str] = None
    confidence: float = 0.0


@dataclass
class DealAnalysis:
    """Análisis de si un producto es un chollo."""
    is_deal: bool
    score: int  # 1-10
    estimated_market_price: float
    savings_percentage: float
    reasoning: str
    recommendation: str


@dataclass
class ProductAnalysis:
    """Análisis de un producto."""
    condition_score: int  # 1-10
    authenticity_score: int  # 1-10 (10 = probablemente auténtico)
    hidden_defects: list[str]
    positive_aspects: list[str]
    warnings: list[str]
    summary: str


class AIAssistant:
    """Asistente de IA para el bot de Vinted."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("OPENAI_API_KEY no configurada. Funciones de IA deshabilitadas.")
            self.client = None
        else:
            self.client = AsyncOpenAI(api_key=self.api_key)

        self.model = "gpt-4o-mini"  # Modelo rápido y económico
        self.embedding_model = "text-embedding-3-small"

        # Cache de embeddings para búsqueda semántica
        self._embeddings_cache: dict[str, list[float]] = {}

    @property
    def is_available(self) -> bool:
        """Verifica si la IA está disponible."""
        return self.client is not None

    async def parse_natural_language_alert(self, user_message: str) -> Optional[AlertFromNaturalLanguage]:
        """
        Convierte un mensaje en lenguaje natural a una alerta estructurada.

        Ejemplo: "Busca zapatillas Nike Air Max negras talla 42 por menos de 50€"
        """
        if not self.is_available:
            return None

        system_prompt = """Eres un asistente que extrae información de búsqueda de productos de Vinted.
Analiza el mensaje del usuario y extrae los siguientes campos si están presentes:
- name: nombre descriptivo para la alerta
- query: palabras clave de búsqueda
- price_from: precio mínimo (número)
- price_to: precio máximo (número)
- category: categoría (mujer_ropa, mujer_zapatos, hombre_ropa, hombre_zapatos, niños, hogar, etc.)
- brand: marca del producto
- size: talla (S, M, L, XL, 38, 42, etc.)
- color: color del producto
- status: estado (nuevo, muy_bueno, bueno, satisfactorio)
- confidence: tu confianza en la interpretación (0.0 a 1.0)

Responde SOLO con JSON válido, sin explicaciones adicionales."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=500,
            )

            result = json.loads(response.choices[0].message.content)

            return AlertFromNaturalLanguage(
                name=result.get("name", "Alerta personalizada"),
                query=result.get("query"),
                price_from=result.get("price_from"),
                price_to=result.get("price_to"),
                category=result.get("category"),
                brand=result.get("brand"),
                size=result.get("size"),
                color=result.get("color"),
                status=result.get("status"),
                confidence=result.get("confidence", 0.5),
            )

        except Exception as e:
            logger.error(f"Error parseando lenguaje natural: {e}")
            return None

    async def analyze_deal(
        self,
        title: str,
        description: str,
        price: float,
        brand: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Optional[DealAnalysis]:
        """
        Analiza si un producto es un chollo comparando con precios de mercado.
        """
        if not self.is_available:
            return None

        system_prompt = """Eres un experto en análisis de precios de productos de segunda mano en Vinted.
Analiza el producto y determina si es un buen precio (chollo) basándote en:
- Precio de mercado típico para productos similares nuevos y de segunda mano
- Estado del producto según la descripción
- Marca y demanda del producto

Responde SOLO con JSON válido con estos campos:
- is_deal: boolean (true si es un chollo)
- score: número del 1-10 (10 = chollo increíble)
- estimated_market_price: precio estimado de mercado para este producto
- savings_percentage: porcentaje de ahorro respecto al precio de mercado
- reasoning: explicación breve de tu análisis
- recommendation: recomendación para el comprador"""

        product_info = f"""
Título: {title}
Descripción: {description}
Precio: {price}€
Marca: {brand or 'No especificada'}
Categoría: {category or 'No especificada'}
"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": product_info}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=500,
            )

            result = json.loads(response.choices[0].message.content)

            return DealAnalysis(
                is_deal=result.get("is_deal", False),
                score=result.get("score", 5),
                estimated_market_price=result.get("estimated_market_price", price),
                savings_percentage=result.get("savings_percentage", 0),
                reasoning=result.get("reasoning", ""),
                recommendation=result.get("recommendation", ""),
            )

        except Exception as e:
            logger.error(f"Error analizando deal: {e}")
            return None

    async def analyze_product_description(
        self,
        title: str,
        description: str,
        brand: Optional[str] = None,
    ) -> Optional[ProductAnalysis]:
        """
        Analiza la descripción de un producto para detectar defectos ocultos,
        señales de falsificación, y extraer información relevante.
        """
        if not self.is_available:
            return None

        system_prompt = """Eres un experto en análisis de productos de segunda mano.
Analiza el título y descripción del producto para:
1. Detectar posibles defectos ocultos o minimizados
2. Evaluar señales de autenticidad/falsificación
3. Identificar aspectos positivos
4. Generar advertencias para el comprador

Responde SOLO con JSON válido con estos campos:
- condition_score: puntuación del estado real (1-10)
- authenticity_score: probabilidad de ser auténtico (1-10, 10=muy probablemente auténtico)
- hidden_defects: lista de posibles defectos detectados o sospechados
- positive_aspects: lista de aspectos positivos
- warnings: lista de advertencias para el comprador
- summary: resumen breve del análisis"""

        product_info = f"""
Título: {title}
Descripción: {description}
Marca: {brand or 'No especificada'}
"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": product_info}
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=600,
            )

            result = json.loads(response.choices[0].message.content)

            return ProductAnalysis(
                condition_score=result.get("condition_score", 5),
                authenticity_score=result.get("authenticity_score", 5),
                hidden_defects=result.get("hidden_defects", []),
                positive_aspects=result.get("positive_aspects", []),
                warnings=result.get("warnings", []),
                summary=result.get("summary", ""),
            )

        except Exception as e:
            logger.error(f"Error analizando producto: {e}")
            return None

    async def get_embedding(self, text: str) -> Optional[list[float]]:
        """Obtiene el embedding de un texto para búsqueda semántica."""
        if not self.is_available:
            return None

        # Verificar cache
        if text in self._embeddings_cache:
            return self._embeddings_cache[text]

        try:
            response = await self.client.embeddings.create(
                model=self.embedding_model,
                input=text,
            )
            embedding = response.data[0].embedding
            self._embeddings_cache[text] = embedding
            return embedding

        except Exception as e:
            logger.error(f"Error obteniendo embedding: {e}")
            return None

    async def find_similar_terms(self, query: str) -> list[str]:
        """
        Genera términos de búsqueda similares/relacionados para mejorar resultados.
        Útil para búsqueda semántica.
        """
        if not self.is_available:
            return [query]

        system_prompt = """Genera términos de búsqueda alternativos y sinónimos para productos de moda/ropa en español.
Incluye:
- Sinónimos
- Variaciones de escritura
- Términos relacionados
- Traducciones comunes si aplica

Responde SOLO con JSON: {"terms": ["término1", "término2", ...]}
Máximo 8 términos adicionales."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Términos alternativos para: {query}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.5,
                max_tokens=200,
            )

            result = json.loads(response.choices[0].message.content)
            terms = result.get("terms", [])
            return [query] + terms[:8]

        except Exception as e:
            logger.error(f"Error generando términos similares: {e}")
            return [query]

    async def smart_chat_response(
        self,
        user_message: str,
        context: Optional[str] = None,
    ) -> str:
        """
        Genera una respuesta inteligente para el chat.
        Puede responder preguntas sobre Vinted, dar consejos de compra, etc.
        """
        if not self.is_available:
            return "Lo siento, el asistente de IA no está disponible en este momento."

        system_prompt = """Eres un asistente experto en Vinted, la plataforma de compraventa de ropa de segunda mano.
Puedes ayudar con:
- Consejos para encontrar buenos productos
- Explicar cómo funciona el bot de alertas
- Dar recomendaciones de búsqueda
- Responder preguntas sobre compras seguras

Sé conciso, amable y útil. Responde en español.
Si el usuario quiere crear una alerta, indica que puede hacerlo con /nueva o describiendo lo que busca."""

        messages = [{"role": "system", "content": system_prompt}]

        if context:
            messages.append({"role": "system", "content": f"Contexto: {context}"})

        messages.append({"role": "user", "content": user_message})

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=300,
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Error en chat: {e}")
            return "Lo siento, ha ocurrido un error. Por favor, inténtalo de nuevo."

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Calcula la similitud coseno entre dos vectores."""
        import numpy as np
        a = np.array(a)
        b = np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    async def semantic_match(
        self,
        query: str,
        candidates: list[str],
        threshold: float = 0.7,
    ) -> list[tuple[str, float]]:
        """
        Encuentra candidatos semánticamente similares a la query.
        Retorna lista de (candidato, score) ordenada por relevancia.
        """
        if not self.is_available:
            return []

        query_embedding = await self.get_embedding(query)
        if not query_embedding:
            return []

        results = []
        for candidate in candidates:
            candidate_embedding = await self.get_embedding(candidate)
            if candidate_embedding:
                score = self.cosine_similarity(query_embedding, candidate_embedding)
                if score >= threshold:
                    results.append((candidate, score))

        return sorted(results, key=lambda x: x[1], reverse=True)
