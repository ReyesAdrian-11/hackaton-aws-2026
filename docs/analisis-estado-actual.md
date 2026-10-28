# Análisis del estado actual

## Resumen

Spookython cuenta con un backend FastAPI funcional y un simulador integrado para Escape de Manta. El backend recomienda movimientos y el simulador mantiene la verdad de la partida.

## Backend implementado

Archivos: `main.py`, `models.py`, `routing.py`, `world_state.py`, `graph_manager.py`, `config.py`, `refugios.json` y `zonas_iniciales.json`.

Incluye FastAPI, NetworkX, carga del grafo GraphML en memoria, IDs estables `N-0000`, autenticación `x-api-key`, rutas seguras, cuatro refugios reales, cuatro zonas iniciales, calles bloqueadas, hordas que bloquean nodo y vecinos, árboles de rutas precalculados y caché de decisiones por turno.

Endpoints:

```text
GET  /health
GET  /estado
POST /estado
GET  /mapa
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

Incluye turnos de dos segundos, caminantes, corredores, hordas, dormidos, BFS limitado para persecuciones, bloqueos de calles, mordidas por nodo y cruces contrarios, refugios, semillas reproducibles, peticiones concurrentes y métricas de rendimiento.

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

La carpeta `images/` contiene los recursos pixel-art para el frontend definitivo:

```text
caminante.png
corredor.png
hordas.png
dormido.png
sobreviviente.png
mordido.png
refugio.png
vecino.png
```

El frontend de prueba fue eliminado para continuar con una implementación definitiva.

## Pruebas

Hay siete pruebas automatizadas:

```text
7 passed
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
- El frontend definitivo todavía está pendiente.
- El despliegue final en AWS está pendiente.
- La Ronda 3 requiere optimización adicional de conexiones HTTP.
- Predicción avanzada, capacidad avanzada y camionetas no están implementadas.
- Los eventos de ejemplo usan IDs de aristas provisionales y deben validarse en el mapa final.

## Próximos pasos

1. Implementar el frontend definitivo usando las imágenes de `images/`.
2. Reutilizar un cliente HTTP persistente durante toda la simulación.
3. Reducir o normalizar el grafo.
4. Repetir la Ronda 3 y medir backend y simulador por separado.
5. Integrar Redis para AWS.
6. Completar despliegue, CloudWatch, Budget y documentación.

## Conclusión

El nivel base está avanzado: existe backend, simulador, autenticación, rutas seguras, reglas principales, eventos, refugios, zonas iniciales y pruebas automatizadas. La Ronda 2 tiene buen resultado de latencia. La prioridad es implementar el frontend definitivo, AWS y documentación antes de los extras.
