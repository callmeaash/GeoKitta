/** Shared viewer state: the selected parcel, tool results, drawing on the map and map moves. */
import { reactive } from 'vue'
import { api } from './api.js'

export const store = reactive({
  tab: 'details', // details | select | buffer | measure | layers
  sheetOpen: false, // mobile: whether the bottom sheet is shown

  selectedId: null,
  details: null,
  detailsLoading: false,
  detailsError: null,
  identifyStats: null, // how the quadtree found the clicked parcel

  layers: { base: 'light', parcels: true, labels: true, zones: true },

  /** @type {null | {kind: string, title: string, list: import('./api.js').ParcelList}} */
  results: null,

  /** Drawing request from a panel: {kind: 'point'|'box'|'line'|'polygon'|'feature', purpose: string}. */
  draw: null,
  drawPoints: [], // [lat, lng] vertices placed so far (for live measuring)
  drawResult: null, // {purpose, kind, latlngs?, feature?}

  featureTypes: 'highway,road,river,stream,power_line',
  feature: null, // road or river picked for a buffer search
  flyTo: null, // {geometry} | {bounds: [[s, w], [n, e]]} | {center: [lat, lng], zoom} | {home: true}
  placePin: null, // {name, lat, lng} of the place chosen in search
  toast: null
})

let toastTimer
export function toast(message) {
  store.toast = message
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { store.toast = null }, 2800)
}

export function setTab(tab) {
  if (store.draw && store.draw.purpose !== tab) cancelDraw()
  store.tab = tab
  store.sheetOpen = true
}

export async function selectParcel(id, { fly = false, stats = null } = {}) {
  store.tab = 'details'
  store.identifyStats = stats
  store.sheetOpen = id != null
  store.selectedId = id
  store.detailsError = null
  if (id == null) {
    store.details = null
    return
  }
  store.detailsLoading = true
  try {
    const details = await api.parcel(id)
    if (store.selectedId !== id) return // another parcel was clicked meanwhile
    store.details = details
    if (fly) store.flyTo = { geometry: details.geometry }
  } catch (e) {
    store.details = null
    store.detailsError = e.message
  } finally {
    store.detailsLoading = false
  }
}

export function startDraw(kind, purpose) {
  store.drawResult = null
  store.drawPoints = []
  store.draw = { kind, purpose }
}

export function cancelDraw() {
  store.draw = null
  store.drawPoints = []
}

export function clearResults() {
  store.results = null
  store.feature = null
  store.drawResult = null
}
