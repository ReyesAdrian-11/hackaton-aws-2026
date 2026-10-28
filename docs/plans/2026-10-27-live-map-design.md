# Mapa táctico en vivo de Spookython

## Contexto

La experiencia debe corresponder al reto de Escape de Manta y al análisis de estado actual en `docs/analisis-estado-actual.md`: grafo vial real de Manta, zonas configuradas (Tarqui, Los Esteros, Barbasquillo y Jocay), refugios definidos, cuatro tipos de zombis, turnos de dos segundos, mordidas y bloqueos en vivo. El frontend no crea escenarios, ubicaciones, rutas ni sucesos.

La interfaz existente sí consulta `GET /estado` cada dos segundos, pero la visualización puede parecer estática: comprime el grafo completo en un SVG, representa cada actor con sprites de 12–20 unidades, no tiene controles de zoom o desplazamiento activos y solo dibuja el siguiente tramo, sin interpolar movimiento entre snapshots. El fondo es una red vectorial oscura, no una cartografía reconocible. El registro de eventos solo está en Ajustes y un cierre de calle usa IDs inexistentes que el servicio de simulación omite.

## Experiencia cartográfica

Usar Leaflet con un mapa base real de OpenStreetMap y atribución visible. Los mosaicos son contexto geográfico solamente; el grafo cargado por el backend mantiene autoridad exclusiva sobre vecinos, rutas, bloqueos y posiciones. La cámara permitirá acercar, alejar y desplazar el mapa, con una vista inicial centrada en los sectores de la simulación.

Sobre el fondo se mostrarán sprites legibles para sobrevivientes y tipos de zombis, refugios, aristas bloqueadas y rutas calculadas. El tamaño de los símbolos deberá seguir siendo reconocible al cambiar zoom. La ruta planificada y el tramo que el actor recorre se distinguirán visualmente. El movimiento se interpolará entre el nodo de origen y el destino emitidos por el backend; no se generarán coordenadas ni trayectorias ficticias en el navegador. Si faltan mosaicos o falla Internet, se conservarán el estado y los overlays geográficos disponibles y se informará que falta el mapa base.

Una franja compacta, visible sin abrir Ajustes, mostrará los sucesos más recientes con turno, categoría, entidades y ubicación cuando esos datos estén disponibles. Ajustes seguirá conteniendo las estadísticas y el detalle técnico.

## Datos y responsabilidades

FastAPI y el simulador son la fuente de verdad. La demo existente mantiene el estado en memoria durante la vida del proceso; no hay una base de datos configurada y esta fase no añade persistencia ni infraestructura AWS. La interfaz consumirá exclusivamente el estado publicado por la API.

Se ampliará el contrato de estado de forma compatible para incluir la información necesaria de movimiento (nodo anterior/actual y destino siguiente) y una ruta segura calculada por el backend cuando esté disponible. La API solo publicará decisiones que correspondan a aristas del grafo no bloqueadas y considere los peligros actuales. La UI interpolará visualmente entre nodos ya publicados, sin alterar el estado lógico.

El simulador publicará sucesos estructurados, en orden y limitados a una ventana reciente: por ejemplo, bloqueo aplicado, cambio de ruta asociado, despertar de zombi, mordida y llegada a refugio. Una mordida solo mencionará el ID del zombi si el motor puede atribuirla mediante la colisión observada; en caso contrario indicará el resultado sin inventar el autor. Los bloqueos de la demo deben apuntar a aristas reales verificadas en el grafo. Los cierres inválidos se reportarán explícitamente y no se presentarán como sucesos ocurridos.

## Validación

- Verificar que la base OSM, atribución, zoom, paneo y símbolos sean legibles en escritorio y móvil.
- Validar que la posición y los segmentos de movimiento coincidan con los nodos y decisiones recibidos del backend en cada turno.
- Probar en la API bloqueos válidos, recálculo de rutas, resultados de sobrevivientes y atribución de mordidas.
- Comprobar que la franja muestre solo sucesos realmente emitidos, en orden, y que una desconexión conserve el último estado válido con señal visible de datos obsoletos.
- Probar fallo de los mosaicos sin esconder actores ni información de la simulación.
- Ejecutar la suite de backend, build y lint del frontend. Medir latencia de decisiones; el objetivo de 500 ms se reportará como medición bajo una carga concreta, no como garantía no verificada.

AWS, base de datos persistente, inicio de sesión de usuarios y otras funciones no forman parte de esta fase.
