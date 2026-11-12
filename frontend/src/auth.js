/** The signed-in officer, if any. The session itself is an HttpOnly cookie the page cannot read. */
import { reactive } from 'vue'
import { request } from './api.js'

export const auth = reactive({ officer: null, checked: false })

/** Ask the API who is signed in (once per page load unless forced). */
export async function loadOfficer(force = false) {
  if (auth.checked && !force) return auth.officer
  try {
    auth.officer = await request('/api/auth/me')
  } catch {
    auth.officer = null
  }
  auth.checked = true
  return auth.officer
}

export async function login(username, password) {
  auth.officer = await request('/api/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password })
  })
  auth.checked = true
  return auth.officer
}

export async function logout() {
  try {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
  } finally {
    auth.officer = null
    auth.checked = true
  }
}

/** "Sita Maharjan" → "SM" */
export const initials = name => name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('')
