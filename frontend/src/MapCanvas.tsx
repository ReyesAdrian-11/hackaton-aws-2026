import { useEffect, useMemo, useRef, useState } from 'react'
import L, { type LatLngExpression, type LeafletEvent, type Marker as LeafletMarker } from 'leaflet'
import {
  Circle,
  MapContainer,
  Marker,
  Pane,
  Polyline,
  TileLayer,
  Tooltip,
  ZoomControl,
  useMap,
} from 'react-leaflet'
import bittenArtwork from '../../images/mordido.png'
import hordeArtwork from '../../images/hordas.png'
import refugeArtwork from '../../images/refugio.png'
import runnerArtwork from '../../images/corredor.png'
import survivorArtwork from '../../images/sobreviviente.png'
import walkerArtwork from '../../images/caminante.png'
import type { InitialZone, MapResponse, Refuge, SimulationEvent, Survivor, WorldState, Zombie } from './types'

const TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
const ICON_SIZE = 30
const zombieArtwork: Record<Zombie['tipo'], string> = {
  caminante: walkerArtwork,
  corredor: runnerArtwork,
  horda: hordeArtwork,
  dormido: walkerArtwork,
}

const survivorIcon = L.icon({
  iconUrl: survivorArtwork,
  iconSize: [ICON_SIZE, ICON_SIZE],
  iconAnchor: [ICON_SIZE / 2, ICON_SIZE / 2],
  className: 'actor-icon actor-icon-survivor',
})
const bittenIcon = L.icon({
  iconUrl: bittenArtwork,
  iconSize: [ICON_SIZE, ICON_SIZE],
  iconAnchor: [ICON_SIZE / 2, ICON_SIZE / 2],
  className: 'actor-icon actor-icon-bitten',
})
const refugeIcon = L.icon({
  iconUrl: refugeArtwork,
  iconSize: [36, 36],
  iconAnchor: [18, 18],
  className: 'actor-icon actor-icon-refuge',
})
const zombieIcons: Record<Zombie['tipo'], L.Icon> = {
  caminante: L.icon({
    iconUrl: zombieArtwork.caminante,
    iconSize: [ICON_SIZE, ICON_SIZE],
    iconAnchor: [ICON_SIZE / 2, ICON_SIZE / 2],
    className: 'actor-icon actor-icon-walker',
  }),
  corredor: L.icon({
    iconUrl: zombieArtwork.corredor,
    iconSize: [ICON_SIZE, ICON_SIZE],
    iconAnchor: [ICON_SIZE / 2, ICON_SIZE / 2],
    className: 'actor-icon actor-icon-runner',
  }),
  horda: L.icon({
    iconUrl: zombieArtwork.horda,
    iconSize: [ICON_SIZE * 1.55, ICON_SIZE * 1.55],
    iconAnchor: [ICON_SIZE * 0.775, ICON_SIZE * 0.775],
    className: 'actor-icon actor-icon-horde',
  }),
  dormido: L.icon({
    iconUrl: zombieArtwork.dormido,
    iconSize: [ICON_SIZE, ICON_SIZE],
    iconAnchor: [ICON_SIZE / 2, ICON_SIZE / 2],
    className: 'actor-icon actor-icon-sleeper',
  }),
}

interface MapCanvasProps {
  map: MapResponse | null
  state: WorldState | null
  stateError: string | null
  loading: boolean
  error: string | null
  onRetry: () => void
}

function refugeLabel(refuge: Refuge): string {
  return refuge.nombre?.split(' - ')[0] ?? refuge.id
}

function toLatLng(coordinate: [number, number]): LatLngExpression {
  return [coordinate[1], coordinate[0]]
}

function eventIcon(type: SimulationEvent['tipo']): string {
  if (type === 'mordida') return 'event-bite'
  if (type === 'rescate') return 'event-rescue'
  if (type === 'bloqueo' || type === 'desvio') return 'event-road'
  return 'event-alert'
}

function FitMapToZones({ zones }: { zones: InitialZone[] }) {
  const map = useMap()
  const boundsKey = zones.map((zone) => `${zone.lat},${zone.lng}`).join(';')

  useEffect(() => {
    if (!zones.length) return
    map.fitBounds(
      L.latLngBounds(zones.map((zone) => [zone.lat, zone.lng])),
      { padding: [48, 48], maxZoom: 14, animate: false },
    )
  }, [boundsKey, map, zones])

  return null
}

function AnimatedActorMarker({
  positions,
  turn,
  icon,
  title,
}: {
  positions: LatLngExpression[]
  turn: number
  icon: L.Icon
  title: string
}) {
  const marker = useRef<LeafletMarker>(null)
  const positionKey = positions
    .map((point) => {
      const [latitude, longitude] = point as [number, number]
      return `${latitude},${longitude}`
    })
    .join(';')
  const points = useMemo(
    () => positionKey.split(';').map((point) => point.split(',').map(Number) as [number, number]),
    [positionKey],
  )
  const [toLat, toLng] = points.at(-1) ?? [0, 0]

  useEffect(() => {
    const leafletMarker = marker.current
    if (!leafletMarker || points.length < 2) {
      if (leafletMarker) leafletMarker.setLatLng([toLat, toLng])
      return
    }

    let startTime: number | null = null
    let animationFrame = 0
    const duration = 1600
    const segments = points.slice(1).map((point, index) => {
      const start = points[index]
      const end = point
      const middleLatitude = ((start[0] + end[0]) / 2 * Math.PI) / 180
      const latitudeDistance = end[0] - start[0]
      const longitudeDistance = (end[1] - start[1]) * Math.cos(middleLatitude)
      return {
        start,
        end,
        length: Math.hypot(latitudeDistance, longitudeDistance),
      }
    })
    const totalLength = segments.reduce((sum, segment) => sum + segment.length, 0)
    const animate = (time: number) => {
      startTime ??= time
      const progress = Math.min(1, (time - startTime) / duration)
      const eased = progress * progress * (3 - 2 * progress)
      let distance = totalLength * eased
      let position = segments[0].start
      for (const segment of segments) {
        if (distance <= segment.length || segment === segments.at(-1)) {
          const part = segment.length ? Math.min(1, distance / segment.length) : 1
          position = [
            segment.start[0] + (segment.end[0] - segment.start[0]) * part,
            segment.start[1] + (segment.end[1] - segment.start[1]) * part,
          ]
          break
        }
        distance -= segment.length
      }
      leafletMarker.setLatLng(position)
      if (progress < 1) animationFrame = requestAnimationFrame(animate)
    }
    animationFrame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(animationFrame)
  }, [points, toLat, toLng, turn])

  return (
    <Marker ref={marker} position={[toLat, toLng]} icon={icon} title={title} keyboard>
      <Tooltip direction="top" offset={[0, -13]}>{title}</Tooltip>
    </Marker>
  )
}

function eventTime(turn: number): string {
  return `T${String(turn).padStart(3, '0')}`
}

export function MapCanvas({ map, state, stateError, loading, error, onRetry }: MapCanvasProps) {
  const [tileError, setTileError] = useState(false)

  const nodePositions = useMemo(() => {
    const positions = new Map<string, [number, number]>()
    for (const feature of map?.grafo.features ?? []) {
      positions.set(feature.properties.id, feature.geometry.coordinates as [number, number])
    }
    return positions
  }, [map])

  const center = useMemo<LatLngExpression | null>(() => {
    const zones = map?.zonas ?? []
    if (zones.length) {
      return [
        zones.reduce((sum, zone) => sum + zone.lat, 0) / zones.length,
        zones.reduce((sum, zone) => sum + zone.lng, 0) / zones.length,
      ]
    }
    const firstNode = map?.grafo.features[0]?.geometry.coordinates
    return firstNode ? toLatLng(firstNode as [number, number]) : null
  }, [map])

  const blockedSegments = (state?.aristasBloqueadas ?? []).flatMap((edge) => {
    if (edge.length !== 2) return []
    const source = nodePositions.get(edge[0])
    const target = nodePositions.get(edge[1])
    return source && target ? [[toLatLng(source), toLatLng(target)] as LatLngExpression[]] : []
  })

  const visibleZombies = (state?.zombies ?? []).filter((zombie) => zombie.visible)
  const eventLocation = (event: SimulationEvent): string | null => {
    if (!map) return null
    const edgeCoordinates = event.arista?.length === 2
      ? [nodePositions.get(event.arista[0]), nodePositions.get(event.arista[1])]
      : []
    const edgeLocation = edgeCoordinates[0] && edgeCoordinates[1]
      ? [
          (edgeCoordinates[0][0] + edgeCoordinates[1][0]) / 2,
          (edgeCoordinates[0][1] + edgeCoordinates[1][1]) / 2,
        ] as [number, number]
      : null
    const coordinate = edgeLocation ?? (event.nodo ? nodePositions.get(event.nodo) : undefined)
    if (!coordinate) {
      return event.arista?.length === 2
        ? `Tramo ${event.arista[0]} ↔ ${event.arista[1]}`
        : event.nodo ? `Nodo ${event.nodo}` : null
    }
    const [longitude, latitude] = coordinate
    const zone = map.zonas.find((candidate) => {
      const latitudeDistance = (candidate.lat - latitude) * 111_000
      const longitudeDistance = (candidate.lng - longitude) * 111_000 * Math.cos((latitude * Math.PI) / 180)
      return Math.hypot(latitudeDistance, longitudeDistance) <= candidate.radioMetros
    })
    if (zone) {
      return event.arista?.length === 2
        ? `${zone.nombre} · ${event.arista[0]} ↔ ${event.arista[1]}`
        : zone.nombre
    }
    return event.arista?.length === 2
      ? `Tramo ${event.arista[0]} ↔ ${event.arista[1]}`
      : `Nodo ${event.nodo}`
  }
  const routes = (state?.sobrevivientes ?? []).flatMap((survivor) => {
    if (!survivor.activo || survivor.ruta.length < 2) return []
    const coordinates = survivor.ruta.flatMap((node) => {
      const coordinate = nodePositions.get(node)
      return coordinate ? [toLatLng(coordinate)] : []
    })
    return coordinates.length > 1 ? [{ id: survivor.id, coordinates }] : []
  })
  const recentEvents = [...(state?.eventos ?? [])].reverse().slice(0, 4)

  if (loading) {
    return (
      <div className="map-placeholder">
        <div className="loader-ring" />
        <span>Conectando el mapa con los datos viales de Manta</span>
      </div>
    )
  }

  if (error || !map || !nodePositions.size || !center) {
    return (
      <div className="map-placeholder map-placeholder-error">
        <span className="map-error-mark">!</span>
        <strong>No se pudo cargar el mapa</strong>
        <span>{error ?? 'La API no entregó coordenadas suficientes para centrar el mapa.'}</span>
        <button className="button button-secondary" onClick={onRetry} type="button">
          Reintentar conexión
        </button>
      </div>
    )
  }

  const onTileFailure = (_event: LeafletEvent) => setTileError(true)

  return (
    <div className="map-stage">
      <MapContainer
        className="tactical-leaflet"
        center={center}
        zoom={12}
        minZoom={10}
        maxZoom={19}
        zoomControl={false}
        preferCanvas
        scrollWheelZoom
      >
        <TileLayer
          url={TILE_URL}
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
          eventHandlers={{ tileerror: onTileFailure }}
        />
        <FitMapToZones zones={map.zonas} />

        <Pane name="spookython-zones" style={{ zIndex: 410 }}>
          {map.zonas.map((zone) => (
            <Circle
              key={zone.id}
              center={[zone.lat, zone.lng]}
              radius={zone.radioMetros}
              pathOptions={{ color: '#81d3ae', weight: 1, dashArray: '5 7', fillColor: '#3eb888', fillOpacity: 0.055 }}
            >
              <Tooltip>{zone.nombre}</Tooltip>
            </Circle>
          ))}
        </Pane>

        <Pane name="spookython-routes" style={{ zIndex: 420 }}>
          {routes.map((route) => (
            <Polyline
              key={route.id}
              positions={route.coordinates}
              pathOptions={{
                className: 'route-plan-flow',
                color: '#65e9c3',
                opacity: 0.28,
                weight: 3,
                dashArray: '5 8',
              }}
            />
          ))}
          {blockedSegments.map((segment, index) => (
            <Polyline
              key={`${state?.turno ?? 0}-blocked-${index}`}
              positions={segment}
              pathOptions={{
                className: 'blocked-road-pulse',
                color: '#ff625d',
                opacity: 0.96,
                weight: 6,
                dashArray: '7 5',
              }}
            />
          ))}
        </Pane>

        <Pane name="spookython-markers" style={{ zIndex: 650 }}>
          {(state?.refugios ?? []).map((refuge) => {
            const coordinate = nodePositions.get(refuge.nodo)
            if (!coordinate) return null
            return (
              <Marker
                key={refuge.id}
                position={toLatLng(coordinate)}
                icon={refugeIcon}
                title={refugeLabel(refuge)}
              >
                <Tooltip direction="top">
                  {`${refugeLabel(refuge)} · ${refuge.ocupados}/${refuge.capacidad} personas`}
                </Tooltip>
              </Marker>
            )
          })}

          {visibleZombies.map((zombie) => {
            const current = nodePositions.get(zombie.nodo)
            if (!current) return null
            const trajectory = zombie.trayecto.flatMap((node) => {
              const coordinate = nodePositions.get(node)
              return coordinate ? [toLatLng(coordinate)] : []
            })
            return (
              <AnimatedActorMarker
                key={zombie.id}
                positions={trajectory.length > 1 ? trajectory : [toLatLng(current)]}
                turn={state?.turno ?? 0}
                icon={zombieIcons[zombie.tipo]}
                title={`${zombie.id} · ${zombie.tipo}`}
              />
            )
          })}

          {(state?.sobrevivientes ?? []).map((survivor: Survivor) => {
            const current = nodePositions.get(survivor.nodo)
            if (!current) return null
            const trajectory = survivor.trayecto.flatMap((node) => {
              const coordinate = nodePositions.get(node)
              return coordinate ? [toLatLng(coordinate)] : []
            })
            const icon = survivor.resultado === 'mordido' ? bittenIcon : survivorIcon
            const status = survivor.resultado ?? (survivor.activo ? 'evacuando' : 'resuelto')
            return (
              <AnimatedActorMarker
                key={survivor.id}
                positions={trajectory.length > 1 ? trajectory : [toLatLng(current)]}
                turn={state?.turno ?? 0}
                icon={icon}
                title={`${survivor.id} · ${status}${survivor.siguienteNodo ? ` · siguiente ${survivor.siguienteNodo}` : ''}`}
              />
            )
          })}
        </Pane>

        <ZoomControl position="bottomright" />
      </MapContainer>

      <div className="map-corner-label">
        <span className="map-stamp-dot" />
        <span>MANTA · ECUADOR</span>
        {state && <span className="map-turn-label">RONDA {state.ronda} · TURNO {String(state.turno).padStart(3, '0')}</span>}
      </div>

      {tileError && (
        <div className="tile-warning" role="status">
          Cartografía base sin conexión. Se conserva la posición del grafo y el estado del simulador.
        </div>
      )}
      {!state && (
        <div className="tile-warning" role="status">
          Esperando el estado publicado por el backend.
        </div>
      )}

      <section className="live-activity" aria-label="Actividad reciente del simulador" aria-live="polite">
        <div className="live-activity-heading">
          <span className={`activity-live-dot ${stateError ? 'activity-live-dot-stale' : ''}`} />
          <strong>{stateError ? 'ESTADO DESACTUALIZADO' : 'ACTIVIDAD DEL SIMULADOR'}</strong>
          <span>{state ? `TURNO ${String(state.turno).padStart(3, '0')}` : 'SIN ESTADO'}</span>
        </div>
        {recentEvents.length ? (
          <ol>
            {recentEvents.map((event) => {
              const location = eventLocation(event)
              return (
                <li className={eventIcon(event.tipo)} key={event.id}>
                  <span className="activity-event-turn">{eventTime(event.turno)}</span>
                  <span>
                    {event.mensaje}
                    {location && <small>{location}</small>}
                  </span>
                </li>
              )
            })}
          </ol>
        ) : (
          <p>{state ? 'Sin sucesos publicados por el simulador.' : 'Esperando datos de la API.'}</p>
        )}
      </section>

      <div className="map-status-key">
        <span><i className="legend-survivor" />Sobrevivientes</span>
        <span><i className="legend-walker" />Zombis</span>
        <span><i className="legend-refuge" />Refugios</span>
        <span><i className="legend-route" />Rutas del backend</span>
      </div>

      <div className="map-attribution-note">
        {map.metadata.nodos.toLocaleString('es-EC')} nodos · Grafo vial local · © OpenStreetMap
      </div>
    </div>
  )
}
