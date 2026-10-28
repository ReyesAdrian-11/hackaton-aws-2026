from argparse import Namespace
import json
import math
from pathlib import Path

import networkx as nx

from models import EstadoMundo
from simulador import Evento, Simulador, Sobreviviente, Zombie, construir_simulador


def make_sim():
    graph = nx.MultiDiGraph()
    graph.add_edge("N-0000", "N-0001")
    graph.add_edge("N-0001", "N-0002")
    graph.add_edge("N-0002", "N-0003")
    graph.add_edge("N-0003", "N-0002")
    return Simulador(graph)


def test_walker_moves_every_two_turns():
    sim = make_sim()
    sim.mundo.zombies["Z-1"] = Zombie("Z-1", "caminante", "N-0000")
    sim.mundo.turno = 1
    sim.mover_zombies()
    assert sim.mundo.zombies["Z-1"].nodo == "N-0000"
    sim.mundo.turno = 2
    sim.mover_zombies()
    assert sim.mundo.zombies["Z-1"].nodo == "N-0001"


def test_sleeping_zombie_wakes_with_survivor_two_hops_away():
    sim = make_sim()
    sim.mundo.zombies["Z-1"] = Zombie("Z-1", "dormido", "N-0000", visible=False)
    sim.mundo.sobrevivientes["S-1"] = Sobreviviente("S-1", "N-0002", "R-1")
    sim.mover_zombies()
    assert sim.mundo.zombies["Z-1"].tipo == "caminante"
    assert sim.mundo.zombies["Z-1"].visible is True


def test_city_event_blocks_edge():
    sim = make_sim()
    sim.mover_zombies([Evento(0, "bloqueo", ("N-0000", "N-0001"), "Puente")])
    assert frozenset(("N-0000", "N-0001")) in sim.mundo.aristas_bloqueadas


def test_crossing_is_a_bite():
    sim = make_sim()
    survivor = Sobreviviente("S-1", "N-0000", "R-1", nodo_anterior="N-0001")
    sim.mundo.sobrevivientes[survivor.id] = survivor
    sim.mundo.zombies["Z-1"] = Zombie("Z-1", "corredor", "N-0001", recorridas=[("N-0000", "N-0001")])
    sim.resolver_resultado()
    assert survivor.mordido is True
    assert survivor.activo is False
    event = sim._estado_api()["eventos"][-1]
    assert event["tipo"] == "mordida"
    assert event["actores"] == ["Z-1", "S-1"]


def test_hidden_sleeping_zombie_does_not_bite_until_awakened():
    sim = make_sim()
    survivor = Sobreviviente("S-1", "N-0000", "R-1")
    sim.mundo.sobrevivientes[survivor.id] = survivor
    sim.mundo.zombies["Z-1"] = Zombie("Z-1", "dormido", "N-0000", visible=False)

    sim.resolver_resultado()

    assert survivor.activo is True
    assert survivor.mordido is False


def test_api_state_keeps_resolved_survivor_results_and_round():
    sim = make_sim()
    survivor = Sobreviviente("S-1", "N-0000", "R-1", activo=False, a_salvo=True)
    sim.mundo.sobrevivientes[survivor.id] = survivor
    sim.registrar_evento(
        "rescate",
        "S-1 llegó a R-1",
        actores=["S-1", "R-1"],
        nodo="N-0000",
    )

    state = EstadoMundo.model_validate(sim._estado_api())

    assert state.ronda == 1
    assert state.sobrevivientes[0].resultado == "rescatado"
    assert state.eventos[0].mensaje == "S-1 llegó a R-1"


def test_event_history_is_not_trimmed_after_one_hundred_entries():
    sim = make_sim()

    for index in range(150):
        sim.registrar_evento(
            "desvio",
            f"Desvío {index}",
            nodo="N-0000",
        )

    assert len(sim._estado_api()["eventos"]) == 150


def test_demo_spawns_do_not_place_survivors_on_visible_zombie_nodes():
    graph = nx.MultiDiGraph()
    zones = json.loads((Path(__file__).parents[1] / "zonas_iniciales.json").read_text(encoding="utf-8"))
    reference_nodes = {
        "N-1980",
        "N-3100",
        "N-5566",
        "N-2420",
    }
    previous_node = None
    for zone_index, zone in enumerate(zones):
        for node_index in range(125):
            angle = node_index * 2.399963229728653
            distance = 500 * math.sqrt(node_index / 125)
            latitude = zone["lat"] + math.sin(angle) * distance / 111_000
            longitude = zone["lng"] + math.cos(angle) * distance / (
                111_000 * math.cos(math.radians(zone["lat"]))
            )
            generated_id = f"N-{zone_index * 125 + node_index:04d}"
            reference = zone["nodoReferencia"] if node_index == 0 else None
            node_id = reference or (generated_id if generated_id not in reference_nodes else f"X-{generated_id}")
            graph.add_node(node_id, x=longitude, y=latitude)
            if node_index > 0:
                graph.add_edge(previous_node, node_id)
                graph.add_edge(node_id, previous_node)
            previous_node = node_id
        previous_node = None
    args = Namespace(
        api_url="http://test",
        api_key="test-key",
        semilla=20261034,
        sobrevivientes=200,
        caminantes=70,
        corredores=50,
        hordas=10,
        dormidos=20,
    )

    sim = construir_simulador(args, graph=graph, zombies_en_zonas=True, ronda=3)
    zombie_nodes = {zombie.nodo for zombie in sim.mundo.zombies.values()}
    survivor_nodes = {survivor.nodo for survivor in sim.mundo.sobrevivientes.values()}

    assert len(survivor_nodes) == 200
    assert len(zombie_nodes) == 150
    assert survivor_nodes.isdisjoint(zombie_nodes)
