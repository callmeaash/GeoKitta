<script setup>
import { computed } from 'vue'
import { clearResults, selectParcel, store } from '../store.js'
import { download, fmt, label, toCsv } from '../utils/format.js'
import Icon from './Icon.vue'
import StatsNote from './StatsNote.vue'

const props = defineProps({ results: { type: Object, required: true } })
const list = computed(() => props.results.list)

function exportCsv() {
  const rows = [['kitta', 'pin', 'ward', 'map_sheet', 'land_use', 'parcel_type', 'area_m2']].concat(
    list.value.parcels.map(p => [p.kitta, p.pin, p.ward, p.map_sheet, p.land_use, p.parcel_type, p.area_m2]))
  download(`geokitta_${props.results.kind}_${list.value.count}_parcels.csv`, toCsv(rows))
}
</script>

<template>
  <div class="results">
    <div class="res-summary">
      <strong>{{ list.count }} {{ list.count === 1 ? 'parcel' : 'parcels' }} found</strong>
      <span class="muted tabular">{{ fmt(list.total_area_m2) }} m²</span>
    </div>
    <p v-if="list.truncated" class="note">Showing the first {{ list.parcels.length }}. Use a smaller area to see all.</p>
    <div v-if="list.parcels.length" class="res-list">
      <button v-for="p in list.parcels" :key="p.id" class="res-row" @click="selectParcel(p.id, { fly: true })">
        <span class="k">Kitta {{ p.kitta }}<small>Ward {{ p.ward }} · {{ label(p.land_use) }}</small></span>
        <span class="a">{{ fmt(p.area_m2) }} m²</span>
        <Icon name="zoom" :size="14" />
      </button>
    </div>
    <div class="res-actions">
      <button class="btn btn-secondary btn-sm" :disabled="!list.parcels.length" @click="exportCsv">
        <Icon name="download" :size="14" /> Export list (CSV)
      </button>
      <button class="btn btn-ghost btn-sm" @click="clearResults()">Clear</button>
    </div>
    <StatsNote :stats="list.stats" />
  </div>
</template>
