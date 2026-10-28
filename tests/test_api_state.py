import asyncio

import networkx as nx
import pytest
from fastapi import HTTPException

from main import get_estado, require_edge, start_demo
from models import EstadoMundo, RondaInicioResponse, Sobreviviente


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

    response = asyncio.run(get_estado())

    assert response.sobrevivientes[0].siguienteNodo == "N-0001"
    assert response.sobrevivientes[0].ruta == ["N-0000", "N-0001"]
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

        def start_demo(self, graph, api):
            return {"ronda": 1, "turno": 0, "estado": "iniciando"}

    class EmptyGraphManager:
        def game_graph(self):
            return nx.MultiDiGraph()

    state_store = MutableStore()
    decisions = {(102, "S-001"): "N-0002"}
    routes = {(102, "S-001"): ["N-0001", "N-0002"]}
    monkeypatch.setattr("main.store", state_store)
    monkeypatch.setattr("main.graphs", EmptyGraphManager())
    monkeypatch.setattr("main.simulation_service", IdleSimulationService())
    monkeypatch.setattr("main.initial_state", lambda: EstadoMundo(turno=0, simulacion="detenida"))
    monkeypatch.setattr("main._decisions", decisions)
    monkeypatch.setattr("main._routes", routes)

    response: RondaInicioResponse = asyncio.run(start_demo())

    assert response.estado == "iniciando"
    assert state_store.get().turno == 0
    assert state_store.get().simulacion == "detenida"
    assert not decisions
    assert not routes
