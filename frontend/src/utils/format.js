/** Display helpers. */

const nf1 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 })
const nf0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })

/** 1234.56 → "1,234.6" */
export const fmt = n => nf1.format(n)

/** Distance: "850 m" or "1.24 km". */
export const fmtDistance = m => (m < 1000 ? `${nf0.format(m)} m` : `${(m / 1000).toFixed(2)} km`)

/** "residential" → "Residential", "power_line" → "Power line" */
export const label = s => (s ? s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, ' ') : '')

const SOURCES = { field_survey: 'Field survey', digitized: 'Digitized', synthetic: 'Synthetic (demo data)' }
export const sourceLabel = s => SOURCES[s] || label(s)

const MEASURED = { centre_line: 'centre line', bank: 'bank', line: 'line' }
export const measuredFrom = s => MEASURED[s] || s

/** Rows to CSV text; quotes values that contain commas, quotes or line breaks. */
export function toCsv(rows) {
  const cell = v => {
    const s = v == null ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  return rows.map(r => r.map(cell).join(',')).join('\n')
}

/** Ask the browser to save text as a file. */
export function download(filename, text, type = 'text/csv') {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([text], { type }))
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

const TXN = {
  registration: 'Registration', boundary_update: 'Boundary update', split: 'Split (kitta kaat)', merge: 'Merge',
  rajinama: 'Rajinama (sale)', hal_ko_bakaspatra: 'Hal ko bakaspatra (gift)', danpatra: 'Danpatra (donation)',
  chhod_patra: 'Chhod patra (release)', ansha_banda: 'Ansha banda (partition)', namasari: 'Namasari (inheritance)',
  samsodhan: 'Samsodhan (correction)', rokka: 'Rokka (hold)', fukuwa: 'Fukuwa (release of hold)'
}
/** Deed or case type for display. */
export const txnLabel = t => TXN[t] || label(t)

const STATUS_CLASS = { approved: 'st-green', draft: 'st-grey', rejected: 'st-red' }
export const statusClass = s => STATUS_CLASS[s] || 'st-grey'

const DISTRICTS = { 25: 'Lalitpur', 26: 'Bhaktapur', 27: 'Kathmandu' }
export const districtName = code => DISTRICTS[code] || (code ? `District ${code}` : '—')
export const DISTRICT_OPTIONS = Object.entries(DISTRICTS).map(([code, name]) => ({ code: Number(code), name }))

/** Exact share for display: "1" (sole owner) reads as "Full". */
export const shareLabel = s => (s === '1' ? 'Full' : s)

/** "1 parcel", "3 parcels" */
export const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`
