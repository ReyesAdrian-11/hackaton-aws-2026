import networkx as nx
from models import Zombie
from routing import next_safe_node


def sample_graph():
    graph = nx.MultiDiGraph()
    graph.add_edge("N-0000", "N-0001", length=1)
    graph.add_edge("N-0001", "N-0002", length=1)
    graph.add_edge("N-0000", "N-0003", length=2)
    graph.add_edge("N-0003", "N-0002", length=2)
    return graph


def test_shortest_path_first_step():
    assert next_safe_node(sample_graph(), "N-0000", "N-0002", [], []) == "N-0001"


def test_avoids_zombie():
    zombie = Zombie(id="Z-1", tipo="caminante", nodo="N-0001")
    assert next_safe_node(sample_graph(), "N-0000", "N-0002", [zombie], []) == "N-0003"


def test_avoids_blocked_edge():
    assert next_safe_node(sample_graph(), "N-0000", "N-0002", [], [["N-0000", "N-0001"]]) == "N-0003"
