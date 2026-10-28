import networkx as nx

from simulador import Evento, Simulador, Sobreviviente, Zombie


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
