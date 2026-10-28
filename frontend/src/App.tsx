import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BadgeAlert,
  Clock3,
  Crosshair,
  DoorOpen,
  MapPinned,
  Radio,
  Route,
  Settings2,
  Shield,
  Siren,
  Users,
  Waypoints,
  X,
} from 'lucide-react'
import hordeArtwork from '../../images/hordas.png'
import 'leaflet/dist/leaflet.css'
import { getMap, getWorldState, startDemo } from './api'
import { MapCanvas } from './MapCanvas'
import type { InitialZone, MapResponse, WorldState, Zombie } from './types'
import './App.css'

type SectionKey = 'panorama' | 'amenazas' | 'refugios' | 'zonas' | 'vias' | 'eventos'

const sections: { id: SectionKey; label: string; icon: typeof Activity }[] = [
  { id: 'panorama', label: 'Panorama', icon: Activity },
  { id: 'amenazas', label: 'Amenazas', icon: Siren },
  { id: 'refugios', label: 'Refugios', icon: Shield },
  { id: 'zonas', label: 'Zonas', icon: MapPinned },
  { id: 'vias', label: 'Vías bloqueadas', icon: Route },
  { id: 'eventos', label: 'Eventos', icon: Radio },
]

const zombieTypes: { id: Zombie['tipo']; label: string }[] = [
  { id: 'caminante', label: 'Caminantes' },
  { id: 'corredor', label: 'Corredores' },
  { id: 'horda', label: 'Hordas' },
  { id: 'dormido', label: 'Dormidos' },
]

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Error desconocido al consultar la API.'
}

function formatTime(date: Date | null): string {
  if (!date) return 'Esperando datos'
  return date.toLocaleTimeString('es-EC', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

type CachedRoute = { round: number; nodes: string[] }

function updateRouteCache(previous: Map<string, CachedRoute>, state: WorldState): Map<string, CachedRoute> {
  const activeSurvivors = new Set(
    state.sobrevivientes.filter((survivor) => survivor.activo).map((survivor) => survivor.id),
  )
  const next = new Map([...previous].filter(([, route]) => route.round === state.ronda))
  let changed = next.size !== previous.size
  for (const [id] of next) {
    if (!activeSurvivors.has(id)) {
      next.delete(id)
      changed = true
    }
  }
  for (const survivor of state.sobrevivientes) {
    if (!survivor.activo || survivor.ruta.length < 2) continue
    const previousRoute = next.get(survivor.id)
    const sameRoute = previousRoute?.nodes.length === survivor.ruta.length
      && previousRoute.nodes.every((node, index) => node === survivor.ruta[index])
    if (!sameRoute) {
      next.set(survivor.id, { round: state.ronda, nodes: survivor.ruta })
      changed = true
    }
  }
  return changed ? next : previous
}

function useSimulationData() {
  const [map, setMap] = useState<MapResponse | null>(null)
  const [state, setState] = useState<WorldState | null>(null)
  const [lastRoutes, setLastRoutes] = useState<Map<string, CachedRoute>>(() => new Map())
  const [mapError, setMapError] = useState<string | null>(null)
  const [stateError, setStateError] = useState<string | null>(null)
  const [mapLoading, setMapLoading] = useState(true)
  const [stateLoading, setStateLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const mounted = useRef(true)
  const stateRefresh = useRef<(() => Promise<void>) | null>(null)
  const refreshState = useCallback(() => {
    void stateRefresh.current?.()
  }, [])

  useEffect(() => {
    mounted.current = true
    const controller = new AbortController()
    let requestActive = false
    let refreshPending = false
    const refresh = async () => {
      if (controller.signal.aborted) return
      if (requestActive) {
        refreshPending = true
        return
      }

      requestActive = true
      try {
        const result = await getWorldState(controller.signal)
        if (mounted.current) {
          setState(result)
          setLastRoutes((previous) => updateRouteCache(previous, result))
          setStateError(null)
          setStateLoading(false)
          setLastUpdated(new Date())
        }
      } catch (error) {
        if (!controller.signal.aborted && mounted.current) {
          setStateError(errorMessage(error))
          setStateLoading(false)
        }
      } finally {
        requestActive = false
        if (refreshPending && mounted.current && !controller.signal.aborted) {
          refreshPending = false
          void refresh()
        }
      }
    }
    stateRefresh.current = refresh
    void getMap(controller.signal)
      .then((result) => {
        if (mounted.current) setMap(result)
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted && mounted.current) setMapError(errorMessage(error))
      })
      .finally(() => {
        if (!controller.signal.aborted && mounted.current) setMapLoading(false)
      })

    void refresh()
    const timer = window.setInterval(() => void refresh(), 500)
    return () => {
      mounted.current = false
      if (stateRefresh.current === refresh) stateRefresh.current = null
      controller.abort()
      window.clearInterval(timer)
    }
  }, [])

  const retryMap = useCallback(() => {
    setMapLoading(true)
    setMapError(null)
    void getMap()
      .then((result) => {
        if (mounted.current) setMap(result)
      })
      .catch((error: unknown) => {
        if (mounted.current) setMapError(errorMessage(error))
      })
      .finally(() => {
        if (mounted.current) setMapLoading(false)
      })
  }, [])

  return { map, state, lastRoutes, mapError, stateError, mapLoading, stateLoading, lastUpdated, retryMap, refreshState }
}

function LandingPage({
  onEnter,
  starting,
  startError,
}: {
  onEnter: () => void
  starting: boolean
  startError: string | null
}) {
  const [loginMessage, setLoginMessage] = useState('')

  return (
    <main className="landing-screen">
      <div className="landing-atmosphere" aria-hidden="true">
        <div className="landing-grid" />
        <div className="landing-radar landing-radar-one" />
        <div className="landing-radar landing-radar-two" />
        <div className="landing-coastline" />
      </div>

      <header className="landing-header">
        <a className="brand-lockup" href="#inicio" aria-label="Spookython, inicio">
          <span className="brand-mark"><Crosshair size={19} strokeWidth={2.2} /></span>
          <span className="brand-name">SPOOKYTHON<span>SIMULADOR DE EVACUACIÓN</span></span>
        </a>
        <div className="landing-location"><span className="status-dot" />MANTA, MANABÍ <span>·</span> ECUADOR</div>
      </header>

      <section className="landing-layout" id="inicio">
        <div className="landing-story">
          <div className="eyebrow"><span className="eyebrow-line" />PROTOCOLO DE EMERGENCIA <span className="eyebrow-index">01 / 04</span></div>
          <h1>Cuando la ciudad<br />se detiene, <em>cada ruta</em><br />cuenta.</h1>
          <p className="landing-lede">
            Observa la evacuación de Manta en tiempo real. Refugios, amenazas y calles cambian con cada turno.
          </p>

          <div className="landing-artwork" aria-hidden="true">
            <div className="artwork-grid" />
            <div className="artwork-coordinate">00°57′S&nbsp; 80°42′W</div>
            <img src={hordeArtwork} alt="" />
            <div className="artwork-caption"><span className="pulse-dot" />ESCENARIO DE EMERGENCIA</div>
            <div className="artwork-route artwork-route-one" />
            <div className="artwork-route artwork-route-two" />
            <div className="artwork-route artwork-route-three" />
          </div>

          <div className="landing-facts">
            <span><Waypoints size={15} /> Red vial de Manta</span>
            <span><DoorOpen size={15} /> Refugios configurados</span>
            <span><Radio size={15} /> Estado del simulador</span>
          </div>
        </div>

        <aside className="access-panel">
          <div className="access-panel-top">
            <span className="access-kicker">CENTRO DE OPERACIONES</span>
            <span className="access-seal"><Shield size={15} /></span>
          </div>
          <h2>Acceso al sistema</h2>
          <p>Ingresa para observar el estado de la ciudad y sus rutas de evacuación.</p>

          <form
            className="login-form"
            onSubmit={(event) => {
              event.preventDefault()
              setLoginMessage('El acceso con cuenta aún no está habilitado. Puedes entrar en modo demo.')
            }}
          >
            <label htmlFor="operator-email">Correo del operador</label>
            <input id="operator-email" type="email" placeholder="operador@spookython.ec" autoComplete="username" />
            <label htmlFor="operator-password">Contraseña</label>
            <input id="operator-password" type="password" placeholder="••••••••••••" autoComplete="current-password" />
            <button type="submit" className="button button-login">Iniciar sesión <ArrowRight size={16} /></button>
          </form>

          {loginMessage && <p className="login-feedback" role="status">{loginMessage}</p>}

          <div className="access-divider"><span>O CONTINÚA SIN CUENTA</span></div>

          <button type="button" className="button button-demo" onClick={onEnter} disabled={starting}>
            <span className="demo-button-icon"><Activity size={18} /></span>
            <span>{starting ? 'Iniciando ronda…' : 'Entrar como demo'}<small>Explorar la simulación en vivo</small></span>
            <ArrowRight className="demo-arrow" size={18} />
          </button>
          {startError && <p className="login-feedback" role="alert">{startError}</p>}
          <div className="access-note"><span className="access-note-dot" />La demo consulta el estado real del simulador.</div>
          <div className="access-bottom"><span>ACCESO DE OPERADOR NO DISPONIBLE</span><span>SPK / MNT</span></div>
        </aside>
      </section>

      <footer className="landing-footer">
        <span>SIMULACIÓN URBANA <i /> MANTA, ECUADOR</span>
        <span>OBSERVA. COMPRENDE. EVACÚA.</span>
      </footer>
    </main>
  )
}

function refugesSummary(state: WorldState | null) {
  return (state?.refugios ?? []).reduce(
    (summary, refuge) => ({
      capacity: summary.capacity + refuge.capacidad,
      occupied: summary.occupied + refuge.ocupados,
    }),
    { capacity: 0, occupied: 0 },
  )
}

function SectionDetails({
  section,
  state,
  map,
}: {
  section: SectionKey
  state: WorldState | null
  map: MapResponse | null
}) {
  const zombies = state?.zombies ?? []
  const visibleZombies = zombies.filter((zombie) => zombie.visible)
  const survivors = (state?.sobrevivientes ?? []).filter((survivor) => survivor.activo)
  const capacity = refugesSummary(state)
  const blockedEdges = (state?.aristasBloqueadas ?? []).filter((edge) => edge.length === 2)
  const nodeCoordinates = new Map(
    (map?.grafo.features ?? []).map((feature) => [
      feature.properties.id,
      feature.geometry.coordinates as [number, number],
    ]),
  )

  const isNodeInZone = (node: string, zone: InitialZone) => {
    const coordinate = nodeCoordinates.get(node)
    if (!coordinate) return false
    const latitudeDistance = (zone.lat - coordinate[1]) * 111_000
    const longitudeDistance = (zone.lng - coordinate[0]) * 111_000 * Math.cos((zone.lat * Math.PI) / 180)
    return Math.hypot(latitudeDistance, longitudeDistance) <= zone.radioMetros
  }

  if (section === 'amenazas') {
    return (
      <div className="detail-grid detail-threats">
        {zombieTypes.map(({ id, label }) => {
          const count = zombies.filter((zombie) => zombie.tipo === id).length
          const activeCount = zombies.filter((zombie) => zombie.tipo === id && zombie.visible).length
          return (
            <div className={`detail-chip threat-chip threat-${id}`} key={id}>
              <span className="threat-mark" />
              <span>{label}<small>{id === 'dormido' && count !== activeCount ? 'No visibles hasta despertar' : 'Detectados en el mapa'}</small></span>
              <strong>{count}</strong>
            </div>
          )
        })}
        <div className="detail-footnote"><AlertTriangle size={14} /> {visibleZombies.length} amenazas visibles en el estado actual</div>
      </div>
    )
  }

  if (section === 'refugios') {
    return (
      <div className="detail-grid detail-refuges">
        {state?.refugios.length ? state.refugios.map((refuge) => {
          const percentage = refuge.capacidad ? Math.min(100, (refuge.ocupados / refuge.capacidad) * 100) : 0
          const full = refuge.ocupados >= refuge.capacidad
          return (
            <div className={`refuge-card ${full ? 'refuge-card-full' : ''}`} key={refuge.id}>
              <div className="refuge-card-heading">
                <span><Shield size={14} />{refuge.id}</span>
                <b>{refuge.ocupados}<small> / {refuge.capacidad}</small></b>
                {full && <strong className="refuge-full-badge">LLENO</strong>}
              </div>
              <strong>{refuge.nombre ?? refuge.id}</strong>
              <div className="capacity-track"><span style={{ width: `${percentage}%` }} /></div>
            </div>
          )
        }) : <div className="empty-detail">Esperando refugios en el estado de la API.</div>}
      </div>
    )
  }

  if (section === 'zonas') {
    return (
      <div className="detail-grid detail-zones">
        {(map?.zonas ?? []).map((zone, index) => {
          const zoneSurvivors = (state?.sobrevivientes ?? []).filter((survivor) => isNodeInZone(survivor.nodo, zone))
          const zoneZombies = visibleZombies.filter((zombie) => isNodeInZone(zombie.nodo, zone))
          const zoneBlockedRoads = blockedEdges.filter((edge) => edge.some((node) => isNodeInZone(node, zone)))
          const zoneEvents = [...(state?.eventos ?? [])]
            .filter((event) => (
              (event.nodo !== null && isNodeInZone(event.nodo, zone))
              || (event.arista?.some((node) => isNodeInZone(node, zone)) ?? false)
            ))
            .sort((first, second) => second.turno - first.turno)
          const latestEvent = zoneEvents[0]
          const active = zoneSurvivors.filter((survivor) => survivor.activo).length
          const rescued = zoneSurvivors.filter((survivor) => survivor.resultado === 'rescatado').length
          const bitten = zoneSurvivors.filter((survivor) => survivor.resultado === 'mordido').length

          return (
            <div className="zone-card" key={zone.id}>
              <span className="zone-card-index">0{index + 1}</span>
              <span className="zone-card-content">
                <strong>{zone.nombre}</strong>
                <small>Inicial · nodo {zone.nodoReferencia} · radio {zone.radioMetros} m</small>
                <small>{active} activos · {rescued} rescatados · {bitten} mordidos · {zoneZombies.length} amenazas</small>
                <small>{zoneBlockedRoads.length} vías bloqueadas</small>
                <small className="zone-latest-event">
                  {latestEvent ? `T${latestEvent.turno}: ${latestEvent.mensaje}` : 'Sin eventos reportados'}
                </small>
              </span>
            </div>
          )
        })}
        {!map?.zonas.length && <div className="empty-detail">Las zonas aparecerán al conectar el mapa.</div>}
      </div>
    )
  }

  if (section === 'vias') {
    return (
      <div className="detail-grid detail-blocked">
        {blockedEdges.length ? blockedEdges.map(([source, target]) => (
          <div className="blocked-edge" key={`${source}:${target}`}>
            <span className="blocked-icon"><Route size={14} /></span>
            <span>
              <strong>{source} <i>↔</i> {target}</strong>
              <small>
                {[...(state?.eventos ?? [])].reverse().find((event) => (
                  event.arista?.length === 2
                  && ((event.arista[0] === source && event.arista[1] === target)
                    || (event.arista[0] === target && event.arista[1] === source))
                ))?.mensaje ?? 'Bloqueo activo en el estado del mundo'}
              </small>
            </span>
            <BadgeAlert size={15} />
          </div>
        )) : <div className="empty-detail">No hay tramos bloqueados en el estado actual.</div>}
      </div>
    )
  }

  if (section === 'eventos') {
    const events = [...(state?.eventos ?? [])].sort((first, second) => second.turno - first.turno)
    return (
      <div className="detail-grid detail-events">
        {events.length ? events.map((event) => (
          <div className="event-row" key={event.id}>
            <span className="event-pulse" />
            <span><strong>{event.mensaje}</strong><small>Turno {event.turno} · {event.actores.join(', ') || 'Simulador'}</small></span>
          </div>
        )) : <div className="empty-detail">Sin eventos de emergencia reportados por el simulador.</div>}
      </div>
    )
  }

  const resolvedSurvivors = (state?.sobrevivientes ?? []).filter((survivor) => survivor.resultado === 'rescatado').length
  const bittenSurvivors = (state?.sobrevivientes ?? []).filter((survivor) => survivor.resultado === 'mordido').length
  return (
    <div className="detail-grid detail-overview">
      <div className="overview-item"><span className="overview-icon icon-turn"><Clock3 size={16} /></span><span><small>RONDA / TURNO</small><strong>{state ? `${state.ronda} / ${String(state.turno).padStart(3, '0')}` : '—'}</strong></span></div>
      <div className="overview-item"><span className="overview-icon icon-survivors"><Users size={16} /></span><span><small>EN MOVIMIENTO</small><strong>{stateLoadingText(state, survivors.length)}</strong></span></div>
      <div className="overview-item"><span className="overview-icon icon-threats"><Siren size={16} /></span><span><small>AMENAZAS VISIBLES</small><strong>{state ? visibleZombies.length : '—'}</strong></span></div>
      <div className="overview-item"><span className="overview-icon icon-refuges"><Shield size={16} /></span><span><small>OCUPACIÓN REFUGIOS</small><strong>{state ? `${capacity.occupied} / ${capacity.capacity}` : '—'}</strong></span></div>
      <div className="overview-item"><span className="overview-icon icon-rescued"><DoorOpen size={16} /></span><span><small>RESCATADOS</small><strong>{state ? resolvedSurvivors : '—'}</strong></span></div>
      <div className="overview-item"><span className="overview-icon icon-bitten"><AlertTriangle size={16} /></span><span><small>MORDIDOS</small><strong>{state ? bittenSurvivors : '—'}</strong></span></div>
      <div className="overview-item overview-routes"><span className="overview-icon icon-routes"><Waypoints size={16} /></span><span><small>TRAMOS BLOQUEADOS</small><strong>{state ? blockedEdges.length : '—'}</strong></span></div>
    </div>
  )
}

function stateLoadingText(state: WorldState | null, count: number): string | number {
  return state ? count : '—'
}

function EmergencyBoard({ onExit }: { onExit: () => void }) {
  const { map, state, lastRoutes, mapError, stateError, mapLoading, stateLoading, lastUpdated, retryMap, refreshState } = useSimulationData()
  const [activeSection, setActiveSection] = useState<SectionKey>('panorama')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [roundError, setRoundError] = useState<string | null>(null)
  const [roundChanging, setRoundChanging] = useState(false)
  const [selectedRound, setSelectedRound] = useState<number | null>(null)
  const currentSection = sections.find((section) => section.id === activeSection) ?? sections[0]
  const activeRound = selectedRound ?? state?.ronda ?? 1
  const displayedState = state?.ronda === activeRound ? state : null
  const connectionLabel = stateError
    ? displayedState ? 'Datos desactualizados' : 'Sin conexión'
    : displayedState?.simulacion === 'error'
      ? 'Simulación con error'
      : (stateLoading && !displayedState) || roundChanging
        ? 'Conectando'
        : displayedState?.simulacion === 'completada'
          ? 'Ronda completada'
          : 'En vivo'

  return (
    <main className="tactical-screen">
      <MapCanvas map={map} state={displayedState} lastRoutes={lastRoutes} stateError={stateError} loading={mapLoading} error={mapError} onRetry={retryMap} />
      <label className="round-selector">
        <span>RONDA</span>
        <select
          aria-label="Cambiar ronda de simulación"
          value={activeRound}
          disabled={roundChanging}
          onChange={(event) => {
            const round = Number(event.currentTarget.value)
            const previousRound = activeRound
            setSelectedRound(round)
            setRoundChanging(true)
            setRoundError(null)
            void startDemo(round)
              .then((result) => {
                if (result.estado === 'error') throw new Error(result.mensaje)
                void refreshState()
              })
              .catch((error: unknown) => {
                setSelectedRound(previousRound)
                setRoundError(errorMessage(error))
              })
              .finally(() => setRoundChanging(false))
          }}
        >
          <option value={1}>01 · Anochecer</option>
          <option value={2}>02 · Medianoche</option>
          <option value={3}>03 · Apocalipsis</option>
        </select>
      </label>
      {state && !displayedState && (
        <div className="round-sync-status" role="status">
          <span className="small-loader" />
          Sincronizando estado de la ronda {activeRound}…
        </div>
      )}
      {roundError && <div className="round-error" role="alert">{roundError}</div>}
      <button
        className={`settings-toggle ${settingsOpen ? 'settings-toggle-active' : ''}`}
        type="button"
        aria-label={settingsOpen ? 'Cerrar ajustes' : 'Abrir ajustes y estado de emergencia'}
        aria-expanded={settingsOpen}
        onClick={() => setSettingsOpen((open) => !open)}
      >
        {settingsOpen ? <X size={18} /> : <Settings2 size={18} />}
        <span>{settingsOpen ? 'Cerrar' : 'Ajustes'}</span>
      </button>

      {settingsOpen && (
        <aside className="settings-panel" aria-label="Ajustes e información de emergencia">
          <div className="settings-heading">
            <div className="settings-heading-brand">
              <span className="brand-mark"><Crosshair size={16} strokeWidth={2.2} /></span>
              <span><strong>SPOOKYTHON</strong><small>CONTROL TÁCTICO · MANTA</small></span>
            </div>
            <button className="settings-close" type="button" aria-label="Cerrar ajustes" onClick={() => setSettingsOpen(false)}>
              <X size={17} />
            </button>
          </div>

          <div className={`settings-connection ${stateError || displayedState?.simulacion === 'error' ? 'settings-connection-error' : ''}`}>
            <span className="connection-indicator" />
            <span>{connectionLabel}</span>
            <span className="settings-round">RONDA {displayedState?.ronda ?? activeRound} · TURNO {String(displayedState?.turno ?? 0).padStart(3, '0')}</span>
          </div>

          <nav className="settings-nav" aria-label="Información del simulador">
            {sections.map(({ id, label, icon: Icon }) => (
              <button
                className={`settings-tab ${activeSection === id ? 'settings-tab-active' : ''}`}
                key={id}
                type="button"
                onClick={() => setActiveSection(id)}
                aria-current={activeSection === id ? 'page' : undefined}
              >
                <Icon size={14} /><span>{label}</span>
              </button>
            ))}
          </nav>

          <section className="settings-content" aria-live="polite">
            <div className="settings-section-title">
              <span className="panel-overline"><span className="panel-overline-mark" />CENTRO DE INFORMACIÓN</span>
              <h1>{currentSection.label}</h1>
              <p>
                {activeSection === 'panorama' && 'Estado publicado por el motor de simulación.'}
                {activeSection === 'amenazas' && 'Amenazas observadas en el último turno.'}
                {activeSection === 'refugios' && 'Capacidad y ocupación reportadas por el backend.'}
                {activeSection === 'zonas' && 'Sectores iniciales del escenario geográfico.'}
                {activeSection === 'vias' && 'Bloqueos que afectan las rutas disponibles.'}
                {activeSection === 'eventos' && 'Mensajes emitidos por los eventos del simulador.'}
              </p>
            </div>
            {stateError && (
              <div className={`stale-message ${displayedState ? 'stale-message-warning' : ''}`} role="status">
                <AlertTriangle size={15} />
                <span>{displayedState ? 'No se pudo actualizar. Se conserva la última respuesta válida.' : 'No se pudo conectar con la API.'}</span>
                <small>{stateError}</small>
              </div>
            )}
            {roundError && <div className="stale-message" role="alert"><AlertTriangle size={15} /><span>{roundError}</span></div>}
            {stateLoading && !displayedState ? (
              <div className="details-loading"><span className="small-loader" />Esperando datos del simulador…</div>
            ) : (
              <SectionDetails section={activeSection} state={displayedState} map={map} />
            )}
            <div className="data-timestamp">
              <span className="data-live-dot" />
              <span>{displayedState && lastUpdated ? `Actualizado ${formatTime(lastUpdated)}` : 'Esperando datos de ronda'}</span>
              <span className="timestamp-divider">·</span>
              <span>Sondeo 500 ms · turno 2 s</span>
            </div>
            {map && (
              <div className="settings-map-meta">
                <Waypoints size={13} />
                <span>{map.metadata.nodos.toLocaleString('es-EC')} nodos</span>
                <i />
                <span>{map.metadata.aristas.toLocaleString('es-EC')} tramos</span>
              </div>
            )}
            <div className="settings-legend">
              <span><i className="legend-dot legend-survivor" />Sobrevivientes</span>
              <span><i className="legend-dot legend-walker" />Caminantes</span>
              <span><i className="legend-dot legend-runner" />Corredores</span>
              <span><i className="legend-dot legend-horde" />Hordas</span>
              <span><i className="legend-dot legend-refuge" />Refugios</span>
            </div>
          </section>

          <button className="settings-exit" type="button" onClick={onExit}>
            <DoorOpen size={15} /> Volver al inicio
          </button>
        </aside>
      )}
    </main>
  )
}

export default function App() {
  const [inDemo, setInDemo] = useState(false)
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)

  const enterDemo = async () => {
    setStarting(true)
    setStartError(null)
    try {
      const result = await startDemo(1)
      if (result.estado === 'error') throw new Error(result.mensaje)
      setInDemo(true)
    } catch (error) {
      setStartError(errorMessage(error))
    } finally {
      setStarting(false)
    }
  }

  return inDemo
    ? <EmergencyBoard onExit={() => setInDemo(false)} />
    : <LandingPage onEnter={() => void enterDemo()} starting={starting} startError={startError} />
}
