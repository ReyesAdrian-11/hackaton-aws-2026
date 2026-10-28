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
        self._nodes_geojson: dict | None = None
        self._edges_geojson: dict | None = None

    def load(self, path: Path):
        self.graph = ox.load_graphml(path)
        nodes = sorted(self.graph.nodes(), key=str)
        self.game_to_osm = {f"N-{i:04d}": node for i, node in enumerate(nodes)}
        self.osm_to_game = {node: game for game, node in self.game_to_osm.items()}
        self._game_graph = nx.relabel_nodes(self.graph, self.osm_to_game, copy=True)
        # The game models streets as traversable connections. OSM can encode
        # one-way traffic, but keeping that direction in the simulation makes
        # valid refuge destinations unreachable and leaves survivors frozen.
        # Keep the original directed graph for map export and add reverse
        # gameplay edges only when the opposite street is absent.
        for source, target, key, data in tuple(self._game_graph.edges(keys=True, data=True)):
            if not self._game_graph.has_edge(target, source):
                self._game_graph.add_edge(target, source, **dict(data))
        self._nodes_geojson = None
        self._edges_geojson = None

    def game_graph(self):
        if self._game_graph is None:
            raise RuntimeError("El grafo no está cargado")
        return self._game_graph

    def has_node(self, node: str) -> bool:
        return node in self.game_to_osm

    def metadata(self):
        return {"nodos": len(self.game_to_osm), "aristas": self.graph.number_of_edges() if self.graph else 0}

    def nodes_geojson(self):
        if self._nodes_geojson is not None:
            return self._nodes_geojson
        if self.graph is None:
            raise RuntimeError("El grafo no está cargado")
        features = []
        for game_id, osm_id in self.game_to_osm.items():
            attrs = self.graph.nodes[osm_id]
            features.append({"type": "Feature", "properties": {"id": game_id}, "geometry": {"type": "Point", "coordinates": [float(attrs["x"]), float(attrs["y"])]}})
        self._nodes_geojson = {"type": "FeatureCollection", "features": features}
        return self._nodes_geojson

    def edges_geojson(self):
        if self._edges_geojson is not None:
            return self._edges_geojson
        if self.graph is None:
            raise RuntimeError("El grafo no está cargado")

        features = []
        for source, target, key, attrs in self.graph.edges(keys=True, data=True):
            source_id = self.osm_to_game[source]
            target_id = self.osm_to_game[target]
            geometry = attrs.get("geometry")
            if geometry is None:
                source_attrs = self.graph.nodes[source]
                target_attrs = self.graph.nodes[target]
                coordinates = [
                    [float(source_attrs["x"]), float(source_attrs["y"])],
                    [float(target_attrs["x"]), float(target_attrs["y"])],
                ]
            else:
                coordinates = [
                    [float(point[0]), float(point[1])]
                    for point in geometry.coords
                ]
            features.append({
                "type": "Feature",
                "id": f"{source_id}:{target_id}:{key}",
                "properties": {
                    "origen": source_id,
                    "destino": target_id,
                    "tipo": attrs.get("highway", "unclassified"),
                    "distancia_m": float(attrs.get("length", 0)),
                },
                "geometry": {"type": "LineString", "coordinates": coordinates},
            })

        self._edges_geojson = {"type": "FeatureCollection", "features": features}
        return self._edges_geojson
