# Rondas y entidades en vivo — diseño aprobado

## Alcance

Implementar las tres rondas descritas en la prueba de fuego del reto. No se
agrega una cuarta ronda sin una especificación propia.

| Ronda | Configuración | Eventos de ciudad |
|---|---|---|
| 1 · Anochecer | 20 sobrevivientes, caminantes | Ninguno |
| 2 · Medianoche | 80 sobrevivientes, caminantes, corredores y hordas | Un puente colapsa |
| 3 · Apocalipsis | 200 sobrevivientes, todos los tipos, incluidos dormidos | Dos calles se bloquean en turnos distintos |

Las cantidades por tipo para Rondas 2 y 3 se mantienen alineadas con los
escenarios y métricas existentes en `docs/analisis-estado-actual.md`.

## Flujo y contrato

El mapa sigue siendo una vista de solo lectura del backend. Un selector visible
de rondas llama `POST /simulacion/demo` con el número elegido. El servicio
inicia una sola ronda a la vez, reinicia el estado cuando cambia la ronda y
publica sus actores, trayectos, refugios, bloqueos y eventos. Las reglas de
movimiento, turnos y peligro no se replican en React.

La planificación de rutas toma en cuenta aristas cerradas, amenazas y capacidad
disponible. Cuando un refugio se llena, se reasignan sobrevivientes pendientes
al refugio alcanzable más cercano según el grafo; el cliente solo dibuja las
rutas publicadas. El estado de ocupación se toma de `refugios.ocupados` y
`refugios.capacidad`, no de conteos inferidos en la interfaz.

El historial estructurado se conserva durante la ronda y se publica en el
estado del mundo. La UI presenta todos los eventos en orden de turno
descendente y permite desplazamiento vertical; se evaluará paginación si el
volumen futuro del historial lo requiere.

## Representación visual

Se conserva el lenguaje visual actual, usando los sprites existentes para
sobrevivientes, mordidos, caminantes, corredores, hordas, dormidos y refugios.
Cada actor tendrá color y badge identificador accesible. Los mordidos quedan
visibles de forma estática en el nodo publicado por el simulador. Los cierres
se dibujan sobre la arista real y muestran `images/obstaculo.png`; el desvío se
resalta cuando cambia la ruta del backend. Los refugios alcanzan estado visual
“LLENO” solo cuando ocupación publicada llega a capacidad.

## Validación

- Pruebas backend de perfiles R1/R2/R3, eventos exclusivos de R2/R3, cambio de
  ronda, capacidad y selección del refugio alcanzable.
- Pruebas del historial completo, orden y deduplicación de eventos.
- Pruebas visuales de sprites/badges, mordidos, refugio lleno, bloqueo y
  desplazamiento del historial.
- Verificar selector y actualización del mapa con respuesta del backend, además
  de build, lint y suite existente.
