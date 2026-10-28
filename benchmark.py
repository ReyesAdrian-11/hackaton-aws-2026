"""Benchmark de aislamiento del backend."""
import asyncio
import httpx
import time
import pathlib

API_KEY = "dev-secret-key"
URL = "http://127.0.0.1:8000"

ESTADO = {
    "turno": 99,
    "zombies": [
        {"id": f"Z-{i:04d}", "tipo": "caminante", "nodo": "N-0100", "visible": True}
        for i in range(150)
    ],
    "sobrevivientes": [
        {"id": f"S-{i:04d}", "nodo": "N-1980", "refugio": "R-001", "activo": True}
        for i in range(200)
    ],
    "aristasBloqueadas": [],
    "refugios": [
        {"id": "R-001", "nodo": "N-4041", "capacidad": 60, "ocupados": 0},
        {"id": "R-002", "nodo": "N-5092", "capacidad": 60, "ocupados": 0},
        {"id": "R-003", "nodo": "N-5090", "capacidad": 50, "ocupados": 0},
        {"id": "R-004", "nodo": "N-4115", "capacidad": 50, "ocupados": 0},
    ],
}

lines = []


def log(msg: str) -> None:
    lines.append(msg)


async def main() -> None:
    limits = httpx.Limits(max_connections=60, max_keepalive_connections=60)
    async with httpx.AsyncClient(timeout=10.0, limits=limits) as client:
        await client.get(f"{URL}/health")

        # POST /estado
        t0 = time.perf_counter()
        r = await client.post(f"{URL}/estado", headers={"x-api-key": API_KEY}, json=ESTADO)
        log(f"POST /estado: {(time.perf_counter()-t0)*1000:.1f}ms  status={r.status_code}")

        # POST /paso individual
        t0 = time.perf_counter()
        await client.post(f"{URL}/paso", headers={"x-api-key": API_KEY},
                          json={"sobrevivienteId": "S-0001", "nodoActual": "N-1980", "turno": 99})
        log(f"POST /paso (1 sola): {(time.perf_counter()-t0)*1000:.1f}ms")

        # GET /pasos bulk (1 sola request para todos)
        t0 = time.perf_counter()
        rb = await client.get(f"{URL}/pasos", headers={"x-api-key": API_KEY})
        bulk_ms = (time.perf_counter()-t0)*1000
        if rb.status_code == 200:
            n_dec = len(rb.json().get("decisiones", {}))
            log(f"GET /pasos bulk: {bulk_ms:.1f}ms  {n_dec} decisiones")
        else:
            log(f"GET /pasos bulk: status={rb.status_code}")

        # 200x /paso con semáforo=40
        sem = asyncio.Semaphore(40)
        lats: list[float] = []

        async def one_paso(i: int) -> None:
            async with sem:
                t = time.perf_counter()
                await client.post(f"{URL}/paso", headers={"x-api-key": API_KEY},
                                  json={"sobrevivienteId": f"S-{i:04d}", "nodoActual": "N-1980", "turno": 99})
                lats.append((time.perf_counter()-t)*1000)

        t_all = time.perf_counter()
        await asyncio.gather(*(one_paso(i) for i in range(200)))
        total_ms = (time.perf_counter()-t_all)*1000
        lats.sort()
        log(f"200x sem=40: total={total_ms:.0f}ms p50={lats[99]:.1f} p95={lats[189]:.1f} max={max(lats):.1f}")

        # Simular 5 turnos completos con bulk
        log("\n=== Simulación de 5 turnos completos con GET /pasos ===")
        for turno in range(100, 105):
            estado_t = dict(ESTADO)
            estado_t["turno"] = turno
            t0 = time.perf_counter()
            await client.post(f"{URL}/estado", headers={"x-api-key": API_KEY}, json=estado_t)
            post_ms = (time.perf_counter()-t0)*1000
            t0 = time.perf_counter()
            await client.get(f"{URL}/pasos", headers={"x-api-key": API_KEY})
            get_ms = (time.perf_counter()-t0)*1000
            total_turno = post_ms + get_ms
            log(f"  Turno {turno}: POST /estado={post_ms:.1f}ms  GET /pasos={get_ms:.1f}ms  total={total_turno:.1f}ms")


asyncio.run(main())
pathlib.Path("benchmark_results.txt").write_text("\n".join(lines))
