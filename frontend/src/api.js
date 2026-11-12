/** GeoKitta API client. In development Vite forwards /api to FastAPI (see vite.config.js). */

/**
 * @typedef {{ cells: number, rows_read: number, candidates: number, checked: number, ms: number }} LookupStats
 * @typedef {{ id: number, pin: string, kitta: number, ward: number, map_sheet: string, land_use: string,
 *             parcel_type: string, area_m2: number }} ParcelSummary
 * @typedef {{ parcels: ParcelSummary[], count: number, total_area_m2: number, truncated: boolean,
 *             zone: object|null, stats: LookupStats }} ParcelList
 */

/**
 * @param {string} path
 * @param {RequestInit} [options]
 */
export async function request(path, options = {}) {
  const res = await fetch(path, { credentials: 'include', ...options })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch { /* not JSON */ }
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  return res.json()
}

const post = (path, body) => request(path, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
})

const qs = params => new URLSearchParams(params).toString()

export const api = {
  health: () => request('/api/health'),

  /** Parcel outlines (GeoJSON) for a Leaflet LatLngBounds. */
  inView: (b, signal) => request(`/api/parcels/in-view?${qs({
    west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth()
  })}`, { signal }),

  /** Outlines (GeoJSON) of listed parcels, e.g. search results. */
  outlines: ids => post('/api/parcels/outlines', { ids }),

  /** @returns {Promise<{parcel: ParcelSummary|null, stats: LookupStats}>} */
  at: (lat, lng, tolerance) => request(`/api/parcels/at?${qs({ lat, lng, tolerance })}`),

  parcel: id => request(`/api/parcels/${id}`),

  /** @returns {Promise<ParcelSummary[]>} */
  search: (q, signal) => request(`/api/parcels/search?${qs({ q })}`, { signal }),

  /** @returns {Promise<ParcelList>} */
  select: body => post('/api/parcels/select', body),

  /** @returns {Promise<ParcelList>} */
  buffer: body => post('/api/parcels/buffer', body),

  nearestFeature: (lat, lng, types, maxDistance = 60) =>
    request(`/api/features/nearest?${qs({ lat, lng, types, max_distance: maxDistance })}`),

  rules: () => request('/api/setback-rules')
}
