"""API del motor de rutas de Spookython."""
from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from config import API_KEY, FRONTEND_ORIGINS, GRAPHML_PATH, REFUGES_PATH, ZONES_PATH
from graph_manager import GraphManager
from models import (
    EstadoCargaRequest,
    EstadoMundo,
    EventoSimulacion,
    PasoRequest,
    PasoResponse,
    RondaInicioResponse,
)
from routing import next_safe_node, route_from_tree, safe_route_tree, warm_base_trees
from simulation_service import SimulationService
from world_state import store

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)
graphs = GraphManager()
simulation_service = SimulationService()
_decisions: dict[tuple[int, str], str] = {}
_routes: dict[tuple[int, str], list[str]] = {}


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
    try:
        yield
    finally:
        await simulation_service.stop()


app = FastAPI(title="Spookython 2026 — Motor de Rutas", version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def require_key(value: str | None) -> None:
    if value != API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key inválida.")


def require_node(node: str) -> None:
    if not graphs.has_node(node):
        raise HTTPException(status_code=422, detail=f"Nodo '{node}' no existe.")


def require_edge(edge: list[str]) -> None:
    if len(edge) != 2 or not all(graphs.has_node(node) for node in edge):
        raise HTTPException(status_code=422, detail=f"Arista inválida: {edge}.")
    graph = graphs.game_graph()
    if not (graph.has_edge(edge[0], edge[1]) or graph.has_edge(edge[1], edge[0])):
        raise HTTPException(status_code=422, detail=f"La arista {edge} no existe en el grafo.")


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
    _routes.clear()
    graph = graphs.game_graph()
    route_trees: dict[str, dict[str, str]] = {}
    for survivor in world.sobrevivientes:
        if not survivor.activo:
            continue
        target = survivor_target(survivor.id, world)
        if target is None:
            _decisions[(world.turno, survivor.id)] = survivor.nodo
            _routes[(world.turno, survivor.id)] = [survivor.nodo]
            continue
        if target not in route_trees:
            route_trees[target] = safe_route_tree(
                graph,
                target,
                world.zombies,
                world.aristasBloqueadas,
            )
        tree = route_trees[target]
        route = route_from_tree(tree, survivor.nodo, target)
        if route is None:
            next_node = next_safe_node(
                graph,
                survivor.nodo,
                target,
                world.zombies,
                world.aristasBloqueadas,
            )
            route = [survivor.nodo]
            if next_node != survivor.nodo:
                route.append(next_node)
                continuation = route_from_tree(tree, next_node, target)
                if continuation:
                    route.extend(continuation[1:])
        _decisions[(world.turno, survivor.id)] = route[1] if len(route) > 1 else survivor.nodo
        _routes[(world.turno, survivor.id)] = route
    logger.info("Decisiones preparadas: turno=%d sobrevivientes=%d duración=%.2fms", world.turno, len(_decisions), (time.perf_counter() - started) * 1000)


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok", "nodos_en_memoria": len(graphs.game_to_osm)}


@app.get("/estado", response_model=EstadoMundo)
async def get_estado():
    world = store.get()
    survivors = [
        survivor.model_copy(
            update={
                "siguienteNodo": _decisions.get((world.turno, survivor.id)),
                "ruta": _routes.get((world.turno, survivor.id), []),
            }
        )
        for survivor in world.sobrevivientes
    ]
    return world.model_copy(update={"sobrevivientes": survivors})


@app.get("/mapa")
async def get_mapa(incluir_calles: bool = True):
    response = {
        "metadata": graphs.metadata(),
        "grafo": graphs.nodes_geojson(),
        "zonas": json.loads(ZONES_PATH.read_text(encoding="utf-8")),
        "refugios": json.loads(REFUGES_PATH.read_text(encoding="utf-8")),
    }
    if incluir_calles:
        response["calles"] = graphs.edges_geojson()
    return response


@app.post("/simulacion/demo", response_model=RondaInicioResponse)
async def start_demo():
    current = store.get()
    if not simulation_service.running and current.simulacion in {"completada", "error"}:
        store.replace(initial_state())
        _decisions.clear()
        _routes.clear()

    result = simulation_service.start_demo(graphs.game_graph(), app)
    if result["estado"] == "iniciando":
        message = "La Ronda 1 se está preparando."
    elif result["estado"] == "error":
        message = "La Ronda 1 anterior terminó con un error. Revisa los logs del servidor."
    else:
        message = "La Ronda 1 ya está en curso."
    return RondaInicioResponse(
        ronda=int(result["ronda"]),
        turno=int(result["turno"]),
        estado=result["estado"],
        mensaje=message,
    )


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
    for item in body.zombies:
        require_node(item.nodo)
        if item.nodoAnterior:
            require_node(item.nodoAnterior)
        for node in item.trayecto:
            require_node(node)
    for item in body.sobrevivientes:
        require_node(item.nodo)
        if item.nodoAnterior:
            require_node(item.nodoAnterior)
        if item.siguienteNodo:
            require_node(item.siguienteNodo)
        for node in [*item.trayecto, *item.ruta]:
            require_node(node)
    for refuge in body.refugios:
        require_node(refuge.nodo)
    for edge in body.aristasBloqueadas:
        require_edge(edge)
    for event in body.eventos:
        if event.nodo:
            require_node(event.nodo)
        if event.arista:
            require_edge(event.arista)
    previous = store.get()
    previous_decisions = dict(_decisions)
    updated = store.replace(body)
    prepare_decisions(updated)
    new_blocked = {
        frozenset(edge) for edge in updated.aristasBloqueadas
    } - {
        frozenset(edge) for edge in previous.aristasBloqueadas
    }
    events = [
        *(
            event
            for event in previous.eventos
            if event.id.startswith("API-DESVIO-")
        ),
        *updated.eventos,
    ]
    if new_blocked:
        for survivor in updated.sobrevivientes:
            if not survivor.activo:
                continue
            old_next = previous_decisions.get((previous.turno, survivor.id))
            new_next = _decisions.get((updated.turno, survivor.id))
            if old_next is not None and new_next is not None and old_next != new_next:
                edge = next(iter(new_blocked))
                events.append(
                    EventoSimulacion(
                        id=f"API-DESVIO-{updated.turno}-{survivor.id}",
                        turno=updated.turno,
                        tipo="desvio",
                        mensaje=f"Ruta de {survivor.id} recalculada por un bloqueo",
                        actores=[survivor.id],
                        nodo=survivor.nodo,
                        arista=list(edge),
                    )
                )
    updated = store.replace(updated.model_copy(update={"eventos": events[-100:]}))
    return updated
