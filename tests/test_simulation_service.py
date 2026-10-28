import asyncio

import networkx as nx

from models import EstadoMundo
from simulation_service import SimulationService


def test_demo_start_is_idempotent_while_round_is_running(monkeypatch):
    monkeypatch.setattr("simulation_service.construir_simulador", lambda *args, **kwargs: object())
    monkeypatch.setattr("simulation_service.cargar_eventos", lambda path: [])
    service = SimulationService()

    async def verify_start():
        first = service.start_demo(nx.MultiDiGraph(), object())
        second = service.start_demo(nx.MultiDiGraph(), object())
        await service.stop()
        return first, second

    first, second = asyncio.run(verify_start())

    assert first["estado"] == "iniciando"
    assert second["estado"] == "en_curso"


def test_demo_can_start_again_after_completed_round(monkeypatch):
    class CompletedStore:
        def get(self):
            return EstadoMundo(ronda=1, turno=102, simulacion="completada")

    monkeypatch.setattr("simulation_service.store", CompletedStore())
    monkeypatch.setattr("simulation_service.construir_simulador", lambda *args, **kwargs: object())
    monkeypatch.setattr("simulation_service.cargar_eventos", lambda path: [])
    service = SimulationService()

    async def finish_round(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "_run_round", finish_round)

    async def verify_restart():
        result = service.start_demo(nx.MultiDiGraph(), object())
        if service._task is not None:
            await service._task
        return result

    result = asyncio.run(verify_restart())

    assert result["estado"] == "iniciando"
