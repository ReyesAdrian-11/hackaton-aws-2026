# Spookython — simulación de evacuación de Manta

Proyecto de simulación para observar cómo cambian las rutas de evacuación ante amenazas y bloqueos en la red vial de Manta. El backend FastAPI y `simulador.py` mantienen la lógica y el estado de la partida; el frontend es un observatorio visual conectado a esos datos.

## Estructura

- `main.py`, `routing.py`, `models.py`: API y motor de rutas.
- `simulador.py`: turnos, sobrevivientes, zombis, refugios y eventos.
- `simulation_service.py`: inicio y ejecución de las tres rondas dentro del backend.
- `manta_grafo.graphml`: grafo vial local de Manta.
- `frontend/`: interfaz React + TypeScript + Vite.
- `docs/analisis-estado-actual.md`: análisis funcional y pendientes.
- `docs/arquitectura.md`: diagrama y descripción de la arquitectura desplegable.
- `docs/costos.md`: estimación mensual y plantilla para registrar el gasto real.
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

El botón demo inicia la Ronda 1; el selector del mapa permite cambiar a las rondas 2 y 3 con `POST /simulacion/demo` y el número de ronda. Las configuraciones son: R1, 20 sobrevivientes y caminantes; R2, 80 sobrevivientes con caminantes, corredores, hordas y un puente colapsado; R3, 200 sobrevivientes con todos los tipos de zombis y dos cierres viales. Las cantidades por tipo y los turnos de eventos están definidos en `simulation_service.py` a partir del análisis del reto. Cada ronda avanza en turnos de dos segundos y termina al resolver a todos los sobrevivientes o al llegar al límite de 150 turnos. El mapa consulta `GET /mapa?incluir_calles=false` y `GET /estado`; el navegador no crea posiciones, rutas ni sucesos. Nodos, rutas, trayectos, bloqueos, refugios ocupados y eventos provienen de la API. Los sprites distinguen sobrevivientes, mordidos y tipos de zombi; los cierres muestran el recurso de obstáculo del proyecto y los refugios se marcan llenos según su capacidad publicada. El historial completo de eventos queda disponible en el feed desplazable. Leaflet usa mosaicos de OpenStreetMap como fondo geográfico (requieren Internet); el grafo vial y los actores se conservan aunque esos mosaicos fallen. Los controles de zoom y paneo son interactivos; Ajustes muestra detalles del estado publicado. El formulario de operador es visual: todavía no existe autenticación de usuarios en la API. Para un origen distinto en despliegues, configura `VITE_API_BASE_URL` al construir el frontend y agrega ese origen a `SPOOKYTHON_CORS_ORIGINS` en el backend.

`GET /mapa` entrega `metadata`, nodos del `grafo`, `zonas` y `refugios`; con `incluir_calles=true` (predeterminado) también entrega las geometrías viales. El frontend omite esas geometrías para limitar la descarga y usa mosaicos OSM como fondo. `GET /estado` expone posiciones, rutas completas calculadas por el backend, trayectos, resultados, bloqueos y eventos estructurados registrados por el simulador. El estado se mantiene en memoria y se reinicia al reiniciar el backend; no hay una base de datos conectada.

Endpoints principales:

```text
GET  /health
GET  /mapa
GET  /estado
WS   /ws/estado
POST /simulacion/demo
POST /simulacion/prueba-fuego
POST /simulacion/incidente (requiere x-api-key)
POST /paso       (requiere x-api-key)
```

Los endpoints de control (`POST /paso`, `GET /pasos` y `POST /estado`)
requieren `x-api-key`; las lecturas y el inicio de demo son públicos para que
la UI aprobada pueda entrar sin configuración adicional. El WebSocket acepta
la clave en la cabecera `x-api-key` o en el parámetro de conexión `x-api-key`.
La
Prueba de Fuego ejecuta R1, R2 y R3 consecutivamente, con 150 turnos de dos
segundos por ronda. `WS /ws/estado` envía el snapshot inicial y cada estado
publicado por el simulador.

Para demostrar una reacción en vivo durante una ronda, se puede programar un
cierre real con `POST /simulacion/incidente`:

```json
{"arista":["N-0100","N-0101"],"nombre":"Puente bloqueado por el jurado"}
```

El backend valida la arista, lo agenda para el siguiente tick atómico y publica
el bloqueo junto con las rutas recalculadas y los desvíos afectados.

## Validación

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm run build
npm run lint
```

Ejecuta `npm` dentro de `frontend/`; el `package.json` no está en la raíz.

## Arquitectura y costos

- [Diagrama de arquitectura](docs/arquitectura.md)
- [Declaración de costos](docs/costos.md)

