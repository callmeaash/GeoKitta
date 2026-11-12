<script setup>
import { computed, ref } from 'vue'
import { cancelDraw, startDraw, store } from '../../store.js'
import { fmt, fmtDistance } from '../../utils/format.js'
import { areaM2, pathLengthM } from '../../utils/geo.js'
import { toRopani } from '../../utils/area.js'
import Icon from '../Icon.vue'

const mode = ref(store.draw?.purpose === 'measure' && store.draw.kind === 'polygon' ? 'area' : 'distance')

const points = computed(() => {
  if (store.draw?.purpose === 'measure') return store.drawPoints
  const r = store.drawResult
  return r?.purpose === 'measure' ? r.latlngs : []
})
const length = computed(() => pathLengthM(points.value))
const closed = computed(() => (points.value.length >= 3 ? [...points.value, points.value[0]] : points.value))
const area = computed(() => areaM2(points.value))

function start(m) {
  mode.value = m
  startDraw(m === 'area' ? 'polygon' : 'line', 'measure')
}

function clear() {
  cancelDraw()
  store.drawResult = null
}
</script>

<template>
  <div class="panel-head"><span class="eyebrow">Measure</span></div>
  <div class="panel-body">
    <div class="field">
      <span class="label">Measure</span>
      <div class="seg full" role="group" aria-label="Measure">
        <button :class="{ on: mode === 'distance' }" @click="start('distance')">Distance</button>
        <button :class="{ on: mode === 'area' }" @click="start('area')">Area</button>
      </div>
    </div>
    <p class="note">Click points on the map. Double-click or press Enter to finish; Esc cancels.</p>

    <dl v-if="points.length" class="kv measure">
      <template v-if="mode === 'distance'">
        <dt>Distance</dt><dd>{{ fmtDistance(length) }}</dd>
        <dt>Points</dt><dd>{{ points.length }}</dd>
      </template>
      <template v-else>
        <dt>Area</dt>
        <dd>{{ fmt(area) }} m²<span class="sub">{{ toRopani(area) }} ropani-aana-paisa-daam</span></dd>
        <dt>Perimeter</dt><dd>{{ fmtDistance(pathLengthM(closed)) }}</dd>
        <dt>Points</dt><dd>{{ points.length }}</dd>
      </template>
    </dl>

    <div class="res-actions">
      <button v-if="!store.draw" class="btn btn-primary btn-sm" @click="start(mode)">
        <Icon name="ruler" :size="14" /> {{ points.length ? 'Measure again' : 'Start measuring' }}
      </button>
      <button v-if="points.length || store.draw" class="btn btn-ghost btn-sm" @click="clear">Clear</button>
    </div>
    <p class="note">Measurements are approximate (about ±0.5%); official areas come from the survey record.</p>
  </div>
</template>
