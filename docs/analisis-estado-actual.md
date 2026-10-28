# Análisis del estado actual

## Resumen

Spookython cuenta con un backend FastAPI funcional, un simulador integrado para Escape de Manta y un frontend React + Vite. El backend recomienda movimientos y el simulador mantiene la verdad de la partida; el frontend observa y visualiza esos datos, sin duplicar la lógica de juego.

## Backend implementado

Archivos: `main.py`, `models.py`, `routing.py`, `world_state.py`, `graph_manager.py`, `config.py`, `refugios.json` y `zonas_iniciales.json`.

Incluye FastAPI, NetworkX, carga del grafo GraphML en memoria, IDs estables `N-0000`, autenticación `x-api-key`, rutas seguras, cuatro refugios, cuatro zonas iniciales, calles bloqueadas, hordas que bloquean nodo y vecinos, árboles de rutas precalculados y caché de decisiones por turno. `GET /mapa` entrega nodos, zonas y refugios; las geometrías de calles se incluyen de forma opcional para reducir el peso cuando el cliente solicita `incluir_calles=false`. El endpoint permite CORS para los orígenes configurados en `SPOOKYTHON_CORS_ORIGINS`.

Endpoints:

```text
GET  /health
GET  /estado
POST /estado
GET  /mapa
POST /simulacion/demo
POST /paso
```

Contrato de `POST /paso`:

```json
{"sobrevivienteId":"S-0089","nodoActual":"N-0117","turno":142}
```

Respuesta:

```json
{"siguienteNodo":"N-0118"}
```

## Zonas y refugios configurados

Los sobrevivientes aparecen en cuatro sectores independientes de los refugios:

```text
Tarqui       → N-1980
Los Esteros  → N-3100
Barbasquillo → N-5566
Jocay        → N-2420
```

Los refugios de destino son:

```text
R-001  Mall del Pacífico                             → N-4041
R-002  ULEAM - Sede Manta                            → N-5092
R-003  Paseo Shopping Manta                          → N-5090
R-004  Aeropuerto Internacional General Eloy Alfaro  → N-4115
```

Las coordenadas están en `zonas_iniciales.json` y `refugios.json`. Los nodos son los puntos viales más cercanos calculados sobre el grafo actual.

## Simulador implementado

Archivos: `simulador.py`, `eventos.json` y `zonas_iniciales.json`.

Incluye turnos de dos segundos, caminantes, corredores, hordas, dormidos, BFS limitado para persecuciones, bloqueos de calles, mordidas por nodo y cruces contrarios, refugios, semillas reproducibles, peticiones concurrentes y métricas de rendimiento. `POST /simulacion/demo` inicia una de las tres rondas como tarea del backend: R1 tiene 20 sobrevivientes y caminantes; R2 tiene 80 sobrevivientes con caminantes, corredores, hordas y un puente colapsado; R3 tiene 200 sobrevivientes con todos los tipos, incluidos dormidos, y dos bloqueos en turnos distintos. `GET /estado` conserva los actores resueltos, los resultados, el historial de eventos del turno y el siguiente nodo recomendado.

Orden de cada turno:

```text
1. Aplicar eventos.
2. Despertar dormidos.
3. Mover zombies.
4. Publicar estado.
5. Solicitar pasos.
6. Validar movimientos.
7. Mover sobrevivientes.
8. Resolver mordidas y refugios.
9. Avanzar turno.
```

## Imágenes

La carpeta `images/` contiene los recursos pixel-art disponibles para la interfaz:

```text
caminante.png
corredor.png
hordas.png
dormido.png
sobreviviente.png
mordido.png
refugio.png
obstaculo.png
vecino.png
```

El frontend React + Vite usa la ilustración de hordas en la portada y los sprites disponibles para los actores del mapa vial real; `obstaculo.png` identifica explícitamente las calles bloqueadas.

## Frontend implementado

El directorio `frontend/` contiene la portada de demo y un mapa táctico a pantalla completa con Leaflet y mosaicos de OpenStreetMap. Los mosaicos aportan contexto geográfico, mientras que los nodos, rutas, trayectos, bloqueos, ocupación de refugios y eventos proceden de la API; el navegador interpola los trayectos publicados, sin inventar movimientos. El mapa permite zoom y paneo, diferencia los sprites de sobrevivientes, mordidos y cada tipo de zombi mediante badges, muestra refugios llenos y cierres viales explícitos, y ofrece un historial desplazable completo. Un selector inicia las rondas 1–3 mediante el backend. El botón flotante abre los paneles de panorama, amenazas, refugios, zonas, vías bloqueadas y eventos. El estado se consulta cada 500 ms para reflejar turnos de dos segundos; si falla la API, conserva la última respuesta válida e indica que está desactualizada. Los mosaicos requieren Internet; si fallan, se mantienen los actores y las capas del simulador. El formulario de operador es visual: la autenticación de usuarios aún no existe en el backend.

Instrucciones para iniciar backend y frontend: [README.md](../README.md). Diseño aprobado: [2026-10-27-frontend-design.md](plans/2026-10-27-frontend-design.md).

## Pruebas

Hay veintidós pruebas automatizadas:

```text
22 passed
```

Cubren rutas, zombies, bloqueos, caminantes, dormidos, eventos y cruces peligrosos.

Ejecutar:

```bash
python -m pytest -q
```

## Rendimiento

### Ronda 2

```text
80 sobrevivientes, 30 caminantes, 15 corredores, 5 hordas, 150 turnos
p95: 128.97 ms
máximo: 307.28 ms
timeouts: 0
errores: 0
salvos: 69
mordidos: 7
```

### Ronda 3

```text
200 sobrevivientes, 70 caminantes, 50 corredores, 10 hordas, 20 dormidos
un turno medido: 2.315 s
p95 medido: 1450.89 ms
timeouts: 134 / 200
```

La Ronda 3 funciona, pero todavía supera el objetivo de latencia. La preparación precalculada del backend para 200 sobrevivientes tarda aproximadamente 7 ms; el retraso restante está principalmente en la simulación y el transporte HTTP concurrente.

## Limitaciones actuales

- El mapa tiene 6.769 nodos y 18.207 aristas; el reto sugiere aproximadamente 300 intersecciones.
- El estado vive en memoria; Redis no está integrado.
- El mapa transmite las coordenadas de 6.769 nodos; las geometrías de las 18.207 aristas se excluyen en la solicitud del frontend para limitar la carga. Los mosaicos de OpenStreetMap requieren conexión a Internet.
- El inicio de sesión de operadores no está conectado porque no existe autenticación de usuarios.
- El historial de eventos vive en memoria y se reinicia al reiniciar el backend.
- El despliegue final en AWS está pendiente.
- La Ronda 3 requiere optimización adicional de conexiones HTTP.
- Predicción avanzada, capacidad avanzada y camionetas no están implementadas.
- Los eventos de ejemplo usan IDs de aristas provisionales y deben validarse en el mapa final.

## Próximos pasos

1. Reutilizar un cliente HTTP persistente durante toda la simulación.
2. Reducir o normalizar el grafo para las necesidades del reto.
3. Repetir la Ronda 3 y medir backend, simulador y visualización por separado.
4. Evaluar paginación del historial si el volumen en memoria crece más allá de las rondas actuales.
5. Integrar Redis para AWS.
6. Completar despliegue, CloudWatch, Budget y documentación.

## Conclusión

El nivel base está avanzado: existe backend, simulador, reglas principales, eventos, refugios, zonas iniciales, pruebas automatizadas y una interfaz visual conectada a la API. La Ronda 2 tiene buen resultado de latencia. Las prioridades pendientes son optimizar la Ronda 3, desplegar en AWS y decidir las ampliaciones de autenticación e historial antes de los extras.
