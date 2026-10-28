import asyncio

import networkx as nx
import pytest
from fastapi import HTTPException

import main
from config import API_KEY
from main import get_estado, require_edge, start_demo
from models import EstadoMundo, Refugio, RondaInicioResponse, Sobreviviente


def test_get_estado_publishes_backend_decision(monkeypatch):
    world = EstadoMundo(
        turno=14,
        ronda=1,
        simulacion="en_curso",
        sobrevivientes=[Sobreviviente(id="S-1", nodo="N-0000")],
    )

    class StaticStore:
        def get(self):
            return world

    monkeypatch.setattr("main.store", StaticStore())
    monkeypatch.setattr("main._decisions", {(14, "S-1"): "N-0001"})
    monkeypatch.setattr("main._routes", {(14, "S-1"): ["N-0000", "N-0001"]})
    monkeypatch.setattr("main._targets", {(14, "S-1"): "R-001"})

    response = asyncio.run(get_estado())

    assert response.sobrevivientes[0].siguienteNodo == "N-0001"
    assert response.sobrevivientes[0].ruta == ["N-0000", "N-0001"]
    assert response.sobrevivientes[0].refugio == "R-001"
    assert response.ronda == 1


def test_require_edge_rejects_edges_outside_the_road_graph(monkeypatch):
    graph = nx.MultiDiGraph()
    graph.add_edge("N-0000", "N-0001")

    class StaticGraphManager:
        def has_node(self, node):
            return graph.has_node(node)

        def game_graph(self):
            return graph

    monkeypatch.setattr("main.graphs", StaticGraphManager())

    with pytest.raises(HTTPException) as error:
        require_edge(["N-0000", "N-0002"])

    assert error.value.status_code == 422


def test_full_assigned_refuge_redirects_survivor_to_available_nearest_refuge(monkeypatch):
    graph = nx.MultiDiGraph()
    graph.add_edge("N-0000", "N-0001", length=1)
    graph.add_edge("N-0001", "N-0002", length=1)

    class StaticGraphManager:
        def game_graph(self):
            return graph

    world = EstadoMundo(
        turno=7,
        ronda=2,
        simulacion="en_curso",
        sobrevivientes=[Sobreviviente(id="S-1", nodo="N-0000", refugio="R-001")],
        refugios=[
            Refugio(id="R-001", nodo="N-0002", capacidad=1, ocupados=1),
            Refugio(id="R-002", nodo="N-0001", capacidad=5, ocupados=0),
        ],
    )
    monkeypatch.setattr("main.graphs", StaticGraphManager())

    main.prepare_decisions(world)

    assert main._targets[(7, "S-1")] == "R-002"
    assert main._routes[(7, "S-1")] == ["N-0000", "N-0001"]
    assert main._decisions[(7, "S-1")] == "N-0001"

    class StaticStore:
        def get_turno(self):
            return 7

    monkeypatch.setattr("main.store", StaticStore())
    response = asyncio.run(main.get_pasos(API_KEY))

    assert response["decisiones"] == {"S-1": "N-0001"}
    assert response["destinos"] == {"S-1": "R-002"}


def test_prepare_decisions_reserves_refuge_capacity(monkeypatch):
    graph = nx.MultiDiGraph()
    graph.add_edge("N-0000", "N-0001", length=1)
    graph.add_edge("N-0001", "N-0002", length=1)
    graph.add_edge("N-0000", "N-0003", length=1)
    graph.add_edge("N-0003", "N-0004", length=1)

    class StaticGraphManager:
        def game_graph(self):
            return graph

    world = EstadoMundo(
        turno=3,
        sobrevivientes=[
            Sobreviviente(id="S-1", nodo="N-0000", refugio="R-001"),
            Sobreviviente(id="S-2", nodo="N-0000", refugio="R-001"),
        ],
        refugios=[
            Refugio(id="R-001", nodo="N-0002", capacidad=1, ocupados=0),
            Refugio(id="R-002", nodo="N-0004", capacidad=5, ocupados=0),
        ],
    )
    monkeypatch.setattr("main.graphs", StaticGraphManager())

    main.prepare_decisions(world)

    assert main._targets[(3, "S-1")] == "R-001"
    assert main._targets[(3, "S-2")] == "R-002"


def test_start_demo_resets_completed_world_and_route_cache(monkeypatch):
    class MutableStore:
        def __init__(self):
            self.world = EstadoMundo(ronda=1, turno=102, simulacion="completada")

        def get(self):
            return self.world

        def replace(self, world):
            self.world = world

    class IdleSimulationService:
        running = False

        round_number = None

        async def start_demo(self, round_number, graph, api):
            return {"ronda": round_number, "turno": 0, "estado": "iniciando"}

    class EmptyGraphManager:
        def game_graph(self):
            return nx.MultiDiGraph()

    state_store = MutableStore()
    decisions = {(102, "S-001"): "N-0002"}
    routes = {(102, "S-001"): ["N-0001", "N-0002"]}
    targets = {(102, "S-001"): "R-001"}
    monkeypatch.setattr("main.store", state_store)
    monkeypatch.setattr("main.graphs", EmptyGraphManager())
    monkeypatch.setattr("main.simulation_service", IdleSimulationService())
    monkeypatch.setattr("main.initial_state", lambda: EstadoMundo(turno=0, simulacion="detenida"))
    monkeypatch.setattr("main._decisions", decisions)
    monkeypatch.setattr("main._routes", routes)
    monkeypatch.setattr("main._targets", targets)

    response: RondaInicioResponse = asyncio.run(start_demo())

    assert response.estado == "iniciando"
    assert state_store.get().turno == 0
    assert state_store.get().simulacion == "iniciando"
    assert state_store.get().ronda == 1
    assert not decisions
    assert not routes
    assert not targets
