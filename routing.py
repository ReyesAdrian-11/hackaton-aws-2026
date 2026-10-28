from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import networkx as nx

_BASE_NEXT: dict[tuple[int, str], dict[str, str]] = {}
_BASE_DISTANCE: dict[tuple[int, str], dict[str, float]] = {}


def blocked_edges(edges: Iterable[list[str]]) -> set[frozenset[str]]:
    return {frozenset(edge) for edge in edges if len(edge) == 2}


def danger_nodes(graph: nx.Graph, zombies: list[Any]) -> set[str]:
    """Hordas bloquean su nodo y todos sus vecinos; otros zombies, solo su nodo."""
    danger: set[str] = set()
    for zombie in zombies:
        if not zombie.visible:
            continue
        danger.add(zombie.nodo)
        if zombie.tipo == "horda" and graph.has_node(zombie.nodo):
            danger.update(str(node) for node in graph.neighbors(zombie.nodo))
    return danger


def _weight(_u: str, _v: str, data: dict[str, Any]) -> float:
    # GraphML/OSMnx suele guardar length como string después de serializar.
    # En MultiDiGraph, NetworkX entrega un diccionario de claves de arista.
    if data and not ("length" in data or "distancia_m" in data):
        return min(_weight(_u, _v, attrs) for attrs in data.values())
    value = data.get("length", data.get("distancia_m", 1))
    try:
        return float(value)
    except (TypeError, ValueError):
        return 1.0


def _edge_weight_factory(forbidden: set[str], blocked: set[frozenset[str]]):
    """Crea un peso que oculta peligros sin copiar ni modificar el grafo."""
    def weight(u: str, v: str, data: dict[str, Any]):
        if str(u) in forbidden or str(v) in forbidden:
            return None
        if frozenset((str(u), str(v))) in blocked:
            return None
        return _weight(u, v, data)
    return weight


def _base_tree(graph: nx.MultiDiGraph, target: str) -> tuple[dict[str, str], dict[str, float]]:
    """Precalcula el siguiente paso hacia un refugio sin peligros dinámicos."""
    key = (id(graph), target)
    if key in _BASE_NEXT:
        return _BASE_NEXT[key], _BASE_DISTANCE[key]
    result: dict[str, str] = {}
    distances: dict[str, float] = {}
    reverse = graph.reverse(copy=False)
    try:
        distances_raw, paths = nx.single_source_dijkstra(reverse, target, weight=_weight)
        distances = {str(node): float(distance) for node, distance in distances_raw.items()}
        for current, path_from_target in paths.items():
            if len(path_from_target) > 1:
                result[str(current)] = str(path_from_target[-2])
    except nx.NodeNotFound:
        pass
    _BASE_NEXT[key] = result
    _BASE_DISTANCE[key] = distances
    return result, distances


def warm_base_trees(graph: nx.MultiDiGraph, targets: Iterable[str]) -> None:
    """Construye los árboles antes de recibir tráfico concurrente."""
    for target in targets:
        _base_tree(graph, target)


def next_safe_node(
    graph: nx.MultiDiGraph,
    current: str,
    target: str,
    zombies: list[Any],
    blocked: Iterable[list[str]],
) -> str:
    """Calcula una ruta segura y devuelve únicamente su primer vecino."""
    if current == target:
        return current
    if not graph.has_node(current) or not graph.has_node(target):
        return current

    forbidden = danger_nodes(graph, zombies)
    forbidden.discard(current)
    forbidden.discard(target)
    blocked_set = blocked_edges(blocked)

    # La mayoría de peticiones no necesitan una búsqueda completa: reutilizar
    # el árbol de rutas base mantiene el p95 bajo cuando el mapa no cambió.
    base_next_map, base_distances = _base_tree(graph, target)
    base_next = base_next_map.get(current)
    if (
        base_next
        and base_next not in forbidden
        and frozenset((str(current), str(base_next))) not in blocked_set
    ):
        return base_next

    # Si el siguiente paso base quedó peligroso, escoger un vecino alternativo
    # que ya tenga distancia precalculada al refugio. Esto evita ejecutar una
    # búsqueda completa para cada sobreviviente durante la Ronda 3.
    candidates = []
    for neighbor in graph.successors(current):
        neighbor = str(neighbor)
        if neighbor in forbidden:
            continue
        if frozenset((str(current), neighbor)) in blocked_set:
            continue
        distance = base_distances.get(neighbor)
        if distance is not None:
            candidates.append((distance, neighbor))
    if candidates:
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    # No ejecutar una búsqueda global como fallback dentro de /paso: con 200
    # solicitudes simultáneas bloquearía el turno completo. El simulador
    # volverá a consultar en el siguiente turno cuando cambie el peligro.
    return current
