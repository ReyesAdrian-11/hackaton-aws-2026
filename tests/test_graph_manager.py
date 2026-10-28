import networkx as nx

from graph_manager import GraphManager


def test_edges_geojson_includes_stable_nodes_and_fallback_geometry():
    manager = GraphManager()
    manager.graph = nx.MultiDiGraph()
    manager.graph.add_node("osm-a", x=-80.7, y=-0.95)
    manager.graph.add_node("osm-b", x=-80.69, y=-0.94)
    manager.graph.add_edge("osm-a", "osm-b", length="120.5", highway="residential")
    manager.osm_to_game = {"osm-a": "N-0000", "osm-b": "N-0001"}

    result = manager.edges_geojson()

    assert result["type"] == "FeatureCollection"
    assert result["features"] == [{
        "type": "Feature",
        "id": "N-0000:N-0001:0",
        "properties": {
            "origen": "N-0000",
            "destino": "N-0001",
            "tipo": "residential",
            "distancia_m": 120.5,
        },
        "geometry": {
            "type": "LineString",
            "coordinates": [[-80.7, -0.95], [-80.69, -0.94]],
        },
    }]
