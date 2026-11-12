/** Reading survey corner points from typed tables, pasted text, CSV and GeoJSON files. */

/** 'utm' when the numbers look like UTM 45N metres, 'wgs84' when they look like longitude/latitude. */
export function guessCrs(points) {
  return points.every(([x, y]) => Math.abs(x) <= 180 && Math.abs(y) <= 90) ? 'wgs84' : 'utm'
}

const X_NAMES = ['easting', 'east', 'x', 'e', 'lon', 'lng', 'longitude']
const Y_NAMES = ['northing', 'north', 'y', 'n', 'lat', 'latitude']

/**
 * Points from CSV or pasted text: "point,easting,northing" files from the pipeline or a total station,
 * or bare rows of two numbers (a leading point number is ignored). Lat/lng columns are swapped to lng, lat.
 * @returns {{ points: number[][], crs: string }}
 */
export function parseTable(text) {
  const rows = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean).map(l => l.split(/[,;\t ]+/))
  if (!rows.length) throw new Error('No rows found.')
  let xi = -1
  let yi = -1
  let start = 0
  const head = rows[0].map(h => h.toLowerCase().replace(/[^a-z]/g, ''))
  if (head.some(h => h && Number.isNaN(Number(h)))) {
    xi = head.findIndex(h => X_NAMES.includes(h))
    yi = head.findIndex(h => Y_NAMES.includes(h))
    if (xi < 0 || yi < 0) throw new Error('Could not find easting/northing (or lon/lat) columns in the header.')
    start = 1
  }
  const points = rows.slice(start).map((r, n) => {
    const nums = r.map(Number)
    const pick = xi >= 0 ? [nums[xi], nums[yi]] : nums.slice(-2) // without a header: the last two numbers
    if (pick.length < 2 || pick.some(v => !Number.isFinite(v))) throw new Error(`Row ${n + start + 1} is not two numbers.`)
    return pick
  })
  if (points.length < 3) throw new Error('A boundary needs at least 3 corner points.')
  return { points: dropClosing(points), crs: guessCrs(points) }
}

/** The outer ring of the first polygon in a GeoJSON file (always lon/lat). */
export function parseGeoJSON(text) {
  let gj
  try {
    gj = JSON.parse(text)
  } catch {
    throw new Error('The file is not valid JSON.')
  }
  const geom = gj.type === 'FeatureCollection' ? gj.features?.[0]?.geometry : gj.type === 'Feature' ? gj.geometry : gj
  if (geom?.type === 'MultiPolygon' && geom.coordinates.length === 1) return parseGeoJSON(JSON.stringify(
    { type: 'Polygon', coordinates: geom.coordinates[0] }))
  if (geom?.type !== 'Polygon') throw new Error('Expected one Polygon (a parcel is a single polygon).')
  return { points: dropClosing(geom.coordinates[0].map(p => [p[0], p[1]])), crs: 'wgs84' }
}

/** Read a dropped or chosen file by its extension. */
export async function parseFile(file) {
  const text = await file.text()
  return /\.(geo)?json$/i.test(file.name) ? parseGeoJSON(text) : parseTable(text)
}

/** The ring is closed by the server; a repeated first point at the end is removed here. */
function dropClosing(points) {
  const [a, b] = [points[0], points[points.length - 1]]
  return points.length > 3 && a[0] === b[0] && a[1] === b[1] ? points.slice(0, -1) : points
}

/** Exact fractions for owner shares: "1/2" + "1/4" + "1/4" = 1. */
const gcd = (a, b) => (b ? gcd(b, a % b) : Math.abs(a))
export function parseShare(s) {
  const m = String(s).trim().match(/^(\d+)(?:\/(\d+))?$/)
  if (!m) return null
  const [n, d] = [Number(m[1]), Number(m[2] || 1)]
  return d > 0 && n > 0 && n <= d ? [n, d] : null
}
export function sumShares(shares) {
  let [n, d] = [0, 1]
  for (const s of shares) {
    const f = parseShare(s)
    if (!f) return null
    ;[n, d] = [n * f[1] + f[0] * d, d * f[1]]
    const g = gcd(n, d)
    ;[n, d] = [n / g, d / g]
  }
  return [n, d]
}
