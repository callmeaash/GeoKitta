/** Shareable links: the map view and selected parcel live in the URL hash, e.g. #map=18/27.70660/85.31120&parcel=12. */

/** @returns {{ zoom?: number, lat?: number, lng?: number, parcel?: number }} */
export function readLink(hash = window.location.hash) {
  const params = new URLSearchParams(hash.replace(/^#/, ''))
  const out = {}
  const m = (params.get('map') || '').split('/').map(Number)
  if (m.length === 3 && m.every(Number.isFinite)) [out.zoom, out.lat, out.lng] = m
  const parcel = Number(params.get('parcel'))
  if (Number.isInteger(parcel) && parcel > 0) out.parcel = parcel
  return out
}

/** Hash text for a view and an optional parcel. */
export function makeLink({ zoom, lat, lng, parcel }) {
  const params = new URLSearchParams()
  params.set('map', `${zoom}/${lat.toFixed(5)}/${lng.toFixed(5)}`)
  if (parcel) params.set('parcel', String(parcel))
  return `#${params.toString().replace(/%2F/g, '/')}`
}

/** Update the address bar without adding a history entry. */
export function writeLink(state) {
  const url = window.location.pathname + window.location.search + makeLink(state)
  window.history.replaceState(window.history.state, '', url) // keep the router's own state
}
