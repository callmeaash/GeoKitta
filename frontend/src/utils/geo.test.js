import { describe, expect, it } from 'vitest'
import { areaM2, distanceM, metresPerPixel, pathLengthM } from './geo.js'

describe('geo', () => {
  it('measures a known distance', () => {
    // one degree of latitude is about 111.2 km
    expect(distanceM([27.0, 85.0], [28.0, 85.0])).toBeCloseTo(111195, -2)
    expect(distanceM([27.7, 85.3], [27.7, 85.3])).toBe(0)
  })

  it('adds up path segments', () => {
    const a = [27.7, 85.3], b = [27.701, 85.3], c = [27.701, 85.301]
    expect(pathLengthM([a, b, c])).toBeCloseTo(distanceM(a, b) + distanceM(b, c), 6)
    expect(pathLengthM([a])).toBe(0)
  })

  it('measures the area of a 100 m square near Kathmandu', () => {
    const lat = 27.7, lng = 85.3
    const dLat = 100 / 111195
    const dLng = 100 / (111195 * Math.cos((lat * Math.PI) / 180))
    const square = [[lat, lng], [lat, lng + dLng], [lat + dLat, lng + dLng], [lat + dLat, lng]]
    expect(areaM2(square)).toBeGreaterThan(9990)
    expect(areaM2(square)).toBeLessThan(10010)
    expect(areaM2(square.slice(0, 2))).toBe(0)
  })

  it('gives metres per pixel for Web Mercator', () => {
    expect(metresPerPixel(0, 0)).toBeCloseTo(156543.03, 1)
    expect(metresPerPixel(27.7, 18)).toBeCloseTo(0.529, 2)
  })
})
