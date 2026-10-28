import type { DemoStartResponse, MapResponse, WorldState } from './types'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/$/, '')

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { signal })
  if (!response.ok) {
    throw new Error(`La API respondió ${response.status} ${response.statusText}`.trim())
  }
  return response.json() as Promise<T>
}

export function getMap(signal?: AbortSignal): Promise<MapResponse> {
  return getJson<MapResponse>('/mapa?incluir_calles=false', signal)
}

export function getWorldState(signal?: AbortSignal): Promise<WorldState> {
  return getJson<WorldState>('/estado', signal)
}

export async function startDemo(): Promise<DemoStartResponse> {
  const response = await fetch(`${API_BASE_URL}/simulacion/demo`, { method: 'POST' })
  if (!response.ok) {
    let detail = `La API respondió ${response.status} ${response.statusText}`.trim()
    try {
      const body = await response.json() as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      // Keep the HTTP status when the server does not return a JSON error.
    }
    throw new Error(detail)
  }
  return response.json() as Promise<DemoStartResponse>
}
