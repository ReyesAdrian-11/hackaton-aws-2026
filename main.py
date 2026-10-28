"""API del motor de rutas de Spookython."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import API_KEY, FRONTEND_ORIGINS, GRAPHML_PATH, REFUGES_PATH, ZONES_PATH
from graph_manager import GraphManager
from models import (
    EstadoCargaRequest,
    EstadoMundo,
    EventoSimulacion,
    IncidenteRequest,
    IncidenteResponse,
    PasoRequest,
    PasoResponse,
    Refugio,
    RondaInicioRequest,
    RondaInicioResponse,
)
from routing import base_distances, next_safe_node, route_from_tree, safe_route_tree, warm_base_trees
from simulation_service import SimulationService
from world_state import store

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)
graphs = GraphManager()
simulation_service = SimulationService()
_decisions: dict[tuple[int, str], str] = {}
_routes: dict[tuple[int, str], list[str]] = {}
_targets: dict[tuple[int, str], str] = {}
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="decisions")


class StateHub:
    """In-process fan-out of snapshots for WebSocket/AppSync adapters."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    async def publish(self, state: EstadoMundo) -> None:
        if not self._clients:
            return
        payload = state.model_dump(by_alias=True)
        stale: list[WebSocket] = []
        for websocket in tuple(self._clients):
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(websocket)


state_hub = StateHub()
PUBLIC_HTTP_ROUTES = {
    ("GET", "/health"),
    ("GET", "/mapa"),
    ("GET", "/estado"),
    ("POST", "/simulacion/demo"),
    ("POST", "/simulacion/prueba-fuego"),
}


def initial_state() -> EstadoMundo:
    if REFUGES_PATH.exists():
        refugios = json.loads(REFUGES_PATH.read_text(encoding="utf-8"))
        refugios = [
            {**refuge, "capacidad": min(int(refuge.get("capacidad", 50)), 50)}
            for refuge in refugios
        ]
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
    allow_headers=["Content-Type", "x-api-key"],
)


@app.middleware("http")
async def authenticate_requests(request: Request, call_next):
    """Require the challenge API key on every application request.

    CORS preflight is intentionally allowed to reach CORSMiddleware; the
    actual GET/POST request still requires x-api-key. This keeps the API
    contract secure without making browser preflight impossible.
    """
    if request.method != "OPTIONS" and (
        request.method,
        request.url.path,
    ) not in PUBLIC_HTTP_ROUTES:
        if request.headers.get("x-api-key") != API_KEY:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "API key inválida."},
            )
    return await call_next(request)


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


def survivor_target(
    survivor_id: str,
    world: EstadoMundo,
    reserved_capacity: dict[str, int] | None = None,
) -> Refugio | None:
    """Choose a reachable refuge while respecting already planned arrivals."""
    reserved_capacity = reserved_capacity if reserved_capacity is not None else {}

    def has_capacity(refuge: Refugio) -> bool:
        remaining = refuge.capacidad - refuge.ocupados
        return reserved_capacity.get(refuge.id, 0) < remaining

    survivor = next((s for s in world.sobrevivientes if s.id == survivor_id), None)
    if survivor and survivor.refugio:
        refuge = next((r for r in world.refugios if r.id == survivor.refugio), None)
        if refuge and has_capacity(refuge):
            return refuge
    available = [r for r in world.refugios if has_capacity(r)]
    if not survivor or not available:
        return None

    graph = graphs.game_graph()
    reachable = [
        (distances[survivor.nodo], refuge)
        for refuge in available
        if (distances := base_distances(graph, refuge.nodo)).get(survivor.nodo) is not None
    ]
    return min(reachable, key=lambda item: item[0])[1] if reachable else None


def prepare_decisions(world: EstadoMundo) -> None:
    """Planifica una vez por turno; /paso únicamente consulta este caché."""
    global _decisions, _routes, _targets

    started = time.perf_counter()
    new_decisions: dict[tuple[int, str], str] = {}
    new_routes: dict[tuple[int, str], list[str]] = {}
    new_targets: dict[tuple[int, str], str] = {}
    graph = graphs.game_graph()
    route_trees: dict[str, dict[str, str]] = {}
    reserved_capacity = {refuge.id: 0 for refuge in world.refugios}
    for survivor in world.sobrevivientes:
        if not survivor.activo:
            continue
        refuge = survivor_target(survivor.id, world, reserved_capacity)
        if refuge is None:
            new_decisions[(world.turno, survivor.id)] = survivor.nodo
            new_routes[(world.turno, survivor.id)] = [survivor.nodo]
            continue
        target = refuge.nodo
        new_targets[(world.turno, survivor.id)] = refuge.id
        reserved_capacity[refuge.id] += 1
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
        new_decisions[(world.turno, survivor.id)] = route[1] if len(route) > 1 else survivor.nodo
        new_routes[(world.turno, survivor.id)] = route

    _decisions = new_decisions
    _routes = new_routes
    _targets = new_targets
    logger.info(
        "Decisiones preparadas: turno=%d sobrevivientes=%d duración=%.2fms",
        world.turno,
        len(new_decisions),
        (time.perf_counter() - started) * 1000,
    )


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
                "refugio": _targets.get((world.turno, survivor.id), survivor.refugio),
            }
        )
        for survivor in world.sobrevivientes
    ]
    return world.model_copy(update={"sobrevivientes": survivors})


@app.websocket("/ws/estado")
async def websocket_estado(websocket: WebSocket):
    """Publica snapshots completos después de cada tick de simulación."""
    key = websocket.headers.get("x-api-key") or websocket.query_params.get("x-api-key")
    if key != API_KEY:
        await websocket.close(code=4401, reason="API key inválida.")
        return
    await state_hub.connect(websocket)
    try:
        current = await get_estado()
        await websocket.send_json(current.model_dump(by_alias=True))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state_hub.disconnect(websocket)
    except Exception:
        state_hub.disconnect(websocket)


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
async def start_demo(request: RondaInicioRequest | None = None):
    round_number = request.ronda if request else 1
    if simulation_service.running and simulation_service.round_number == round_number:
        result = await simulation_service.start_demo(round_number, graphs.game_graph(), app)
    else:
        if simulation_service.running:
            await simulation_service.stop()
        _decisions.clear()
        _routes.clear()
        _targets.clear()
        fresh_state = initial_state().model_copy(
            update={"ronda": round_number, "simulacion": "iniciando"}
        )
        store.replace(fresh_state)
        result = await simulation_service.start_demo(round_number, graphs.game_graph(), app)
    if result["estado"] == "iniciando":
        message = f"La Ronda {round_number} se está preparando."
    elif result["estado"] == "error":
        message = f"La Ronda {round_number} anterior terminó con un error. Revisa los logs del servidor."
    else:
        message = f"La Ronda {round_number} ya está en curso."
    return RondaInicioResponse(
        ronda=int(result["ronda"]),
        turno=int(result["turno"]),
        estado=result["estado"],
        mensaje=message,
    )


@app.post("/simulacion/prueba-fuego", response_model=RondaInicioResponse)
async def start_fire_test():
    """Launch the mandatory R1 → R2 → R3 sequence, 150 ticks each."""
    if simulation_service.running:
        return RondaInicioResponse(
            ronda=int(simulation_service.round_number or 1),
            turno=store.get().turno,
            estado="en_curso",
            mensaje="La Prueba de Fuego ya está en curso.",
        )
    _decisions.clear()
    _routes.clear()
    _targets.clear()
    store.replace(initial_state().model_copy(update={"simulacion": "iniciando"}))
    result = await simulation_service.start_fire_test(graphs.game_graph(), app)
    return RondaInicioResponse(
        ronda=int(result["ronda"]),
        turno=int(result["turno"]),
        estado=result["estado"],
        mensaje="La Prueba de Fuego R1 → R2 → R3 se está preparando.",
    )


@app.post("/simulacion/incidente", response_model=IncidenteResponse)
async def inject_incident(
    request: IncidenteRequest,
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
):
    """Schedule a real road closure for the current simulation tick."""
    require_key(x_api_key)
    require_edge(request.arista)
    edge = tuple(request.arista)
    if frozenset(edge) in store.get_blocked_edges():
        raise HTTPException(status_code=409, detail="La arista ya está bloqueada.")
    turno = simulation_service.inject_block(edge, request.nombre)
    if turno is None:
        raise HTTPException(status_code=409, detail="No hay una simulación activa.")
    return IncidenteResponse(
        estado="programado",
        turno=turno,
        arista=request.arista,
        mensaje=f"Incidente programado para el turno {turno}; las rutas se recalcularán al publicarse el tick.",
    )


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
        "destinos": {
            sid: target
            for (turno, sid), target in _targets.items()
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
        graph = graphs.game_graph()
        blocked_edges = store.get_blocked_edges()
        if cached == body.nodoActual or (
            graph.has_edge(body.nodoActual, cached)
            and frozenset((body.nodoActual, cached)) not in blocked_edges
        ):
            return PasoResponse(siguienteNodo=cached)
        logger.warning("Cache miss por nodo divergente: sobreviviente=%s cache_nodo=%s actual=%s", body.sobrevivienteId, cached, body.nodoActual)

    # Fallback: calcular on-the-fly desde la posición real reportada.
    world = store.get()
    target_id = _targets.get((body.turno, body.sobrevivienteId))
    target_refuge = next((refuge for refuge in world.refugios if refuge.id == target_id), None)
    if target_refuge is None:
        target_refuge = survivor_target(body.sobrevivienteId, world)
    if target_refuge is None:
        return PasoResponse(siguienteNodo=body.nodoActual)
    next_node = next_safe_node(
        graphs.game_graph(),
        body.nodoActual,
        target_refuge.nodo,
        world.zombies,
        world.aristasBloqueadas,
    )
    return PasoResponse(siguienteNodo=next_node)


@app.post("/estado", response_model=EstadoMundo)
async def replace_estado(body: EstadoCargaRequest, x_api_key: str | None = Header(default=None, alias="x-api-key")):
    """Endpoint temporal para integrar y probar el simulador local."""
    require_key(x_api_key)

    all_nodes = {
        node
        for item in body.zombies
        for node in (item.nodo, item.nodoAnterior, *item.trayecto)
        if node is not None
    }
    all_nodes.update(
        node
        for item in body.sobrevivientes
        for node in (item.nodo, item.nodoAnterior, item.siguienteNodo, *item.trayecto, *item.ruta)
        if node is not None
    )
    all_nodes.update(refuge.nodo for refuge in body.refugios)
    for node in all_nodes:
        require_node(node)
    for edge in body.aristasBloqueadas:
        require_edge(edge)
    for event in body.eventos:
        if event.nodo:
            require_node(event.nodo)
        if event.arista:
            require_edge(event.arista)

    previous = store.get()
    previous_decisions = dict(_decisions)
    previous_routes = dict(_routes)
    previous_targets = dict(_targets)
    normalized = body.model_copy(update={
        "refugios": [
            refuge.model_copy(update={"capacidad": min(refuge.capacidad, 50)})
            for refuge in body.refugios
        ],
    })
    updated = store.replace(normalized)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, prepare_decisions, updated)
    new_blocked = {
        frozenset(edge) for edge in updated.aristasBloqueadas
    } - {
        frozenset(edge) for edge in previous.aristasBloqueadas
    }
    events = [
        *(event for event in previous.eventos if event.id.startswith("API-")),
        *updated.eventos,
    ]
    if new_blocked:
        for survivor in updated.sobrevivientes:
            if not survivor.activo:
                continue
            old_next = previous_decisions.get((previous.turno, survivor.id))
            new_next = _decisions.get((updated.turno, survivor.id))
            old_route = previous_routes.get((previous.turno, survivor.id), [])
            new_route = _routes.get((updated.turno, survivor.id), [])
            if old_next is not None and new_next is not None and old_route != new_route:
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
    for survivor in updated.sobrevivientes:
        if not survivor.activo:
            continue
        old_target = previous_targets.get((previous.turno, survivor.id), survivor.refugio)
        new_target = _targets.get((updated.turno, survivor.id), survivor.refugio)
        if old_target and new_target and old_target != new_target:
            old_refuge = next((refuge for refuge in previous.refugios if refuge.id == old_target), None)
            if old_refuge and old_refuge.ocupados >= old_refuge.capacidad:
                events.append(
                    EventoSimulacion(
                        id=f"API-REFUGIO-LLENO-{updated.turno}-{survivor.id}",
                        turno=updated.turno,
                        tipo="desvio",
                        mensaje=f"{old_refuge.id} lleno; {survivor.id} redirigido a {new_target}",
                        actores=[survivor.id, old_target, new_target],
                        nodo=survivor.nodo,
                    )
                )
    events.sort(key=lambda event: event.turno)
    updated = store.replace(updated.model_copy(update={"eventos": events}))
    await state_hub.publish(updated)
    return updated
