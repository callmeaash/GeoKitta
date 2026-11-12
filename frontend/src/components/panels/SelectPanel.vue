<script setup>
import { ref, watch } from 'vue'
import { api } from '../../api.js'
import { cancelDraw, startDraw, store, toast } from '../../store.js'
import Icon from '../Icon.vue'
import ResultsList from '../ResultsList.vue'

const mode = ref('box')
const busy = ref(false)

watch(() => store.drawResult, async r => {
  if (!r || r.purpose !== 'select') return
  const pts = r.latlngs
  const body = r.kind === 'box'
    ? { box: [Math.min(pts[0][1], pts[1][1]), Math.min(pts[0][0], pts[1][0]),
        Math.max(pts[0][1], pts[1][1]), Math.max(pts[0][0], pts[1][0])] }
    : { line: pts.map(([lat, lng]) => [lng, lat]) }
  busy.value = true
  try {
    store.results = { kind: 'select', tab: 'select', list: await api.select(body) }
  } catch (e) {
    toast(`Selection failed: ${e.message}`)
  } finally {
    busy.value = false
  }
})

function draw() {
  if (store.draw?.purpose === 'select') return cancelDraw()
  startDraw(mode.value, 'select')
}
</script>

<template>
  <div class="panel-head"><span class="eyebrow">Select parcels</span></div>
  <div class="panel-body">
    <div class="field">
      <span class="label">Select with</span>
      <div class="seg full" role="group" aria-label="Selection shape">
        <button :class="{ on: mode === 'box' }" @click="mode = 'box'">Rectangle</button>
        <button :class="{ on: mode === 'line' }" @click="mode = 'line'">Line</button>
      </div>
    </div>
    <p class="note">
      <template v-if="mode === 'box'">Every parcel the rectangle touches is selected.</template>
      <template v-else>Every parcel the line crosses is selected, e.g. along a planned pipe or road.</template>
    </p>
    <button class="btn btn-primary btn-block" :disabled="busy" @click="draw">
      <Icon :name="mode === 'box' ? 'select' : 'line'" :size="16" />
      {{ store.draw?.purpose === 'select' ? 'Cancel drawing' : mode === 'box' ? 'Draw rectangle' : 'Draw line' }}
    </button>
    <p v-if="busy" class="note">Searching…</p>
    <ResultsList v-if="store.results?.tab === 'select'" :results="store.results" />
  </div>
</template>
