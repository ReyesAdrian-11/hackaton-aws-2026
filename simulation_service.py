from __future__ import annotations

import argparse
import asyncio
import logging
import time
from typing import Any

import httpx
import networkx as nx

from config import API_KEY, BASE_DIR
from simulador import Evento, Simulador, cargar_eventos, construir_simulador
from world_state import store

logger = logging.getLogger(__name__)
DEMO_SURVIVORS = 20
DEMO_WALKERS = 10
DEMO_MAX_TURNS = 150
TURN_INTERVAL_SECONDS = 2.0


class SimulationService:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start_demo(self, graph: nx.MultiDiGraph, api: Any) -> dict[str, int | str]:
        if self.running:
            return {"ronda": 1, "turno": store.get().turno, "estado": "en_curso"}

        args = argparse.Namespace(
            api_url="http://spookython",
            api_key=API_KEY,
            semilla=20261031,
            sobrevivientes=DEMO_SURVIVORS,
            caminantes=DEMO_WALKERS,
            corredores=0,
            hordas=0,
            dormidos=0,
            turnos=DEMO_MAX_TURNS,
        )
        simulator = construir_simulador(args, graph=graph, zombies_en_zonas=True)
        events = cargar_eventos(BASE_DIR / "eventos.json")
        valid_events = []
        for event in events:
            if len(event.arista) == 2 and (
                graph.has_edge(*event.arista) or graph.has_edge(*reversed(event.arista))
            ):
                valid_events.append(event)
            else:
                logger.warning(
                    "Se omite evento con arista inexistente: turno=%d arista=%s nombre=%s",
                    event.turno,
                    event.arista,
                    event.nombre,
                )

        self._task = asyncio.create_task(
            self._run_round(simulator, valid_events, api),
            name="spookython-demo-round-1",
        )
        return {"ronda": 1, "turno": 0, "estado": "iniciando"}

    async def stop(self) -> None:
        if self._task is None or self._task.done():
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            logger.info("Simulación cancelada durante el cierre del servidor.")

    async def _run_round(
        self,
        simulator: Simulador,
        events: list[Evento],
        api: Any,
    ) -> None:
        transport = httpx.ASGITransport(app=api)
        limits = httpx.Limits(max_connections=250, max_keepalive_connections=250)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=simulator.api_url,
            timeout=simulator.timeout,
            limits=limits,
        ) as client:
            try:
                await simulator.publicar_estado(client)
                for _ in range(DEMO_MAX_TURNS):
                    if not any(survivor.activo for survivor in simulator.mundo.sobrevivientes.values()):
                        break
                    started = time.perf_counter()
                    await simulator.ejecutar_turno(events, client)
                    elapsed = time.perf_counter() - started
                    await asyncio.sleep(max(0, TURN_INTERVAL_SECONDS - elapsed))

                simulator.simulacion = "completada"
                await simulator.publicar_estado(client)
                logger.info(
                    "Ronda demo completada: turno=%d salvos=%d mordidos=%d",
                    simulator.mundo.turno,
                    sum(survivor.a_salvo for survivor in simulator.mundo.sobrevivientes.values()),
                    sum(survivor.mordido for survivor in simulator.mundo.sobrevivientes.values()),
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Falló la Ronda 1 de demostración.")
                current = store.get()
                store.replace(current.model_copy(update={"simulacion": "error"}))
