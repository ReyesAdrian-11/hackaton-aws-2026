"""Simulador local de Escape de Manta.

El simulador es la fuente de verdad de la partida. El backend solo recomienda
el siguiente nodo mediante POST /paso; aquí se validan y aplican las decisiones.

Ejemplo:
    python simulador.py --sobrevivientes 20 --caminantes 10 --turnos 20
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import httpx
import networkx as nx
import osmnx as ox

from config import BASE_DIR, GRAPHML_PATH, REFUGES_PATH
from graph_manager import GraphManager

logger = logging.getLogger("spookython.simulador")


@dataclass
class Zombie:
    id: str
    tipo: str
    nodo: str
    visible: bool = True
    activo: bool = True
    recorridas: list[tuple[str, str]] = field(default_factory=list)
    nodo_anterior: str | None = None


@dataclass
class Sobreviviente:
    id: str
    nodo: str
    refugio: str
    activo: bool = True
    a_salvo: bool = False
    mordido: bool = False
    nodo_anterior: str | None = None


@dataclass
class Refugio:
    id: str
    nodo: str
    capacidad: int
    ocupados: int = 0


@dataclass
class Evento:
    turno: int
    tipo: str
    arista: tuple[str, str]
    nombre: str


@dataclass
class Mundo:
    turno: int = 0
    zombies: dict[str, Zombie] = field(default_factory=dict)
    sobrevivientes: dict[str, Sobreviviente] = field(default_factory=dict)
    refugios: dict[str, Refugio] = field(default_factory=dict)
    aristas_bloqueadas: set[frozenset[str]] = field(default_factory=set)
    eventos: list[dict[str, Any]] = field(default_factory=list)
    siguiente_evento: int = 1
    movimientos_zombies: dict[str, list[tuple[str, str]]] = field(default_factory=dict)

    def visible_zombies(self) -> list[Zombie]:
        return [z for z in self.zombies.values() if z.activo and z.visible]


class Simulador:
    def __init__(
        self,
        graph: nx.MultiDiGraph,
        api_url: str = "http://127.0.0.1:8000",
        api_key: str = "dev-secret-key",
        seed: int = 20261031,
        timeout: float = 0.50,
        max_concurrency: int = 250,
        ronda: int = 1,
    ) -> None:
        self.graph = graph
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.rng = random.Random(seed)
        self.timeout = timeout
        self.ronda = ronda
        self.simulacion = "en_curso"
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.mundo = Mundo()
        self.latencias_ms: list[float] = []
        self.timeouts = 0
        self.errores_api = 0

    def vecinos(self, nodo: str) -> list[str]:
        if not self.graph.has_node(nodo):
            return []
        return [str(v) for v in self.graph.successors(nodo) if str(v) != nodo]

    def arista_disponible(self, origen: str, destino: str) -> bool:
        return (
            self.graph.has_edge(origen, destino)
            and frozenset((origen, destino)) not in self.mundo.aristas_bloqueadas
        )

    def vecinos_disponibles(self, nodo: str) -> list[str]:
        return [v for v in self.vecinos(nodo) if self.arista_disponible(nodo, v)]

    def registrar_evento(
        self,
        tipo: str,
        mensaje: str,
        actores: list[str] | None = None,
        nodo: str | None = None,
        arista: tuple[str, str] | None = None,
    ) -> None:
        event: dict[str, Any] = {
            "id": f"EV-{self.mundo.siguiente_evento:05d}",
            "turno": self.mundo.turno,
            "tipo": tipo,
            "mensaje": mensaje,
            "actores": actores or [],
            "nodo": nodo,
            "arista": list(arista) if arista else None,
        }
        self.mundo.siguiente_evento += 1
        self.mundo.eventos.append(event)
        del self.mundo.eventos[:-100]

    def distancia_saltos(self, origen: str, destino: str, limite: int | None = None) -> int | None:
        if origen == destino:
            return 0
        try:
            if limite is not None:
                distances = nx.single_source_shortest_path_length(self.graph, origen, cutoff=limite)
                return distances.get(destino)
            return nx.shortest_path_length(self.graph, origen, destino)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def _mover_caminantes(self) -> None:
        if self.mundo.turno % 2 != 0:
            return
        for zombie in self.mundo.zombies.values():
            if not zombie.activo or zombie.tipo != "caminante":
                continue
            opciones = self.vecinos_disponibles(zombie.nodo)
            if opciones:
                destino = self.rng.choice(opciones)
                zombie.recorridas = [(zombie.nodo, destino)]
                zombie.nodo = destino

    def _objetivo_corredor(self, zombie: Zombie) -> str | None:
        candidatos: list[tuple[int, str]] = []
        for survivor in self.mundo.sobrevivientes.values():
            if not survivor.activo:
                continue
            distancia = self.distancia_saltos(zombie.nodo, survivor.nodo, limite=3)
            if distancia is not None and distancia <= 3:
                candidatos.append((distancia, survivor.id))
        if not candidatos:
            return None
        candidatos.sort()
        return self.mundo.sobrevivientes[candidatos[0][1]].nodo

    def _siguiente_hacia(self, origen: str, destino: str) -> str | None:
        """Primer paso mediante BFS limitado; los corredores solo detectan 3 saltos."""
        if origen == destino:
            return origen
        queue = [origen]
        parent = {origen: None}
        depth = {origen: 0}
        cursor = 0
        while cursor < len(queue):
            current = queue[cursor]
            cursor += 1
            if depth[current] >= 3:
                continue
            for neighbor in self.vecinos_disponibles(current):
                if neighbor in parent:
                    continue
                parent[neighbor] = current
                depth[neighbor] = depth[current] + 1
                queue.append(neighbor)
                if neighbor == destino:
                    step = neighbor
                    while parent[step] != origen:
                        step = parent[step]  # type: ignore[assignment]
                    return step
        return None

    def _mover_corredores(self) -> None:
        for zombie in self.mundo.zombies.values():
            if not zombie.activo or zombie.tipo != "corredor":
                continue
            zombie.recorridas = []
            objetivo = self._objetivo_corredor(zombie)
            for _ in range(2):
                opciones = self.vecinos_disponibles(zombie.nodo)
                if not opciones:
                    break
                destino = self._siguiente_hacia(zombie.nodo, objetivo) if objetivo else None
                if destino not in opciones:
                    destino = self.rng.choice(opciones)
                zombie.recorridas.append((zombie.nodo, destino))
                zombie.nodo = destino

    def _nodos_bloqueados_por_hordas(self) -> set[str]:
        bloqueados: set[str] = set()
        for zombie in self.mundo.zombies.values():
            if zombie.activo and zombie.tipo == "horda":
                bloqueados.add(zombie.nodo)
                bloqueados.update(self.vecinos(zombie.nodo))
        return bloqueados

    def _despertar_dormidos(self) -> None:
        for zombie in self.mundo.zombies.values():
            if not zombie.activo or zombie.tipo != "dormido":
                continue
            cerca = any(
                survivor.activo
                and self.distancia_saltos(zombie.nodo, survivor.nodo, limite=2) is not None
                and self.distancia_saltos(zombie.nodo, survivor.nodo, limite=2) <= 2
                for survivor in self.mundo.sobrevivientes.values()
            )
            if cerca:
                zombie.tipo = "caminante"
                zombie.visible = True
                self.registrar_evento(
                    "despertar",
                    f"{zombie.id} despertó",
                    actores=[zombie.id],
                    nodo=zombie.nodo,
                )

    def aplicar_eventos(self, eventos: Iterable[Evento]) -> None:
        for evento in eventos:
            if evento.turno != self.mundo.turno:
                continue
            if len(evento.arista) != 2 or not (
                self.graph.has_edge(*evento.arista)
                or self.graph.has_edge(*reversed(evento.arista))
            ):
                logger.warning(
                    "Evento omitido: arista inexistente en turno %d: %s (%s)",
                    evento.turno,
                    evento.arista,
                    evento.nombre,
                )
                continue
            self.mundo.aristas_bloqueadas.add(frozenset(evento.arista))
            self.registrar_evento(
                "bloqueo",
                evento.nombre,
                nodo=evento.arista[0],
                arista=evento.arista,
            )

    def mover_zombies(self, eventos: Iterable[Evento] = ()) -> None:
        self.aplicar_eventos(eventos)
        self._despertar_dormidos()
        for zombie in self.mundo.zombies.values():
            zombie.recorridas = []
            zombie.nodo_anterior = zombie.nodo
        self._mover_caminantes()
        self._mover_corredores()

    def _estado_api(self) -> dict:
        return {
            "turno": self.mundo.turno,
            "ronda": self.ronda,
            "simulacion": self.simulacion,
            "zombies": [
                {
                    "id": z.id,
                    "tipo": z.tipo,
                    "nodo": z.nodo,
                    "nodoAnterior": z.nodo_anterior,
                    "trayecto": [
                        z.nodo_anterior or z.nodo,
                        *[destination for _, destination in z.recorridas],
                    ],
                    "visible": z.visible,
                }
                for z in self.mundo.zombies.values() if z.activo
            ],
            "sobrevivientes": [
                {
                    "id": s.id,
                    "nodo": s.nodo,
                    "nodoAnterior": s.nodo_anterior,
                    "trayecto": [s.nodo_anterior or s.nodo, s.nodo],
                    "refugio": s.refugio,
                    "activo": s.activo,
                    "resultado": "rescatado" if s.a_salvo else "mordido" if s.mordido else None,
                }
                for s in self.mundo.sobrevivientes.values()
            ],
            "aristasBloqueadas": [list(edge) for edge in self.mundo.aristas_bloqueadas],
            "eventos": self.mundo.eventos,
            "refugios": [
                {"id": r.id, "nodo": r.nodo, "capacidad": r.capacidad, "ocupados": r.ocupados}
                for r in self.mundo.refugios.values()
            ],
        }

    async def publicar_estado(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            f"{self.api_url}/estado",
            headers={"x-api-key": self.api_key},
            json=self._estado_api(),
        )
        response.raise_for_status()

    async def _pedir_paso(self, client: httpx.AsyncClient, survivor: Sobreviviente) -> tuple[str, str]:
        async with self.semaphore:
            inicio = time.perf_counter()
            try:
                response = await client.post(
                    f"{self.api_url}/paso",
                    headers={"x-api-key": self.api_key},
                    json={"sobrevivienteId": survivor.id, "nodoActual": survivor.nodo, "turno": self.mundo.turno},
                )
                elapsed = (time.perf_counter() - inicio) * 1000
                self.latencias_ms.append(elapsed)
                if response.status_code != 200 or elapsed > self.timeout * 1000:
                    if elapsed > self.timeout * 1000:
                        self.timeouts += 1
                    else:
                        self.errores_api += 1
                    return survivor.id, survivor.nodo
                return survivor.id, str(response.json().get("siguienteNodo", survivor.nodo))
            except (httpx.HTTPError, ValueError):
                elapsed = (time.perf_counter() - inicio) * 1000
                self.latencias_ms.append(elapsed)
                if elapsed > self.timeout * 1000:
                    self.timeouts += 1
                else:
                    self.errores_api += 1
                return survivor.id, survivor.nodo

    def movimiento_valido(self, origen: str, destino: str) -> bool:
        return destino == origen or self.arista_disponible(origen, destino)

    async def mover_sobrevivientes(self, client: httpx.AsyncClient) -> None:
        activos = [s for s in self.mundo.sobrevivientes.values() if s.activo]
        decisiones = await asyncio.gather(*(self._pedir_paso(client, s) for s in activos))
        for survivor_id, destino in decisiones:
            survivor = self.mundo.sobrevivientes[survivor_id]
            if self.movimiento_valido(survivor.nodo, destino) and self.graph.has_node(destino):
                survivor.nodo = destino

    def resolver_resultado(self) -> None:
        visible_zombies = [
            zombie
            for zombie in self.mundo.zombies.values()
            if zombie.activo and zombie.visible
        ]
        for survivor in self.mundo.sobrevivientes.values():
            if not survivor.activo:
                continue
            attacking_zombie = next(
                (zombie for zombie in visible_zombies if zombie.nodo == survivor.nodo),
                None,
            )
            if attacking_zombie is None:
                attacking_zombie = next(
                    (
                        zombie
                        for zombie in visible_zombies
                        if any(
                            survivor.nodo_anterior == destination
                            and survivor.nodo == origin
                            for origin, destination in zombie.recorridas
                        )
                    ),
                    None,
                )
            if attacking_zombie is not None:
                survivor.activo = False
                survivor.mordido = True
                self.registrar_evento(
                    "mordida",
                    f"{attacking_zombie.id} mordió a {survivor.id}",
                    actores=[attacking_zombie.id, survivor.id],
                    nodo=survivor.nodo,
                )
                continue
            refuge = self.mundo.refugios.get(survivor.refugio)
            if refuge and survivor.nodo == refuge.nodo and refuge.ocupados < refuge.capacidad:
                survivor.activo = False
                survivor.a_salvo = True
                refuge.ocupados += 1
                self.registrar_evento(
                    "rescate",
                    f"{survivor.id} llegó a {refuge.id}",
                    actores=[survivor.id, refuge.id],
                    nodo=refuge.nodo,
                )

    async def ejecutar_turno(
        self,
        eventos: Iterable[Evento] = (),
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if client is None:
            limits = httpx.Limits(max_connections=250, max_keepalive_connections=250)
            async with httpx.AsyncClient(timeout=self.timeout, limits=limits) as own_client:
                await self.ejecutar_turno(eventos, own_client)
            return

        for survivor in self.mundo.sobrevivientes.values():
            survivor.nodo_anterior = survivor.nodo
        self.mover_zombies(eventos)
        await self.publicar_estado(client)
        await self.mover_sobrevivientes(client)
        self.resolver_resultado()
        self.mundo.turno += 1
        await self.publicar_estado(client)

    async def ejecutar(
        self,
        turnos: int,
        eventos: Iterable[Evento] = (),
        intervalo: float = 2.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if client is None:
            limits = httpx.Limits(max_connections=250, max_keepalive_connections=250)
            async with httpx.AsyncClient(timeout=self.timeout, limits=limits) as own_client:
                await self.ejecutar(turnos, eventos, intervalo, own_client)
            return

        for _ in range(turnos):
            inicio = time.perf_counter()
            if not any(s.activo for s in self.mundo.sobrevivientes.values()):
                break
            await self.ejecutar_turno(eventos, client)
            duracion = time.perf_counter() - inicio
            logger.info(
                "Turno %d | vivos=%d salvos=%d mordidos=%d duración=%.0fms",
                self.mundo.turno,
                sum(s.activo for s in self.mundo.sobrevivientes.values()),
                sum(s.a_salvo for s in self.mundo.sobrevivientes.values()),
                sum(s.mordido for s in self.mundo.sobrevivientes.values()),
                duracion * 1000,
            )
            await asyncio.sleep(max(0, intervalo - duracion))

    def metricas(self) -> dict[str, float | int]:
        ordered = sorted(self.latencias_ms)
        index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1)) if ordered else 0
        return {
            "peticiones": len(ordered),
            "p95_ms": round(ordered[index], 2) if ordered else 0,
            "max_ms": round(max(ordered), 2) if ordered else 0,
            "timeouts": self.timeouts,
            "errores_api": self.errores_api,
            "salvos": sum(s.a_salvo for s in self.mundo.sobrevivientes.values()),
            "mordidos": sum(s.mordido for s in self.mundo.sobrevivientes.values()),
        }


def construir_simulador(
    args: argparse.Namespace,
    graph: nx.MultiDiGraph | None = None,
    zombies_en_zonas: bool = False,
) -> Simulador:
    if graph is None:
        manager = GraphManager()
        manager.load(GRAPHML_PATH)
        graph = manager.game_graph()
    simulator = Simulador(
        graph,
        api_url=args.api_url,
        api_key=args.api_key,
        seed=args.semilla,
    )
    refuge_data = json.loads(REFUGES_PATH.read_text(encoding="utf-8"))
    refugios = [(item["id"], item["nodo"]) for item in refuge_data]
    for item in refuge_data:
        if simulator.graph.has_node(item["nodo"]):
            simulator.mundo.refugios[item["id"]] = Refugio(item["id"], item["nodo"], item["capacidad"])
    zones_path = BASE_DIR / "zonas_iniciales.json"
    zones = json.loads(zones_path.read_text(encoding="utf-8"))

    def zone_nodes(reference: str) -> list[str]:
        if not simulator.graph.has_node(reference):
            return list(simulator.graph.nodes())
        # La zona utiliza el nodo de referencia y sus vecinos cercanos del grafo.
        candidates = {reference}
        frontier = {reference}
        for _ in range(2):
            next_frontier = set()
            for node in frontier:
                next_frontier.update(str(n) for n in simulator.graph.successors(node))
                next_frontier.update(str(n) for n in simulator.graph.predecessors(node))
            candidates.update(next_frontier)
            frontier = next_frontier
        return sorted(candidates)

    zone_candidates = [zone_nodes(zone["nodoReferencia"]) for zone in zones]
    for i in range(args.sobrevivientes):
        zone_index = i % len(zone_candidates)
        candidates = zone_candidates[zone_index]
        simulator.mundo.sobrevivientes[f"S-{i + 1:04d}"] = Sobreviviente(
            id=f"S-{i + 1:04d}",
            nodo=candidates[(i // len(zone_candidates)) % len(candidates)],
            refugio=refugios[i % len(refugios)][0],
        )
    nodes = sorted(simulator.graph.nodes())
    cantidades = [("caminante", args.caminantes), ("corredor", args.corredores), ("horda", args.hordas), ("dormido", args.dormidos)]
    cursor = len(nodes) // 3
    number = 1
    for tipo, cantidad in cantidades:
        for _ in range(cantidad):
            if zombies_en_zonas and zone_candidates:
                zone = zone_candidates[(number - 1) % len(zone_candidates)]
                node = zone[(number * 7) % len(zone)]
            else:
                node = nodes[cursor % len(nodes)]
            simulator.mundo.zombies[f"Z-{number:04d}"] = Zombie(
                f"Z-{number:04d}",
                tipo,
                node,
                visible=tipo != "dormido",
            )
            cursor += 7
            number += 1
    return simulator


def cargar_eventos(path: Path | None) -> list[Evento]:
    if path is None or not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Evento(int(item["turno"]), item["tipo"], tuple(item["arista"]), item["nombre"]) for item in data]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulador de Escape de Manta")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default="dev-secret-key")
    parser.add_argument("--semilla", type=int, default=20261031)
    parser.add_argument("--sobrevivientes", type=int, default=20)
    parser.add_argument("--caminantes", type=int, default=10)
    parser.add_argument("--corredores", type=int, default=0)
    parser.add_argument("--hordas", type=int, default=0)
    parser.add_argument("--dormidos", type=int, default=0)
    parser.add_argument("--turnos", type=int, default=10)
    parser.add_argument("--eventos", type=Path, default=BASE_DIR / "eventos.json")
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    options = parse_args()
    simulation = construir_simulador(options)
    asyncio.run(simulation.ejecutar(options.turnos, cargar_eventos(options.eventos)))
    logger.info("Métricas finales: %s", simulation.metricas())
