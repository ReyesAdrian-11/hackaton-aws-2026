import networkx as nx
from models import Zombie
from routing import next_safe_node, safe_route_tree, route_from_tree


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


def test_safe_route_tree_returns_complete_route_around_zombie_and_blocked_edge():
    graph = sample_graph()
    graph.add_edge("N-0000", "N-0004")
    graph.add_edge("N-0004", "N-0002")
    zombie = Zombie(id="Z-1", tipo="caminante", nodo="N-0001")
    tree = safe_route_tree(
        graph,
        "N-0002",
        [zombie],
        [["N-0000", "N-0003"]],
    )

    assert route_from_tree(tree, "N-0000", "N-0002") == [
        "N-0000",
        "N-0004",
        "N-0002",
    ]


def test_route_weight_uses_street_speed_not_only_distance():
    graph = nx.MultiDiGraph()
    graph.add_edge("N-0000", "N-0001", length=5, highway="primary")
    graph.add_edge("N-0001", "N-0003", length=5, highway="primary")
    graph.add_edge("N-0000", "N-0002", length=20, highway="residential")
    graph.add_edge("N-0002", "N-0003", length=20, highway="residential")

    # The primary route is longer in meters but faster in travel time.
    assert next_safe_node(graph, "N-0000", "N-0003", [], []) == "N-0001"
