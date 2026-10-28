"""API del motor de rutas de Spookython."""
from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager

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
    _decisions.clear()
    graph = graphs.game_graph()
    for survivor in world.sobrevivientes:
        if not survivor.activo:
            continue
        target = survivor_target(survivor.id, world)
        if target is None:
            _decisions[(world.turno, survivor.id)] = survivor.nodo
            continue
        _decisions[(world.turno, survivor.id)] = next_safe_node(
            graph,
            survivor.nodo,
            target,
            world.zombies,
            world.aristasBloqueadas,
        )
    logger.info("Decisiones preparadas: turno=%d sobrevivientes=%d duración=%.2fms", world.turno, len(_decisions), (time.perf_counter() - started) * 1000)


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok", "nodos_en_memoria": len(graphs.game_to_osm)}


@app.get("/estado", response_model=EstadoMundo)
async def get_estado():
    return store.get()


@app.get("/mapa")
async def get_mapa():
    return {"metadata": graphs.metadata(), "grafo": graphs.nodes_geojson()}


@app.post("/paso", response_model=PasoResponse)
async def paso(body: PasoRequest, x_api_key: str | None = Header(default=None, alias="x-api-key")):
    require_key(x_api_key)
    require_node(body.nodoActual)
    world = store.get()
    if body.turno != world.turno:
        raise HTTPException(status_code=409, detail=f"Turno actual: {world.turno}.")
    cached = _decisions.get((body.turno, body.sobrevivienteId))
    if cached is not None:
        return PasoResponse(siguienteNodo=cached)
    target = survivor_target(body.sobrevivienteId, world)
    if target is None:
        return PasoResponse(siguienteNodo=body.nodoActual)
    next_node = next_safe_node(graphs.game_graph(), body.nodoActual, target, world.zombies, world.aristasBloqueadas)
    return PasoResponse(siguienteNodo=next_node)


@app.post("/estado", response_model=EstadoMundo)
async def replace_estado(body: EstadoCargaRequest, x_api_key: str | None = Header(default=None, alias="x-api-key")):
    """Endpoint temporal para integrar y probar el simulador local."""
    require_key(x_api_key)
    for item in [*body.zombies, *body.sobrevivientes]:
        require_node(item.nodo)
    for refuge in body.refugios:
        require_node(refuge.nodo)
    updated = store.replace(body)
    prepare_decisions(updated)
    return updated
