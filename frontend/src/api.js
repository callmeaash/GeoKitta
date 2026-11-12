/**
 * Small wrapper around fetch for the GeoKitta API.
 * In development, Vite forwards /api to the FastAPI backend (see vite.config.js).
 */

/**
 * @typedef {{ status: string, app: string }} Health
 */

/**
 * @param {string} path  e.g. '/api/health'
 * @param {RequestInit} [options]
 */
export async function request(path, options = {}) {
  const res = await fetch(path, { credentials: 'include', ...options })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

/** @returns {Promise<Health>} */
export const getHealth = () => request('/api/health')
