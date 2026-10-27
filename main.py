"""
main.py  —  Spookython 2026 · Motor de rutas en tiempo real
Objetivo de latencia: < 150 ms por petición.

Arrancar:
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
"""

from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager
from typing import Any

import networkx as nx
import osmnx as ox
from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuración básica
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

GRAPHML_PATH: str = os.getenv("GRAPHML_PATH", "manta_grafo.graphml")
API_KEY: str = os.getenv("SPOOKYTHON_API_KEY", "dev-secret-key")  # sobreescribir en producción


# ---------------------------------------------------------------------------
# Estado global — el grafo se carga UNA sola vez al arrancar
# ---------------------------------------------------------------------------
class AppState:
    graph: nx.MultiDiGraph | None = None


state = AppState()


# ---------------------------------------------------------------------------
# Lifespan: carga el grafo antes de aceptar peticiones
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    logger.info("Cargando grafo desde '%s' ...", GRAPHML_PATH)
    if not os.path.exists(GRAPHML_PATH):
        raise FileNotFoundError(
            f"No se encontró '{GRAPHML_PATH}'. "
            "Ejecuta 'python generar_mapa.py' primero."
        )
    state.graph = ox.load_graphml(GRAPHML_PATH)
    logger.info(
        "Grafo listo — nodos: %d | aristas: %d",
        state.graph.number_of_nodes(),
        state.graph.number_of_edges(),
    )
    yield
    # Cleanup (si fuera necesario liberar recursos)
    state.graph = None
    logger.info("Grafo descargado de memoria.")


# ---------------------------------------------------------------------------
# Aplicación FastAPI
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Spookython 2026 — Motor de Rutas",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Modelos Pydantic
# ---------------------------------------------------------------------------
class PasoRequest(BaseModel):
    """Cuerpo de la petición POST /paso."""

    sobrevivienteId: str = Field(..., examples=["S-0089"])
    nodoActual: str = Field(..., examples=["N-0117"])
    turno: int = Field(..., ge=0, examples=[142])


class PasoResponse(BaseModel):
    """Respuesta estricta del endpoint POST /paso."""

    siguienteNodo: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _validar_api_key(api_key: str) -> None:
    """Lanza 401 si la clave no coincide."""
    if api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida.",
        )


def _resolver_nodo_osm(node_label: str) -> int:
    """
    Convierte una etiqueta interna 'N-XXXX' al ID de nodo OSM.

    Estrategia actual: el sufijo numérico se usa como índice posicional
    sobre la lista de nodos del grafo (orden determinista de GraphML).
    En producción, sustituir por un dict de mapeo precalculado.
    """
    assert state.graph is not None
    try:
        index = int(node_label.split("-")[1])
        nodes = list(state.graph.nodes())
        return nodes[index % len(nodes)]
    except (IndexError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Nodo '{node_label}' no válido: {exc}",
        ) from exc


def _calcular_siguiente_nodo(nodo_actual_label: str) -> str:
    """
    Devuelve el primer vecino en el camino más corto hacia el nodo
    de mayor centralidad (punto de mayor conectividad de la red).

    Para latencia < 150 ms el grafo debe estar en memoria (ya lo está).
    """
    assert state.graph is not None
    G = state.graph

    origen_osm = _resolver_nodo_osm(nodo_actual_label)

    # Selecciona destino heurístico: nodo con mayor grado de salida
    # (puedes reemplazar por un destino fijo o recibirlo en el request)
    destino_osm: int = max(G.nodes(), key=lambda n: G.out_degree(n))  # type: ignore[arg-type]

    if origen_osm == destino_osm:
        # Ya estamos en el destino
        return nodo_actual_label

    try:
        ruta: list[Any] = nx.shortest_path(G, origen_osm, destino_osm, weight="length")
    except nx.NetworkXNoPath:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sin ruta desde '{nodo_actual_label}'.",
        )

    siguiente_osm = ruta[1]  # primer paso de la ruta
    nodes_list = list(G.nodes())
    siguiente_index = nodes_list.index(siguiente_osm)
    return f"N-{siguiente_index:04d}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.post(
    "/paso",
    response_model=PasoResponse,
    status_code=status.HTTP_200_OK,
    summary="Calcula el siguiente nodo en la ruta del sobreviviente",
)
async def paso(
    body: PasoRequest,
    x_api_key: str = Header(..., alias="x-api-key"),
) -> PasoResponse:
    """
    Recibe la posición actual de un sobreviviente y devuelve
    el siguiente nodo óptimo en su ruta de escape.

    - Valida el header **x-api-key**.
    - Calcula el camino más corto en el grafo en memoria.
    - Devuelve `{"siguienteNodo": "N-XXXX"}`.
    """
    _validar_api_key(x_api_key)

    logger.info(
        "Turno %d | Sobreviviente %s | Nodo actual %s",
        body.turno,
        body.sobrevivienteId,
        body.nodoActual,
    )

    siguiente = _calcular_siguiente_nodo(body.nodoActual)

    return PasoResponse(siguienteNodo=siguiente)


# ---------------------------------------------------------------------------
# Health-check (sin autenticación)
# ---------------------------------------------------------------------------
@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    nodos = state.graph.number_of_nodes() if state.graph else 0
    return {"status": "ok", "nodos_en_memoria": str(nodos)}
