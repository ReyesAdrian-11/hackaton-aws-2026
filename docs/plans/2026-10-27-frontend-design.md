# Diseño del frontend de Spookython

## Objetivo

Crear la experiencia visual del simulador de evacuación en Manta, manteniendo el backend y `simulador.py` como fuentes de verdad. El frontend debe comunicar la emergencia y permitir observar cómo evoluciona la partida; no será un juego de acciones manuales ni implementará una segunda versión de las reglas.

## Alcance y flujo

La aplicación React + Vite tendrá dos pantallas:

1. **Portada:** contexto de la emergencia en Manta, presentación visual y acceso a la demo. No se simulará un inicio de sesión real porque la API no tiene autenticación de usuarios. El acceso demo abrirá directamente el tablero.
2. **Tablero:** mapa protagonista de la ciudad y navegación superior con secciones seleccionables. La sección de información de emergencia se ubicará en la parte superior; su contenido cambiará según la selección. Secciones iniciales: panorama, amenazas, refugios y zonas. El mapa ocupará el resto del espacio y se adaptará a pantallas pequeñas sin quedar oculto por el panel.

La dirección visual será propia, oscura y legible, con jerarquía clara de calles y alertas. Se tomará la imagen de referencia como guía de densidad y contexto, no como una plantilla para copiar. No se crearán imágenes generadas para representar Manta.

## Mapa y datos geográficos

Se usará un mapa vectorial dibujado desde el grafo GraphML incluido en el repositorio, sin depender de un proveedor externo de mosaicos. Se verificó que el grafo tiene 6.769 nodos, 18.207 aristas y geometrías `LineString` en las aristas. El mapa debe preservar proporciones geográficas, usar niveles de zoom y grosores jerárquicos para las vías, y distinguir actores, refugios y bloqueos sin saturar la vista.

El endpoint `GET /mapa` entrega actualmente los puntos de los nodos, pero no las geometrías de las calles. Se ampliará de forma compatible para incluir las aristas como geometrías GeoJSON con sus nodos extremos, conservando el `metadata` y los puntos actuales. Los bloqueos de `GET /estado` se asociarán a esos extremos. Los actores y refugios se ubicarán a partir de sus nodos y las coordenadas del grafo.

## Integración y estados

- Al entrar al tablero, consultar `GET /mapa` una vez y `GET /estado` periódicamente (objetivo inicial: cada 2 segundos).
- Mantener en el navegador la última respuesta válida; si falla una consulta, indicar que los datos están desactualizados y mostrar el error de conexión, sin reemplazar el estado por una partida vacía.
- No llamar a `POST /paso`: el simulador ya solicita recomendaciones y ejecuta los movimientos.
- Derivar recuentos y resúmenes únicamente de campos presentes en `EstadoMundo`. No presentar como reales mensajes o historial de eventos que la API no expone.
- El historial textual de eventos requerirá una ampliación posterior del contrato de API.
- Configurar el acceso del frontend a la API por URL de entorno y permitir el origen de desarrollo de forma explícita, sin exponer claves secretas en el navegador.

## Componentes principales

- `LandingPage`: contexto de la emergencia y navegación a demo.
- `SimulationPage`: carga inicial, sondeo del estado y disposición del tablero.
- `EmergencyNavigation`: selector superior de sección.
- `EmergencyInfoPanel`: información contextual de la sección activa.
- `MantaGraphMap`: calles vectoriales, nodos y marcadores de actores, refugios y bloqueos.
- `ConnectionStatus`: estado de carga, error y antigüedad de los datos.

La interfaz no incluirá controles para mover sobrevivientes ni cálculos locales de rutas. La lógica permanece en `main.py`, `routing.py` y `simulador.py`.

## Validación de aceptación

1. La portada muestra el contexto de la emergencia y abre la demo sin credenciales.
2. El tablero dibuja la red real del GraphML y coloca nodos, actores y refugios desde la API.
3. Las calles bloqueadas y las secciones superiores se actualizan con los datos recibidos.
4. Cambiar de sección cambia la información superior y no inventa eventos que no vengan de la API.
5. Si la API falla, se conserva la última respuesta y se informa el problema.
6. El mapa y el panel siguen siendo utilizables en escritorio y móvil.
7. El backend conserva el formato y los metadatos actuales de `GET /mapa`, y sus pruebas verifican las nuevas geometrías de aristas.
