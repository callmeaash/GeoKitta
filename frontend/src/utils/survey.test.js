import { describe, expect, it } from 'vitest'
import { guessCrs, parseGeoJSON, parseShare, parseTable, sumShares } from './survey.js'

describe('survey input', () => {
  it('reads the pipeline CSV format', () => {
    const r = parseTable('point,easting,northing\n1,335639.03,3066479.34\n2,335639.75,3066471.96\n3,335641.27,3066465.16\n')
    expect(r.crs).toBe('utm')
    expect(r.points).toEqual([[335639.03, 3066479.34], [335639.75, 3066471.96], [335641.27, 3066465.16]])
  })

  it('reads pasted rows without a header, ignoring point numbers', () => {
    const r = parseTable('1\t335000\t3066000\n2\t335010\t3066000\n3\t335010\t3066010')
    expect(r.points[2]).toEqual([335010, 3066010])
  })

  it('swaps lat/lng columns into lng, lat and guesses WGS 84', () => {
    const r = parseTable('lat,lng\n27.70,85.31\n27.70,85.32\n27.71,85.32\n27.70,85.31')
    expect(r.crs).toBe('wgs84')
    expect(r.points).toEqual([[85.31, 27.70], [85.32, 27.70], [85.32, 27.71]]) // closing point dropped
  })

  it('explains bad input', () => {
    expect(() => parseTable('easting,northing\n1,2\n3,x\n5,6')).toThrow(/Row 3/)
    expect(() => parseTable('a,b\n1,2\n3,4\n5,6')).toThrow(/columns/)
    expect(() => parseTable('1,2\n3,4')).toThrow(/at least 3/)
  })

  it('reads a GeoJSON polygon or feature', () => {
    const ring = [[85.31, 27.7], [85.32, 27.7], [85.32, 27.71], [85.31, 27.7]]
    expect(parseGeoJSON(JSON.stringify({ type: 'Feature', geometry: { type: 'Polygon', coordinates: [ring] } })).points)
      .toHaveLength(3)
    expect(() => parseGeoJSON('{"type":"Point","coordinates":[1,2]}')).toThrow(/Polygon/)
  })

  it('guesses the coordinate system', () => {
    expect(guessCrs([[335000, 3066000]])).toBe('utm')
    expect(guessCrs([[85.3, 27.7]])).toBe('wgs84')
  })

  it('adds shares exactly', () => {
    expect(parseShare('1/2')).toEqual([1, 2])
    expect(parseShare('3/2')).toBeNull()
    expect(sumShares(['1/2', '1/4', '1/4'])).toEqual([1, 1])
    expect(sumShares(['1/3', '1/3'])).toEqual([2, 3])
    expect(sumShares(['1/2', 'x'])).toBeNull()
  })
})
