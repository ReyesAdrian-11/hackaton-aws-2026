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
from models import EstadoMundo, Refugio
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
        walkers=40,
        runners=25,
        hordes=5,
        sleepers=10,
        event_turns=(85, 110),
    ),
}


class SimulationService:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._round: int | None = None
        self._start_lock = asyncio.Lock()
        self._active_simulator: Simulador | None = None
        self._pending_events: list[Evento] = []

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def round_number(self) -> int | None:
        return self._round

    def inject_block(self, arista: tuple[str, str], nombre: str) -> int | None:
        """Queue a real-time closure for the currently executing tick."""
        simulator = self._active_simulator
        if simulator is None or not self.running:
            return None
        # The current tick may already be inside the zombie/survivor phase;
        # schedule the incident for the next atomic tick so it cannot be lost.
        turno = simulator.mundo.turno + 1
        self._pending_events.append(Evento(turno, "bloqueo", arista, nombre))
        return turno

    def _take_pending_events(self) -> list[Evento]:
        pending = self._pending_events
        self._pending_events = []
        return pending

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
            self._pending_events.clear()
            self._task = asyncio.create_task(
                self._run_round(simulator, valid_events, api),
                name=f"spookython-demo-round-{round_number}",
            )
            return {"ronda": round_number, "turno": 0, "estado": "iniciando"}

    async def start_fire_test(self, graph: nx.MultiDiGraph, api: Any) -> dict[str, int | str]:
        """Start R1, R2 and R3 consecutively as one fire-test session."""
        async with self._start_lock:
            if self.running:
                return {
                    "ronda": self._round or 1,
                    "turno": store.get().turno,
                    "estado": "en_curso",
                }
            self._round = 1
            self._task = asyncio.create_task(
                self._run_fire_test(graph, api),
                name="spookython-fire-test",
            )
            return {"ronda": 1, "turno": 0, "estado": "iniciando"}

    async def _run_fire_test(self, graph: nx.MultiDiGraph, api: Any) -> None:
        previous_refugios = store.get().refugios
        try:
            for round_number in (1, 2, 3):
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
                    args, graph=graph, zombies_en_zonas=True, ronda=round_number
                )
                if previous_refugios:
                    simulator.mundo.refugios = {
                        refuge.id: Refugio(
                            refuge.id,
                            refuge.nodo,
                            refuge.capacidad,
                            refuge.ocupados,
                        )
                        for refuge in previous_refugios
                    }
                events = [
                    event
                    for event in cargar_eventos(BASE_DIR / "eventos.json")
                    if event.turno in round_config.event_turns
                ]
                store.replace(
                    EstadoMundo(
                        turno=0,
                        ronda=round_number,
                        simulacion="en_curso",
                        refugios=previous_refugios,
                    )
                )
                self._round = round_number
                self._active_simulator = simulator
                await self._run_round(simulator, events, api, exact_duration=True)
                self._active_simulator = None
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falló la Prueba de Fuego.")
            current = store.get()
            store.replace(current.model_copy(update={"simulacion": "error"}))

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
        exact_duration: bool = False,
    ) -> None:
        self._active_simulator = simulator
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
                    if (
                        not exact_duration
                        and not any(
                            survivor.activo
                            for survivor in simulator.mundo.sobrevivientes.values()
                        )
                    ):
                        break
                    started = time.perf_counter()
                    live_events = [*events, *self._take_pending_events()]
                    await simulator.ejecutar_turno(live_events, client)
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
            finally:
                if self._active_simulator is simulator:
                    self._active_simulator = None
