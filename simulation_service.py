from __future__ import annotations

import argparse
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
import networkx as nx

from config import API_KEY, BASE_DIR
from simulador import Evento, Simulador, cargar_eventos, construir_simulador
from world_state import store

logger = logging.getLogger(__name__)
DEMO_MAX_TURNS = 150
TURN_INTERVAL_SECONDS = 2.0


@dataclass(frozen=True)
class RoundConfig:
    survivors: int
    walkers: int
    runners: int = 0
    hordes: int = 0
    sleepers: int = 0
    event_turns: tuple[int, ...] = ()


ROUND_CONFIGS = {
    1: RoundConfig(survivors=20, walkers=10),
    2: RoundConfig(survivors=80, walkers=30, runners=15, hordes=5, event_turns=(40,)),
    3: RoundConfig(
        survivors=200,
        walkers=70,
        runners=50,
        hordes=10,
        sleepers=20,
        event_turns=(85, 110),
    ),
}


class SimulationService:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._round: int | None = None
        self._start_lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def round_number(self) -> int | None:
        return self._round

    async def start_demo(
        self,
        round_number: int,
        graph: nx.MultiDiGraph,
        api: Any,
    ) -> dict[str, int | str]:
        if round_number not in ROUND_CONFIGS:
            raise ValueError(f"Ronda no configurada: {round_number}.")

        async with self._start_lock:
            if self.running and self._round == round_number:
                return {"ronda": round_number, "turno": store.get().turno, "estado": "en_curso"}
            if self.running:
                await self.stop()

            round_config = ROUND_CONFIGS[round_number]
            args = argparse.Namespace(
                api_url="http://spookython",
                api_key=API_KEY,
                semilla=20261031 + round_number,
                sobrevivientes=round_config.survivors,
                caminantes=round_config.walkers,
                corredores=round_config.runners,
                hordas=round_config.hordes,
                dormidos=round_config.sleepers,
                turnos=DEMO_MAX_TURNS,
            )
            simulator = construir_simulador(
                args,
                graph=graph,
                zombies_en_zonas=True,
                ronda=round_number,
            )
            events = [
                event
                for event in cargar_eventos(BASE_DIR / "eventos.json")
                if event.turno in round_config.event_turns
            ]
            valid_events = []
            for event in events:
                if len(event.arista) == 2 and (
                    graph.has_edge(*event.arista) or graph.has_edge(*reversed(event.arista))
                ):
                    valid_events.append(event)
                else:
                    logger.warning(
                        "Se omite evento con arista inexistente: ronda=%d turno=%d arista=%s nombre=%s",
                        round_number,
                        event.turno,
                        event.arista,
                        event.nombre,
                    )

            self._round = round_number
            self._task = asyncio.create_task(
                self._run_round(simulator, valid_events, api),
                name=f"spookython-demo-round-{round_number}",
            )
            return {"ronda": round_number, "turno": 0, "estado": "iniciando"}

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
                logger.exception("Falló la Ronda %d de demostración.", simulator.ronda)
                current = store.get()
                store.replace(current.model_copy(update={"simulacion": "error"}))
