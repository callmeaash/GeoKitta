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
