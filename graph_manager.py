from __future__ import annotations
from typing import Any
from pathlib import Path
import networkx as nx
import osmnx as ox

class GraphManager:
    def __init__(self):
        self.graph = None
        self._game_graph = None
        self.game_to_osm: dict[str, Any] = {}
        self.osm_to_game: dict[Any, str] = {}

    def load(self, path: Path):
        self.graph = ox.load_graphml(path)
        nodes = sorted(self.graph.nodes(), key=str)
        self.game_to_osm = {f"N-{i:04d}": node for i, node in enumerate(nodes)}
        self.osm_to_game = {node: game for game, node in self.game_to_osm.items()}
        self._game_graph = nx.relabel_nodes(self.graph, self.osm_to_game, copy=True)

    def game_graph(self):
        if self._game_graph is None:
            raise RuntimeError("El grafo no está cargado")
        return self._game_graph

    def has_node(self, node: str) -> bool:
        return node in self.game_to_osm

    def metadata(self):
        return {"nodos": len(self.game_to_osm), "aristas": self.graph.number_of_edges() if self.graph else 0}

    def nodes_geojson(self):
        features = []
        for game_id, osm_id in self.game_to_osm.items():
            attrs = self.graph.nodes[osm_id]
            features.append({"type": "Feature", "properties": {"id": game_id}, "geometry": {"type": "Point", "coordinates": [float(attrs["x"]), float(attrs["y"])]}})
        return {"type": "FeatureCollection", "features": features}
