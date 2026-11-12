import { describe, expect, it } from 'vitest'
import { ROPANI_M2, toRopani } from './area.js'

describe('toRopani', () => {
  it('converts whole units', () => {
    expect(toRopani(ROPANI_M2)).toBe('1-0-0-0')
    expect(toRopani(ROPANI_M2 / 16)).toBe('0-1-0-0')
    expect(toRopani(ROPANI_M2 / 2)).toBe('0-8-0-0')
  })

  it('converts a typical Kathmandu plot', () => {
    expect(toRopani(296.6)).toBe('0-9-1-1')
  })

  it('handles zero', () => {
    expect(toRopani(0)).toBe('0-0-0-0')
  })
})
