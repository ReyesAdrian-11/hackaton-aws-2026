import asyncio
from types import SimpleNamespace

import networkx as nx

from models import EstadoMundo
from simulation_service import ROUND_CONFIGS, SimulationService


def test_demo_start_is_idempotent_while_round_is_running(monkeypatch):
    monkeypatch.setattr(
        "simulation_service.construir_simulador",
        lambda *args, **kwargs: SimpleNamespace(mundo=SimpleNamespace(turno=4)),
    )
    monkeypatch.setattr("simulation_service.cargar_eventos", lambda path: [])
    service = SimulationService()

    async def hold_round(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(service, "_run_round", hold_round)

    async def verify_start():
        first = await service.start_demo(1, nx.MultiDiGraph(), object())
        second = await service.start_demo(1, nx.MultiDiGraph(), object())
        await service.stop()
        return first, second

    first, second = asyncio.run(verify_start())

    assert first["estado"] == "iniciando"
    assert second["estado"] == "en_curso"
    assert second["turno"] == 0


def test_demo_can_start_again_after_completed_round(monkeypatch):
    class CompletedStore:
        def get(self):
            return EstadoMundo(ronda=1, turno=102, simulacion="completada")

    monkeypatch.setattr("simulation_service.store", CompletedStore())
    monkeypatch.setattr(
        "simulation_service.construir_simulador",
        lambda *args, **kwargs: SimpleNamespace(mundo=SimpleNamespace(turno=0)),
    )
    monkeypatch.setattr("simulation_service.cargar_eventos", lambda path: [])
    service = SimulationService()

    async def finish_round(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "_run_round", finish_round)

    async def verify_restart():
        result = await service.start_demo(1, nx.MultiDiGraph(), object())
        if service._task is not None:
            await service._task
        return result

    result = asyncio.run(verify_restart())

    assert result["estado"] == "iniciando"


def test_round_configs_match_the_challenge():
    assert ROUND_CONFIGS[1].survivors == 20
    assert (ROUND_CONFIGS[1].walkers, ROUND_CONFIGS[1].runners, ROUND_CONFIGS[1].hordes, ROUND_CONFIGS[1].sleepers) == (10, 0, 0, 0)
    assert ROUND_CONFIGS[1].event_turns == ()

    assert ROUND_CONFIGS[2].survivors == 80
    assert (ROUND_CONFIGS[2].walkers, ROUND_CONFIGS[2].runners, ROUND_CONFIGS[2].hordes, ROUND_CONFIGS[2].sleepers) == (30, 15, 5, 0)
    assert len(ROUND_CONFIGS[2].event_turns) == 1

    assert ROUND_CONFIGS[3].survivors == 200
    assert (ROUND_CONFIGS[3].walkers, ROUND_CONFIGS[3].runners, ROUND_CONFIGS[3].hordes, ROUND_CONFIGS[3].sleepers) == (40, 25, 5, 10)
    assert len(ROUND_CONFIGS[3].event_turns) == 2


def test_switching_round_cancels_the_previous_round(monkeypatch):
    monkeypatch.setattr(
        "simulation_service.construir_simulador",
        lambda *args, **kwargs: SimpleNamespace(mundo=SimpleNamespace(turno=0)),
    )
    monkeypatch.setattr("simulation_service.cargar_eventos", lambda path: [])
    service = SimulationService()
    started_rounds = []

    async def hold_round(simulator, events, api):
        started_rounds.append(simulator)
        await asyncio.Event().wait()

    monkeypatch.setattr(service, "_run_round", hold_round)

    async def verify_switch():
        await service.start_demo(1, nx.MultiDiGraph(), object())
        await asyncio.sleep(0)
        result = await service.start_demo(2, nx.MultiDiGraph(), object())
        await asyncio.sleep(0)
        await service.stop()
        return result

    result = asyncio.run(verify_switch())

    assert len(started_rounds) == 2
    assert result["ronda"] == 2
    assert service.round_number == 2


def test_round_start_uses_matching_population_and_city_events(monkeypatch):
    captured = []
    events = [
        SimpleNamespace(turno=40, arista=("N-0000", "N-0001")),
        SimpleNamespace(turno=85, arista=("N-0000", "N-0001")),
        SimpleNamespace(turno=110, arista=("N-0000", "N-0001")),
    ]
    graph = nx.MultiDiGraph()
    graph.add_edge("N-0000", "N-0001")

    def build(args, *, graph, zombies_en_zonas, ronda):
        captured.append((ronda, args, zombies_en_zonas))
        return SimpleNamespace(mundo=SimpleNamespace(turno=0), api_url="http://test", timeout=1, ronda=ronda)

    monkeypatch.setattr("simulation_service.construir_simulador", build)
    monkeypatch.setattr("simulation_service.cargar_eventos", lambda path: events)
    service = SimulationService()

    async def hold_round(simulator, round_events, api):
        captured[-1] += (round_events,)
        await asyncio.Event().wait()

    monkeypatch.setattr(service, "_run_round", hold_round)

    async def run_rounds():
        for round_number in (1, 2, 3):
            await service.start_demo(round_number, graph, object())
            await asyncio.sleep(0)
            await service.stop()

    asyncio.run(run_rounds())

    assert len(captured) == 3
    expected = {
        1: (20, 10, 0, 0, 0, []),
        2: (80, 30, 15, 5, 0, [40]),
        3: (200, 40, 25, 5, 10, [85, 110]),
    }
    for round_number, args, uses_zones, round_events in captured:
        assert uses_zones
        assert (
            args.sobrevivientes,
            args.caminantes,
            args.corredores,
            args.hordas,
            args.dormidos,
            [event.turno for event in round_events],
        ) == expected[round_number]
