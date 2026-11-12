<script setup>
import { computed, ref } from 'vue'
import { api } from '../api.js'
import { selectParcel, store } from '../store.js'
import { label } from '../utils/format.js'
import Icon from './Icon.vue'

const PLACE_ICON = { tole: 'pin', landmark: 'flag', park: 'tree', river: 'waves', road: 'road', ward: 'map' }
const PLACE_ZOOM = { ward: 15, road: 16, river: 16 }

const q = ref('')
const open = ref(false)
const result = ref({ places: [], parcels: [], suggestion: null })
const state = ref('idle') // idle | loading | done | error
let timer
let controller

const items = computed(() => [
  ...result.value.places.map(p => ({ kind: 'place', item: p })),
  ...result.value.parcels.map(p => ({ kind: 'parcel', item: p }))
])

function onInput() {
  clearTimeout(timer)
  if (!q.value.trim()) {
    open.value = false
    return
  }
  timer = setTimeout(run, 200)
}

async function run() {
  controller?.abort()
  controller = new AbortController()
  state.value = 'loading'
  open.value = true
  try {
    result.value = await api.search(q.value.trim(), controller.signal)
    state.value = 'done'
  } catch (e) {
    if (e.name !== 'AbortError') state.value = 'error'
  }
}

/** How close a place matched, in the prototype's words. */
function matchLabel(p) {
  if (p.distance === 0) return 'match'
  if (p.edits === 0) return 'other spelling'
  if (p.edits < 1) return 'starts with'
  const n = Math.round(p.edits)
  return `close match · ${n} edit${n > 1 ? 's' : ''}`
}

function choose({ kind, item }) {
  open.value = false
  if (kind === 'place') {
    q.value = item.name
    store.placePin = { name: item.name, lat: item.lat, lng: item.lng }
    store.flyTo = { center: [item.lat, item.lng], zoom: PLACE_ZOOM[item.kind] || 18 }
  } else {
    q.value = `Kitta ${item.kitta}, ward ${item.ward}`
    store.placePin = null
    selectParcel(item.id, { fly: true })
  }
}

function useSuggestion() {
  q.value = result.value.suggestion
  run()
}

function closeSoon() {
  setTimeout(() => { open.value = false }, 150)
}

function onKey(e) {
  if (e.key === 'Escape') {
    open.value = false
    e.target.blur()
  } else if (e.key === 'Enter' && items.value.length && state.value === 'done') {
    choose(items.value[0])
  }
}
</script>

<template>
  <div class="search" @focusout="closeSoon">
    <span class="s-icon"><Icon name="search" :size="16" /></span>
    <input v-model="q" type="search" placeholder="Search a place, PIN or kitta number…" autocomplete="off"
           aria-label="Search a place, PIN or kitta number" @input="onInput" @keydown="onKey" @focus="q && run()">
    <div class="dropdown" :class="{ open }" role="listbox">
      <div v-if="state === 'loading' && !items.length" class="dd-empty">Searching…</div>
      <div v-else-if="state === 'error'" class="dd-empty">Search failed. Is the API running?</div>
      <template v-else-if="items.length">
        <div v-if="result.suggestion" class="dd-hint">
          Did you mean: <a @mousedown.prevent="useSuggestion">{{ result.suggestion }}</a>?
        </div>
        <template v-if="result.places.length">
          <div class="dd-group">Places</div>
          <div v-for="p in result.places" :key="'p' + p.id" class="dd-item" role="option"
               @mousedown.prevent="choose({ kind: 'place', item: p })">
            <span class="dd-icon"><Icon :name="PLACE_ICON[p.kind] || 'pin'" :size="16" /></span>
            {{ p.name }}<span class="dd-type">{{ label(p.kind) }}<template v-if="p.ward"> · Ward {{ p.ward }}</template></span>
            <span class="meta">{{ matchLabel(p) }}</span>
          </div>
        </template>
        <template v-if="result.parcels.length">
          <div class="dd-group">Parcels</div>
          <div v-for="p in result.parcels" :key="'k' + p.id" class="dd-item" role="option"
               @mousedown.prevent="choose({ kind: 'parcel', item: p })">
            <span class="dd-icon"><Icon name="parcel" :size="16" /></span>
            Kitta {{ p.kitta }}<span class="dd-type">Ward {{ p.ward }} · {{ label(p.land_use) }}</span>
            <span class="meta">{{ p.pin }}</span>
          </div>
        </template>
      </template>
      <div v-else class="dd-empty">
        No matches. Try a place (e.g. Baluwatar), a PIN (KTM-04-012-0034), a kitta number, or ward/kitta (4/123).
      </div>
    </div>
  </div>
</template>
