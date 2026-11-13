<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { api } from '../../api.js'

/** Read-only map: the proposed shapes among the existing parcels. Nothing here can change a boundary. */
const props = defineProps({
  shapes: { type: Array, default: () => [] }, // [{ geometry, kind: proposed|old|parent|childA|childB|childC|overlap }]
  height: { type: Number, default: 380 }
})

const STYLES = {
  proposed: { color: '#0F766E', weight: 2.5, dashArray: '7 4', fillColor: '#0F766E', fillOpacity: 0.15 },
  new: { color: '#0F766E', weight: 3, fillColor: '#0F766E', fillOpacity: 0.12 },
  old: { color: '#64748B', weight: 2.5, dashArray: '7 4', fill: false },
  parent: { color: '#64748B', weight: 2.5, dashArray: '7 4', fill: false },
  childA: { color: '#0F766E', weight: 2.5, fillColor: '#0F766E', fillOpacity: 0.24 },
  childB: { color: '#2563EB', weight: 2.5, fillColor: '#2563EB', fillOpacity: 0.2 },
  childC: { color: '#7C3AED', weight: 2.5, fillColor: '#7C3AED', fillOpacity: 0.2 },
  overlap: { color: '#DC2626', weight: 1.5, fillColor: '#DC2626', fillOpacity: 0.45 },
  issueA: { color: '#DC2626', weight: 2.5, fillColor: '#DC2626', fillOpacity: 0.06 },
  issueB: { color: '#D97706', weight: 2.5, fillColor: '#D97706', fillOpacity: 0.08 }
}

const el = ref(null)
let map, shapesLayer, neighbours
let lastKey = ''

function draw() {
  shapesLayer.clearLayers()
  const valid = props.shapes.filter(s => s.geometry)
  for (const s of valid) L.geoJSON(s.geometry, { style: STYLES[s.kind] || STYLES.proposed, interactive: false }).addTo(shapesLayer)
  if (!valid.length) return
  const bounds = shapesLayer.getBounds()
  const key = bounds.toBBoxString()
  if (key !== lastKey) { // refit and reload neighbours only when the shapes move
    lastKey = key
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 20 })
    loadNeighbours(bounds.pad(1.5))
  }
}

async function loadNeighbours(bounds) {
  try {
    const fc = await api.inView(bounds)
    neighbours.clearLayers()
    if (!fc.too_many) neighbours.addData(fc)
  } catch { /* the preview still works without neighbours */ }
}

onMounted(() => {
  map = L.map(el.value, { zoomControl: true, attributionControl: true, maxZoom: 21, preferCanvas: true })
    .setView([27.7085, 85.3206], 13)
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 21, maxNativeZoom: 19, className: 'tiles-light',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map)
  map.attributionControl.setPrefix(false)
  neighbours = L.geoJSON(null, { interactive: false, style: { color: '#1E3A8A', weight: 0.8, opacity: 0.6, fill: false } }).addTo(map)
  shapesLayer = L.featureGroup().addTo(map)
  draw()
})
onBeforeUnmount(() => map?.remove())
watch(() => props.shapes, () => map && draw(), { deep: true })
</script>

<template>
  <div class="preview-box">
    <div ref="el" :style="{ height: height + 'px' }"></div>
    <div class="map-legend-inline"><slot /></div>
  </div>
</template>

<style scoped>
.preview-box { position: relative; isolation: isolate; border-radius: var(--radius-md); overflow: hidden;
  border: 1px solid var(--color-border); background: var(--map-land); }
.preview-box .map-legend-inline { z-index: 1000; }
</style>
