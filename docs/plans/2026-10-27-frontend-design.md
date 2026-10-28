# Diseño del modo táctico de Spookython

## Contexto y objetivo

Spookython simula la evacuación de Manta ante una emergencia zombie. FastAPI recomienda el siguiente movimiento; el simulador mantiene el estado real de la partida; React observa la API y renderiza los datos, sin generar posiciones ni reglas localmente.

La documentación del estado actual es la referencia de producto y restricciones: turnos de dos segundos, cuatro zonas y refugios configurados, cuatro tipos de zombis y problemas de latencia al escalar a 200 sobrevivientes. La Ronda 1 será más pequeña para ofrecer una demo interactiva sin confundirla con los resultados de rendimiento de las rondas mayores.

## Experiencia de usuario

La portada contextual mantiene el acceso de demo; el formulario de operador es visual mientras no exista autenticación de usuarios. Al elegir demo, el servidor inicia la Ronda 1 y abre el tablero cuando la API confirma el inicio.

Durante el juego, el mapa táctico ocupa todo el viewport. La vista no conserva encabezados, estadísticas ni paneles informativos permanentes. Un único botón flotante de ajustes abre un panel plegable que muestra información técnica del estado y controles discretos de visualización. Los sprites existentes representan a sobrevivientes, caminantes, corredores, hordas y refugios. Las capas vectoriales de calles usan geometrías del grafo real. Los marcadores y líneas solo se dibujan a partir de datos publicados por el servidor; el frontend no inventa eventos ni trayectorias.

## Ronda 1

- 20 sobrevivientes y 10 caminantes, que corresponden a los valores predeterminados existentes de `construir_simulador`.
- Posiciones obtenidas de los nodos de las cuatro zonas iniciales y del grafo GraphML real.
- Los cuatro refugios fijos se cargan de `refugios.json`.
- Seed reproducible, turnos de dos segundos y un máximo de 150 turnos.
- Final anticipado cuando todos los sobrevivientes están rescatados o mordidos.
- El servidor conserva los resultados finales por sobreviviente; el contrato actual solo expone actores activos y se ampliará de forma compatible.

La ronda debe validar los eventos contra el grafo cargado: el análisis actual ya señala que los IDs de eventos de ejemplo necesitan validación y uno de los eventos no coincide con una arista del grafo actual.

## Arquitectura y contrato

FastAPI será propietario de una única sesión global de demo y de su tarea de fondo. `POST /simulacion/demo` inicia idempotentemente la ronda o devuelve el turno de la sesión activa. `GET /estado` seguirá sirviendo de fuente visual y publicará turno, actores activos y resueltos, refugios ocupados, calles bloqueadas, mensajes registrados y próximo nodo recomendado real. `POST /paso` conservará su autenticación `x-api-key` y su respuesta `siguienteNodo`; la decisión se comprobará como arista existente, no bloqueada y segura. `GET /mapa` conserva `metadata` y nodos, y expone geometrías de calles, zonas y refugios.

El simulador se ejecutará dentro del proceso backend y reutilizará sus reglas; no se iniciará un proceso arbitrario ni se confiará en una tercera terminal. El cliente del simulador se reutilizará entre turnos para no repetir conexiones HTTP, una mejora coherente con la limitación de rendimiento documentada. Una llamada de demo concurrente no creará partidas superpuestas. Si el inicio o una actualización falla, el frontend informa el error y conserva la última respuesta válida.

## Interfaz y datos

- `LandingPage`: contexto de Manta y acceso demo.
- `TacticalMap`: mapa SVG/vectorial de viewport completo y marcadores vivos.
- `FloatingSettings`: botón y panel plegable para estado, amenazas, refugios, zonas, ronda y conexión.
- `ConnectionStatus`: estado del polling y antigüedad de los datos.
- El mapa se carga una vez desde `GET /mapa`; `GET /estado` se consulta cada dos segundos.
- React nunca publica el estado inicial de la partida ni calcula decisiones de ruta.
- Las líneas de planificación se dibujan únicamente si el backend proporciona el siguiente paso decidido o una ruta calculada real.

## Validación de aceptación

1. Entrar a demo inicia en el servidor una única Ronda 1; no requiere terminal de simulador aparte.
2. El turno inicial contiene 20 sobrevivientes y 10 caminantes distribuidos desde las zonas y el grafo reales.
3. La ronda avanza en turnos de dos segundos y acaba al resolver a todos los sobrevivientes o al alcanzar el límite.
4. `GET /estado` refleja posiciones y resultados publicados por el motor; sus marcadores coinciden con la UI.
5. Las decisiones de `/paso` mantienen autenticación y no recomiendan un tramo inexistente o bloqueado.
6. El mapa ocupa la pantalla y solo tiene un acceso flotante a ajustes; el panel se puede abrir/cerrar y funciona en móvil.
7. El frontend muestra error en caso de desconexión y conserva la última respuesta válida.
8. Las pruebas incluyen inicio idempotente, fin de ronda, movimientos, resultados, API y carga de mapa.
9. Medir latencia a tamaños de Ronda 1 y cargas documentadas; no afirmar una garantía de 500 ms sin medirla bajo carga.
