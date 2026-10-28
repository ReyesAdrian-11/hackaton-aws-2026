export type Coordinate = [number, number]

export interface GeoFeature<TProperties> {
  type: 'Feature'
  id?: string
  properties: TProperties
  geometry:
    | { type: 'Point'; coordinates: Coordinate }
    | { type: 'LineString'; coordinates: Coordinate[] }
}

export interface MapNodeProperties {
  id: string
}

export interface MapEdgeProperties {
  origen: string
  destino: string
  tipo: string | string[]
  distancia_m: number
}

export interface InitialZone {
  id: string
  nombre: string
  nodoReferencia: string
  lat: number
  lng: number
  radioMetros: number
}

export interface MapRefuge {
  id: string
  nodo: string
  nombre: string
  lat: number
  lng: number
  capacidad: number
  ocupados: number
}

export interface MapResponse {
  metadata: {
    nodos: number
    aristas: number
  }
  grafo: {
    type: 'FeatureCollection'
    features: GeoFeature<MapNodeProperties>[]
  }
  calles?: {
    type: 'FeatureCollection'
    features: GeoFeature<MapEdgeProperties>[]
  }
  zonas: InitialZone[]
  refugios: MapRefuge[]
}

export interface Zombie {
  id: string
  tipo: 'caminante' | 'corredor' | 'horda' | 'dormido'
  nodo: string
  nodoAnterior: string | null
  trayecto: string[]
  visible: boolean
}

export interface Survivor {
  id: string
  nodo: string
  nodoAnterior: string | null
  trayecto: string[]
  refugio: string | null
  activo: boolean
  siguienteNodo: string | null
  ruta: string[]
  resultado: 'rescatado' | 'mordido' | null
}

export interface Refuge {
  id: string
  nodo: string
  nombre: string | null
  capacidad: number
  ocupados: number
}

export interface WorldState {
  turno: number
  ronda: number
  simulacion: 'detenida' | 'iniciando' | 'en_curso' | 'completada' | 'error'
  zombies: Zombie[]
  sobrevivientes: Survivor[]
  aristasBloqueadas: string[][]
  refugios: Refuge[]
  eventos: SimulationEvent[]
}

export interface SimulationEvent {
  id: string
  turno: number
  tipo: 'bloqueo' | 'desvio' | 'despertar' | 'mordida' | 'rescate'
  mensaje: string
  actores: string[]
  nodo: string | null
  arista: string[] | null
}

export interface DemoStartResponse {
  ronda: number
  turno: number
  estado: 'iniciando' | 'en_curso' | 'completada' | 'error'
  mensaje: string
}
