<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../../api.js'
import { cancelDraw, startDraw, store, toast } from '../../store.js'
import { fmt, label, measuredFrom } from '../../utils/format.js'
import Icon from '../Icon.vue'
import ResultsList from '../ResultsList.vue'

const source = ref('feature') // point | line | feature
const distance = ref(15)
const ruleId = ref('custom')
const rules = ref([])
const shape = ref(null) // [lat, lng] points of the drawn point or line
const busy = ref(false)

onMounted(async () => {
  try {
    rules.value = await api.rules()
  } catch {
    rules.value = []
  }
})

const featureRules = computed(() =>
  store.feature ? rules.value.filter(r => r.feature_type === store.feature.feature_type) : [])
const rule = computed(() => featureRules.value.find(r => r.id === ruleId.value) || null)
const ready = computed(() => (source.value === 'feature' ? !!store.feature : !!shape.value))

watch(() => store.feature, () => {
  // pick the strictest rule for this kind of feature, or a custom distance if it has none
  const best = [...featureRules.value].sort((a, b) => b.distance_m - a.distance_m)[0]
  ruleId.value = best ? best.id : 'custom'
})

watch(() => store.drawResult, r => {
  if (!r || r.purpose !== 'buffer') return
  if (r.kind === 'feature') {
    store.feature = r.feature
    source.value = 'feature'
  } else {
    shape.value = r.latlngs
    source.value = r.kind === 'point' ? 'point' : 'line'
    if (r.nearby) {
      r.nearby = false // run once, not every time the panel opens
      distance.value = 50
      run()
    }
  }
}, { immediate: true })

function pick() {
  if (store.draw?.purpose === 'buffer') return cancelDraw()
  startDraw(source.value === 'feature' ? 'feature' : source.value, 'buffer')
}

function setSource(s) {
  source.value = s
  shape.value = null
}

async function run() {
  const body = { distance_m: distance.value }
  if (source.value === 'feature') {
    body.feature_id = store.feature.id
    if (rule.value) body.rule_id = rule.value.id
  } else if (source.value === 'point') {
    body.point = [shape.value[0][1], shape.value[0][0]]
  } else {
    body.line = shape.value.map(([lat, lng]) => [lng, lat])
  }
  busy.value = true
  try {
    const list = await api.buffer(body)
    store.results = { kind: rule.value ? 'setback' : 'buffer', tab: 'buffer', list }
  } catch (e) {
    toast(`Search failed: ${e.message}`)
  } finally {
    busy.value = false
  }
}

const pickLabel = computed(() => {
  if (store.draw?.purpose === 'buffer') return 'Cancel'
  if (source.value === 'feature') return store.feature ? 'Pick another' : 'Pick on map'
  if (source.value === 'point') return shape.value ? 'Pick another point' : 'Pick a point'
  return shape.value ? 'Draw another line' : 'Draw a line'
})
</script>

<template>
  <div class="panel-head"><span class="eyebrow">Buffer and setback search</span></div>
  <div class="panel-body">
    <div class="field">
      <span class="label">Search from</span>
      <div class="seg full" role="group" aria-label="Search from">
        <button :class="{ on: source === 'feature' }" @click="setSource('feature')">Road/river</button>
        <button :class="{ on: source === 'point' }" @click="setSource('point')">Point</button>
        <button :class="{ on: source === 'line' }" @click="setSource('line')">Line</button>
      </div>
    </div>

    <div class="field">
      <span class="label">{{ source === 'feature' ? 'Feature' : source === 'point' ? 'Point' : 'Line' }}</span>
      <div class="pick-row">
        <div class="input-like">
          <Icon :name="source === 'feature' ? (store.feature?.feature_type.match(/river|stream/) ? 'waves' : 'road') : source"
                :size="16" />
          <span v-if="source === 'feature' && store.feature" class="pick-name">
            {{ store.feature.name || `Unnamed ${label(store.feature.feature_type).toLowerCase()}` }}
            <span class="muted">· {{ label(store.feature.feature_type) }}</span>
          </span>
          <span v-else-if="source !== 'feature' && shape" class="pick-name">
            {{ source === 'point' ? 'Point picked' : `Line with ${shape.length} points` }}
          </span>
          <span v-else class="muted">Not chosen yet</span>
        </div>
        <button class="btn btn-secondary btn-sm" @click="pick">{{ pickLabel }}</button>
      </div>
      <span v-if="source === 'feature' && store.feature" class="hint">
        {{ store.feature.ways }} OSM way{{ store.feature.ways > 1 ? 's' : '' }} with this name<span
          v-if="store.feature.width_m">, about {{ fmt(store.feature.width_m) }} m wide</span>
      </span>
    </div>

    <div v-if="source === 'feature' && store.feature" class="field">
      <label for="buf-rule">Setback rule</label>
      <select id="buf-rule" v-model="ruleId">
        <option v-for="r in featureRules" :key="r.id" :value="r.id">
          {{ fmt(r.distance_m) }} m from the {{ measuredFrom(r.measured_from) }} ({{ r.source }})
        </option>
        <option value="custom">Custom distance from the centre line</option>
      </select>
      <span v-if="rule?.note" class="hint">{{ rule.note }}</span>
    </div>

    <div v-if="!rule" class="field">
      <label for="buf-d">Distance</label>
      <div class="range-row">
        <input id="buf-d" v-model.number="distance" type="range" min="5" max="200" step="1">
        <span class="range-val">{{ distance }} m</span>
      </div>
    </div>

    <button class="btn btn-primary btn-block" :disabled="!ready || busy" @click="run">
      <Icon name="search" :size="16" /> {{ busy ? 'Searching…' : 'Find parcels' }}
    </button>
    <ResultsList v-if="store.results?.tab === 'buffer'" :results="store.results" />
    <p v-else class="note">Parcels that touch the zone are highlighted on the map and listed here.</p>
  </div>
</template>
