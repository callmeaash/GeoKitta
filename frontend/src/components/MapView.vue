<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { api } from '../api.js'
import { cancelDraw, selectParcel, store, toast } from '../store.js'
import { metresPerPixel } from '../utils/geo.js'
import { readLink, writeLink } from '../utils/link.js'
import Icon from './Icon.vue'

const OUTLINE_ZOOM = 17 // parcel outlines are loaded from this zoom
const LABEL_ZOOM = 19 // kitta numbers are drawn from this zoom
const CLICK_PX = 4 // click tolerance in screen pixels
const HOME = { center: [27.7085, 85.3206], zoom: 13 }
const COLORS = { parcel: '#1E3A8A', hover: '#2563EB', selected: '#EA580C', setback: '#7C3AED', buffer: '#0284C7' }
const OSM = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

const el = ref(null)
const zoom = ref(HOME.zoom)
const outlines = ref('hidden') // hidden | loading | shown | too_many | error
const tip = ref({ show: false, x: 0, y: 0, text: '' })

let map, bases, renderer, parcelsLayer, labelsLayer, selectedLayer, zoneLayer, featureLayer, drawLayer, resultsLayer
let pinLayer
let loadedBounds = null
let loadController = null
let hovered = null

/* ---------- Parcel outlines ---------- */

function parcelStyle() {
  return { color: COLORS.parcel, weight: 0.8, opacity: 0.85, fill: true, fillOpacity: 0 }
}

async function loadOutlines(force = false) {
  zoom.value = map.getZoom()
  if (!store.layers.parcels || map.getZoom() < OUTLINE_ZOOM) {
    parcelsLayer.clearLayers()
    labelsLayer.clearLayers()
    loadedBounds = null
    outlines.value = 'hidden'
    return
  }
  if (!force && loadedBounds && loadedBounds.contains(map.getBounds())) {
    drawLabels()
    return
  }
  const bounds = map.getBounds().pad(0.2)
  loadController?.abort()
  loadController = new AbortController()
  outlines.value = 'loading'
  try {
    const fc = await api.inView(bounds, loadController.signal)
    parcelsLayer.clearLayers()
    if (fc.too_many) {
      outlines.value = 'too_many'
      loadedBounds = null
      labelsLayer.clearLayers()
      return
    }
    parcelsLayer.addData(fc)
    loadedBounds = bounds
    outlines.value = 'shown'
    drawLabels()
  } catch (e) {
    if (e.name !== 'AbortError') outlines.value = 'error'
  }
}

function drawLabels() {
  labelsLayer.clearLayers()
  if (!store.layers.labels || map.getZoom() < LABEL_ZOOM) return
  const view = map.getBounds()
  parcelsLayer.eachLayer(layer => {
    const [lng, lat] = layer.feature.properties.label
    if (!view.contains([lat, lng])) return
    L.marker([lat, lng], {
      interactive: false,
      icon: L.divIcon({ className: 'parcel-label', html: String(layer.feature.properties.kitta), iconSize: null })
    }).addTo(labelsLayer)
  })
}

/* ---------- Click to identify (linear quadtree on the server) ---------- */

async function identifyAt(latlng) {
  const tolerance = Math.min(25, Math.max(0.5, CLICK_PX * metresPerPixel(latlng.lat, map.getZoom())))
  try {
    const res = await api.at(latlng.lat, latlng.lng, tolerance.toFixed(2))
    if (res.parcel) await selectParcel(res.parcel.id, { stats: res.stats })
    else {
      selectParcel(null)
      toast('No parcel here')
    }
  } catch (e) {
    toast(`Lookup failed: ${e.message}`)
  }
}

/* ---------- Drawing for the Select, Buffer and Measure tools ---------- */

const DRAW_STYLE = { color: '#0F766E', weight: 2.5, dashArray: '6 4', fillColor: '#0F766E', fillOpacity: 0.08 }
let finished = null // the last completed shape stays on the map until its results are cleared

function redrawSketch(cursor) {
  drawLayer.clearLayers()
  const d = store.draw || finished
  const pts = store.draw ? store.drawPoints.slice() : finished?.pts.slice() || []
  if (!d || !pts.length) return
  if (cursor) pts.push([cursor.lat, cursor.lng])
  if (d.kind === 'box' && pts.length >= 2) L.rectangle([pts[0], pts[pts.length - 1]], DRAW_STYLE).addTo(drawLayer)
  else if (d.kind === 'polygon' && pts.length >= 3) L.polygon(pts, DRAW_STYLE).addTo(drawLayer)
  else if (pts.length >= 2) L.polyline(pts, DRAW_STYLE).addTo(drawLayer)
  for (const p of store.draw ? store.drawPoints : finished.pts) {
    L.circleMarker(p, { radius: 4, color: '#0F766E', weight: 2, fillColor: '#fff', fillOpacity: 1 }).addTo(drawLayer)
  }
}

function finishDraw() {
  const d = store.draw
  if (!d) return
  const pts = store.drawPoints.slice()
  const need = { point: 1, box: 2, line: 2, polygon: 3 }[d.kind] || 1
  if (pts.length < need) return
  finished = { kind: d.kind, pts }
  store.drawResult = { purpose: d.purpose, kind: d.kind, latlngs: pts }
  store.draw = null
}

async function drawClick(e) {
  const d = store.draw
  const p = [e.latlng.lat, e.latlng.lng]
  if (d.kind === 'feature') {
    try {
      const tolerance = Math.max(30, 12 * metresPerPixel(e.latlng.lat, map.getZoom()))
      const feature = await api.nearestFeature(p[0], p[1], store.featureTypes, Math.min(500, tolerance))
      store.drawResult = { purpose: d.purpose, kind: 'feature', feature }
      store.draw = null
    } catch (err) {
      toast(err.status === 404 ? 'No road or river there. Click closer to one.' : err.message)
    }
    return
  }
  const last = store.drawPoints[store.drawPoints.length - 1]
  if (last && map.latLngToContainerPoint(last).distanceTo(e.containerPoint) < 4) return // double-click repeat
  if (d.kind === 'polygon' && store.drawPoints.length >= 3 &&
      map.latLngToContainerPoint(store.drawPoints[0]).distanceTo(e.containerPoint) < 10) {
    finishDraw() // clicked the first point again
    return
  }
  store.drawPoints = [...store.drawPoints, p]
  if (d.kind === 'point' || (d.kind === 'box' && store.drawPoints.length === 2)) finishDraw()
  else redrawSketch()
}

/* ---------- Highlights ---------- */

function showSelected(details) {
  selectedLayer.clearLayers()
  if (!details) return
  L.geoJSON(details.geometry, {
    renderer, interactive: false,
    style: { color: COLORS.selected, weight: 3, fillColor: '#FDBA74', fillOpacity: 0.35 }
  }).addTo(selectedLayer)
}

let resultsRequest = 0

async function showResults(results) {
  zoneLayer.clearLayers()
  resultsLayer.clearLayers()
  const ids = results ? results.list.parcels.map(p => p.id) : []
  const request = ++resultsRequest
  if (ids.length) {
    // results get their own outlines, so they show at any zoom, even where all parcels are not drawn
    api.outlines(ids).then(fc => { if (request === resultsRequest) resultsLayer.addData(fc) })
      .catch(e => toast(`Could not draw the results: ${e.message}`))
  }
  if (results?.list.zone && store.layers.zones) {
    const color = results.kind === 'setback' ? COLORS.setback : COLORS.buffer
    L.geoJSON(results.list.zone, {
      renderer, interactive: false, style: { color, weight: 1.5, opacity: 0.8, fillColor: color, fillOpacity: 0.14 }
    }).addTo(zoneLayer)
  }
}

function showFeature(feature) {
  featureLayer.clearLayers()
  if (!feature) return
  L.geoJSON(feature.geometry, { interactive: false, style: { color: '#0284C7', weight: 5, opacity: 0.55 } })
    .addTo(featureLayer)
}

/* ---------- Setup ---------- */

onMounted(() => {
  const link = readLink()
  map = L.map(el.value, { zoomControl: false, minZoom: 11, maxZoom: 20, doubleClickZoom: true })
    .setView(link.zoom ? [link.lat, link.lng] : HOME.center, link.zoom || HOME.zoom)
  map.setMaxBounds(L.latLngBounds([27.55, 85.15], [27.85, 85.50]))
  // "Light" is the same OpenStreetMap tiles with a grey CSS filter, so parcels stand out; no API key needed
  const osmTiles = className => L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 20, maxNativeZoom: 19, attribution: OSM, className
  })
  bases = { light: osmTiles('tiles-light'), osm: osmTiles('') }
  bases[store.layers.base].addTo(map)
  map.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>')
  L.control.scale({ imperial: false, position: 'bottomleft' }).addTo(map)

  renderer = L.canvas({ padding: 0.3, tolerance: 2 })
  zoneLayer = L.layerGroup().addTo(map)
  featureLayer = L.layerGroup().addTo(map)
  parcelsLayer = L.geoJSON(null, { renderer, style: parcelStyle }).addTo(map)
  resultsLayer = L.geoJSON(null, {
    renderer, interactive: false,
    style: { color: COLORS.selected, weight: 1.5, opacity: 1, fillColor: '#FDBA74', fillOpacity: 0.32 }
  }).addTo(map)
  selectedLayer = L.layerGroup().addTo(map)
  labelsLayer = L.layerGroup().addTo(map)
  drawLayer = L.layerGroup().addTo(map)
  pinLayer = L.layerGroup().addTo(map)

  parcelsLayer.on('mousemove', e => {
    if (store.draw) return
    const layer = e.layer
    if (hovered !== layer) {
      if (hovered) parcelsLayer.resetStyle(hovered)
      hovered = layer
      layer.setStyle({ color: COLORS.hover, weight: 2, fillColor: COLORS.hover, fillOpacity: 0.1 })
    }
    const p = layer.feature.properties
    tip.value = { show: true, x: e.containerPoint.x, y: e.containerPoint.y, text: `Kitta ${p.kitta} · Ward ${p.ward}` }
  })
  parcelsLayer.on('mouseout', () => {
    if (hovered) parcelsLayer.resetStyle(hovered)
    hovered = null
    tip.value = { ...tip.value, show: false }
  })

  map.on('click', e => (store.draw ? drawClick(e) : identifyAt(e.latlng)))
  map.on('dblclick', e => {
    if (store.draw && (store.draw.kind === 'line' || store.draw.kind === 'polygon')) {
      L.DomEvent.stop(e)
      finishDraw()
    }
  })
  map.on('mousemove', e => {
    if (store.draw && store.drawPoints.length && store.draw.kind !== 'point') redrawSketch(e.latlng)
  })
  map.on('moveend', () => {
    loadOutlines()
    updateLink()
  })
  map.on('zoomend', () => { zoom.value = map.getZoom() })
  window.addEventListener('keydown', onKey)
  loadOutlines()
  if (link.parcel) selectParcel(link.parcel, { fly: !link.zoom })
})

function updateLink() {
  const c = map.getCenter()
  writeLink({ zoom: map.getZoom(), lat: c.lat, lng: c.lng, parcel: store.selectedId })
}

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  map?.remove()
})

function onKey(e) {
  if (e.key === 'Escape' && store.draw) {
    cancelDraw()
    redrawSketch()
  } else if (e.key === 'Enter' && store.draw) finishDraw()
}

/* ---------- React to the rest of the app ---------- */

watch(() => store.details, showSelected)
watch(() => store.selectedId, () => map && updateLink())
watch(() => store.results, showResults)
watch(() => store.feature, showFeature)
watch(() => store.placePin, pin => {
  pinLayer.clearLayers()
  if (!pin) return
  L.circleMarker([pin.lat, pin.lng], { radius: 10, color: '#fff', weight: 3, fillColor: '#0F766E', fillOpacity: 1 })
    .bindTooltip(pin.name, { direction: 'top', offset: [0, -10], permanent: true, className: 'pin-label' })
    .addTo(pinLayer)
})
watch(() => store.layers.base, base => {
  for (const [name, layer] of Object.entries(bases)) {
    if (name === base) layer.addTo(map)
    else map.removeLayer(layer)
  }
})
watch(() => store.layers.parcels, () => loadOutlines(true))
watch(() => store.layers.labels, drawLabels)
watch(() => store.layers.zones, () => showResults(store.results))
watch(() => store.draw, d => {
  map.getContainer().classList.toggle('drawing', !!d)
  if (d) {
    finished = null
    tip.value = { ...tip.value, show: false }
    if (d.kind === 'line' || d.kind === 'polygon') map.doubleClickZoom.disable()
  } else {
    map.doubleClickZoom.enable()
  }
  redrawSketch()
})
watch(() => store.drawResult, r => {
  if (!r && !store.draw) {
    finished = null
    drawLayer.clearLayers()
  }
})
watch(() => store.drawPoints, pts => { if (store.draw && pts.length) redrawSketch() })
watch(() => store.flyTo, target => {
  if (!target) return
  if (target.home) map.flyTo(HOME.center, HOME.zoom)
  else if (target.geometry) map.flyToBounds(L.geoJSON(target.geometry).getBounds(), { maxZoom: 19, padding: [60, 60] })
  else if (target.bounds) map.flyToBounds(target.bounds, { maxZoom: 19, padding: [40, 40] })
  else if (target.center) map.flyTo(target.center, target.zoom || 17)
  store.flyTo = null
})

defineExpose({ finishDraw })
</script>

<template>
  <section class="map" aria-label="Parcel map">
    <div ref="el" class="leaflet-host"></div>

    <div class="basemap" role="group" aria-label="Base map">
      <button :aria-pressed="store.layers.base === 'light'" @click="store.layers.base = 'light'">Light</button>
      <button :aria-pressed="store.layers.base === 'osm'" @click="store.layers.base = 'osm'">OpenStreetMap</button>
    </div>

    <div class="controls">
      <div class="ctrl-group">
        <button aria-label="Zoom in" @click="map.zoomIn()"><Icon name="plus" :size="18" /></button>
        <button aria-label="Zoom out" @click="map.zoomOut()"><Icon name="minus" :size="18" /></button>
      </div>
      <div class="ctrl-group">
        <button aria-label="Show all of Kathmandu" @click="store.flyTo = { home: true }"><Icon name="locate" :size="18" /></button>
      </div>
    </div>

    <div v-if="store.draw" class="map-hint drawing-hint" role="status">
      <template v-if="store.draw.kind === 'point'">Click a point on the map</template>
      <template v-else-if="store.draw.kind === 'box'">Click two opposite corners</template>
      <template v-else-if="store.draw.kind === 'feature'">Click a road or river</template>
      <template v-else>Click to add points · double-click or Enter to finish</template>
      · <button class="link" @click="cancelDraw()">Cancel</button>
    </div>
    <div v-else-if="store.layers.parcels && outlines !== 'shown'" class="map-hint" role="status">
      <template v-if="outlines === 'loading'">Loading parcels…</template>
      <template v-else-if="outlines === 'too_many'">Too many parcels here. Zoom in to see outlines.</template>
      <template v-else-if="outlines === 'error'">Parcels could not be loaded. Is the API running?</template>
      <template v-else>Zoom in to see parcel outlines. Clicking anywhere still finds the parcel.</template>
    </div>

    <div class="legend">
      <h4>Legend</h4>
      <div class="lg-row"><span class="sw sw-parcel"></span>Parcel</div>
      <div class="lg-row"><span class="sw sw-sel"></span>Selected / found parcel</div>
      <div class="lg-row"><span class="sw sw-setback"></span>Setback zone</div>
      <div class="lg-row"><span class="sw sw-buffer"></span>Buffer zone</div>
    </div>

    <div class="tooltip" :style="{ display: tip.show ? 'block' : 'none', left: tip.x + 'px', top: tip.y + 'px' }">
      {{ tip.text }}
    </div>
    <div class="toast" :class="{ show: !!store.toast }" role="status">{{ store.toast }}</div>
  </section>
</template>
