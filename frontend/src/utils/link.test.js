import { describe, expect, it } from 'vitest'
import { makeLink, readLink } from './link.js'

describe('link', () => {
  it('round-trips the view and parcel', () => {
    const hash = makeLink({ zoom: 18, lat: 27.706612, lng: 85.311234, parcel: 42 })
    expect(hash).toBe('#map=18/27.70661/85.31123&parcel=42')
    expect(readLink(hash)).toEqual({ zoom: 18, lat: 27.70661, lng: 85.31123, parcel: 42 })
  })

  it('ignores broken links', () => {
    expect(readLink('#map=abc&parcel=-3')).toEqual({})
    expect(readLink('')).toEqual({})
  })
})
