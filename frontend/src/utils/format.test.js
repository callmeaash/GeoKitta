import { describe, expect, it } from 'vitest'
import { fmt, fmtDistance, label, toCsv } from './format.js'

describe('format', () => {
  it('formats numbers and distances', () => {
    expect(fmt(1234.56)).toBe('1,234.6')
    expect(fmtDistance(850.4)).toBe('850 m')
    expect(fmtDistance(1240)).toBe('1.24 km')
  })

  it('turns codes into labels', () => {
    expect(label('residential')).toBe('Residential')
    expect(label('power_line')).toBe('Power line')
    expect(label(null)).toBe('')
  })

  it('quotes CSV cells that need it', () => {
    expect(toCsv([['a', 'b,c'], [1, 'say "hi"']])).toBe('a,"b,c"\n1,"say ""hi"""')
  })
})

describe('deed labels', async () => {
  const { txnLabel, districtName } = await import('./format.js')
  it('explains Nepali deed types', () => {
    expect(txnLabel('rajinama')).toBe('Rajinama (sale)')
    expect(txnLabel('something_new')).toBe('Something new')
    expect(districtName(27)).toBe('Kathmandu')
  })
})
