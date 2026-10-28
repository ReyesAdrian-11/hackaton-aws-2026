# Spookython — simulación de evacuación de Manta

Proyecto de simulación para observar cómo cambian las rutas de evacuación ante amenazas y bloqueos en la red vial de Manta. El backend FastAPI y `simulador.py` mantienen la lógica y el estado de la partida; el frontend es un observatorio visual conectado a esos datos.

## Estructura

- `main.py`, `routing.py`, `models.py`: API y motor de rutas.
- `simulador.py`: turnos, sobrevivientes, zombis, refugios y eventos.
- `simulation_service.py`: inicio y ejecución de la Ronda 1 dentro del backend.
- `manta_grafo.graphml`: grafo vial local de Manta.
- `frontend/`: interfaz React + TypeScript + Vite.
- `docs/analisis-estado-actual.md`: análisis funcional y pendientes.
- `docs/plans/2026-10-27-live-map-design.md`: diseño aprobado del mapa táctico en vivo.

## Ejecutar en desarrollo

Requiere Python y Node.js instalados. En PowerShell, abre dos terminales desde la raíz del repositorio.

**Terminal 1 — backend:**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

**Terminal 2 — frontend:**

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

Abre la URL que muestre Vite (normalmente `http://127.0.0.1:5173`). En desarrollo, Vite reenvía `/api` al backend en `http://127.0.0.1:8000`. Puedes cambiar el destino con `VITE_DEV_API_TARGET` en `frontend/.env.local`; `frontend/.env.example` contiene los valores iniciales.

El botón demo solicita `POST /simulacion/demo`; el backend inicia la Ronda 1 con 20 sobrevivientes, 10 caminantes, el grafo, las zonas y los refugios configurados. La ronda avanza en turnos de dos segundos y finaliza al resolver a todos los sobrevivientes o llegar al límite de 150 turnos. Si ya terminó, volver a entrar en modo demo inicia una ronda nueva desde el turno 0. El mapa consulta `GET /mapa?incluir_calles=false` y `GET /estado`; el navegador no crea posiciones, rutas ni sucesos. Nodos, rutas, trayectos, bloqueos y eventos provienen de la API. Leaflet usa mosaicos de OpenStreetMap como fondo geográfico (requieren Internet); el grafo vial y los actores se conservan aunque esos mosaicos fallen. Los controles de zoom y paneo son interactivos; Ajustes muestra detalles del estado publicado y la franja del mapa muestra sucesos recientes. El formulario de operador es visual: todavía no existe autenticación de usuarios en la API. Para un origen distinto en despliegues, configura `VITE_API_BASE_URL` al construir el frontend y agrega ese origen a `SPOOKYTHON_CORS_ORIGINS` en el backend.

`GET /mapa` entrega `metadata`, nodos del `grafo`, `zonas` y `refugios`; con `incluir_calles=true` (predeterminado) también entrega las geometrías viales. El frontend omite esas geometrías para limitar la descarga y usa mosaicos OSM como fondo. `GET /estado` expone posiciones, rutas completas calculadas por el backend, trayectos, resultados, bloqueos y eventos estructurados registrados por el simulador. El estado se mantiene en memoria y se reinicia al reiniciar el backend; no hay una base de datos conectada.

Endpoints principales:

```text
GET  /health
GET  /mapa
GET  /estado
POST /simulacion/demo
POST /paso       (requiere x-api-key)
```

## Validación

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm run build
npm run lint
```

Ejecuta `npm` dentro de `frontend/`; el `package.json` no está en la raíz.
