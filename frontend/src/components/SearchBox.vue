<script setup>
import { ref } from 'vue'
import { api } from '../api.js'
import { selectParcel } from '../store.js'
import { label } from '../utils/format.js'
import Icon from './Icon.vue'

const q = ref('')
const open = ref(false)
const hits = ref([])
const state = ref('idle') // idle | loading | done | error
let timer
let controller

function onInput() {
  clearTimeout(timer)
  if (!q.value.trim()) {
    open.value = false
    return
  }
  timer = setTimeout(run, 250)
}

async function run() {
  controller?.abort()
  controller = new AbortController()
  state.value = 'loading'
  open.value = true
  try {
    hits.value = await api.search(q.value.trim(), controller.signal)
    state.value = 'done'
  } catch (e) {
    if (e.name !== 'AbortError') state.value = 'error'
  }
}

function choose(p) {
  open.value = false
  q.value = `Kitta ${p.kitta}, ward ${p.ward}`
  selectParcel(p.id, { fly: true })
}

function closeSoon() {
  setTimeout(() => { open.value = false }, 150)
}

function onKey(e) {
  if (e.key === 'Escape') {
    open.value = false
    e.target.blur()
  } else if (e.key === 'Enter' && hits.value.length && state.value === 'done') {
    choose(hits.value[0])
  }
}
</script>

<template>
  <div class="search" @focusout="closeSoon">
    <span class="s-icon"><Icon name="search" :size="16" /></span>
    <input v-model="q" type="search" placeholder="Search PIN or kitta number…" autocomplete="off"
           aria-label="Search PIN or kitta number" @input="onInput" @keydown="onKey" @focus="q && run()">
    <div class="dropdown" :class="{ open }" role="listbox">
      <div v-if="state === 'loading'" class="dd-empty">Searching…</div>
      <div v-else-if="state === 'error'" class="dd-empty">Search failed. Is the API running?</div>
      <template v-else-if="hits.length">
        <div class="dd-group">Parcels</div>
        <div v-for="p in hits" :key="p.id" class="dd-item" role="option" @mousedown.prevent="choose(p)">
          <span class="dd-icon"><Icon name="parcel" :size="16" /></span>
          Kitta {{ p.kitta }}<span class="dd-type">Ward {{ p.ward }} · {{ label(p.land_use) }}</span>
          <span class="meta">{{ p.pin }}</span>
        </div>
      </template>
      <div v-else class="dd-empty">
        No parcels found. Try a PIN (KTM-04-012-0034), a kitta number, or ward and kitta (4/123).
      </div>
    </div>
  </div>
</template>
