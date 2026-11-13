import { describe, expect, it } from 'vitest'
import { adToBs, bsToAd, daysInBsMonth, formatBs, isValidBs, parseBs } from './bs.js'

describe('Bikram Sambat dates', () => {
  it('matches known Nepali New Year days (1 Baisakh)', () => {
    expect(bsToAd(1975, 1, 1)).toBe('1918-04-13') // the epoch
    expect(bsToAd(2000, 1, 1)).toBe('1943-04-14')
    expect(bsToAd(2080, 1, 1)).toBe('2023-04-14')
    expect(bsToAd(2081, 1, 1)).toBe('2024-04-13')
    expect(bsToAd(2082, 1, 1)).toBe('2025-04-14')
    expect(bsToAd(2083, 1, 1)).toBe('2026-04-14')
  })

  it('converts both ways for every day in the table', () => {
    let d = new Date(Date.UTC(1918, 3, 13))
    const end = Date.UTC(2043, 3, 1)
    let prev = null
    for (; d.getTime() < end; d = new Date(d.getTime() + 86400000)) {
      const ad = d.toISOString().slice(0, 10)
      const b = adToBs(ad)
      expect(bsToAd(b.year, b.month, b.day)).toBe(ad)
      if (prev) { // consecutive AD days are consecutive BS days
        const next = prev.day < daysInBsMonth(prev.year, prev.month) ? { ...prev, day: prev.day + 1 }
          : prev.month < 12 ? { year: prev.year, month: prev.month + 1, day: 1 } : { year: prev.year + 1, month: 1, day: 1 }
        expect(b).toEqual(next)
      }
      prev = b
    }
  })

  it('has realistic month and year lengths', () => {
    for (let y = 1975; y <= 2100; y++) {
      let total = 0
      for (let m = 1; m <= 12; m++) {
        expect(daysInBsMonth(y, m)).toBeGreaterThanOrEqual(29)
        expect(daysInBsMonth(y, m)).toBeLessThanOrEqual(32)
        total += daysInBsMonth(y, m)
      }
      // official years are 365 or 366 days; the projected years after 2090 are less certain (2096 has 364)
      expect(y <= 2090 ? total === 365 || total === 366 : total >= 364 && total <= 366).toBe(true)
    }
  })

  it('formats, parses and rejects bad dates', () => {
    expect(formatBs('2026-11-13')).toBe('2083-07-28') // Kartik 2083 began on 17 October 2026
    expect(formatBs('2026-11-13T10:00:00+05:45')).toBe('2083-07-28')
    expect(formatBs(null)).toBe('')
    expect(formatBs('1900-01-01')).toBe('') // before the table
    expect(parseBs('2083/7/27')).toEqual({ year: 2083, month: 7, day: 27 })
    expect(parseBs('2082-02-32')).toBeNull() // Jestha 2082 has 31 days
    expect(parseBs('27-07-2083')).toBeNull()
    expect(isValidBs(2083, 13, 1)).toBe(false)
    expect(() => bsToAd(1974, 12, 30)).toThrow(RangeError)
  })
})
