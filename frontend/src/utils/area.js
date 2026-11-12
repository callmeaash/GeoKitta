/** 1 ropani = 508.72 m² = 16 aana = 64 paisa = 256 daam */
export const ROPANI_M2 = 508.72

/**
 * Convert square metres to ropani-aana-paisa-daam, e.g. 296.6 → "0-9-1-1".
 * @param {number} m2
 * @returns {string}
 */
export function toRopani(m2) {
  let daam = Math.round(m2 / (ROPANI_M2 / 256))
  const ropani = Math.floor(daam / 256); daam -= ropani * 256
  const aana = Math.floor(daam / 16); daam -= aana * 16
  const paisa = Math.floor(daam / 4)
  return `${ropani}-${aana}-${paisa}-${daam - paisa * 4}`
}
