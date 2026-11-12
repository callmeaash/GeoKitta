/** Small geodesy helpers for the measure tool. Points are [lat, lng]. */

const R = 6371008.8 // mean Earth radius, metres
const rad = d => (d * Math.PI) / 180

/** Great-circle distance in metres (haversine). */
export function distanceM(a, b) {
  const dLat = rad(b[0] - a[0])
  const dLng = rad(b[1] - a[1])
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)))
}

/** Length of a path in metres. */
export function pathLengthM(points) {
  let total = 0
  for (let i = 1; i < points.length; i++) total += distanceM(points[i - 1], points[i])
  return total
}

/** Area of a polygon in m²: local flat projection around its mean latitude, then the shoelace formula. */
export function areaM2(points) {
  if (points.length < 3) return 0
  const lat0 = rad(points.reduce((s, p) => s + p[0], 0) / points.length)
  const xy = points.map(([lat, lng]) => [R * rad(lng) * Math.cos(lat0), R * rad(lat)])
  let twice = 0
  for (let i = 0; i < xy.length; i++) {
    const [x1, y1] = xy[i]
    const [x2, y2] = xy[(i + 1) % xy.length]
    twice += x1 * y2 - x2 * y1
  }
  return Math.abs(twice) / 2
}

/** Ground metres covered by one screen pixel (Web Mercator). */
export function metresPerPixel(lat, zoom) {
  return (156543.03392 * Math.cos(rad(lat))) / 2 ** zoom
}
