const BASE = import.meta.env.VITE_API_BASE ?? '/api'

export async function get(path, params = {}, signal) {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null))
  const res = await fetch(`${BASE}${path}?${q}`, { signal })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : `HTTP ${res.status}`)
  }
  return res.json()
}

export async function retrain(timeframe, token) {
  const res = await fetch(`${BASE}/train?timeframe=${timeframe}`, { method: 'POST', headers: { 'X-Admin-Token': token } })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`)
}

export function load(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback } catch { return fallback }
}
export function save(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* private mode */ }
}
