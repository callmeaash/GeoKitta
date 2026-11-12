<script setup>
import { computed, ref } from 'vue'
import { parseFile, parseTable } from '../../utils/survey.js'
import Icon from '../Icon.vue'

/** Survey corners as [[x, y], ...] in the chosen system; typed, pasted or uploaded, never drawn. */
const points = defineModel('points', { type: Array, required: true })
const crs = defineModel('crs', { type: String, default: 'utm' })
const error = ref('')
const pasting = ref(false)
const pasteText = ref('')
const fileInput = ref(null)
const dragging = ref(false)

const labels = computed(() => (crs.value === 'utm' ? ['Easting (m)', 'Northing (m)'] : ['Longitude', 'Latitude']))
const step = computed(() => (crs.value === 'utm' ? '0.01' : '0.0000001'))

function setCell(i, j, value) {
  const next = points.value.map(p => p.slice())
  next[i][j] = value === '' ? null : Number(value)
  points.value = next
}
function addRow() { points.value = [...points.value, [null, null]] }
function removeRow(i) { points.value = points.value.filter((_, n) => n !== i) }

function load(result) {
  points.value = result.points
  crs.value = result.crs
  error.value = ''
}
function applyPaste() {
  try {
    load(parseTable(pasteText.value))
    pasting.value = false
    pasteText.value = ''
  } catch (e) {
    error.value = e.message
  }
}
async function readFile(file) {
  if (!file) return
  try {
    load(await parseFile(file))
  } catch (e) {
    error.value = `${file.name}: ${e.message}`
  }
}
function onDrop(e) {
  dragging.value = false
  readFile(e.dataTransfer.files[0])
}
</script>

<template>
  <div class="coord-editor" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave="dragging = false"
       @drop.prevent="onDrop">
    <div class="field" style="max-width: 320px">
      <label>Coordinate system</label>
      <select v-model="crs">
        <option value="utm">UTM 45N (EPSG:32645) · metres</option>
        <option value="wgs84">Longitude / latitude (WGS 84)</option>
      </select>
    </div>
    <div class="tbl-wrap">
      <table class="tbl coord-tbl">
        <thead><tr><th>Point</th><th style="text-align: right">{{ labels[0] }}</th>
          <th style="text-align: right">{{ labels[1] }}</th><th></th></tr></thead>
        <tbody>
          <tr v-for="(p, i) in points" :key="i">
            <td>{{ i + 1 }}</td>
            <td><input class="num" type="number" :step="step" :value="p[0]" :aria-label="`Point ${i + 1} ${labels[0]}`"
                       @change="setCell(i, 0, $event.target.value)"></td>
            <td><input class="num" type="number" :step="step" :value="p[1]" :aria-label="`Point ${i + 1} ${labels[1]}`"
                       @change="setCell(i, 1, $event.target.value)"></td>
            <td><button class="icon-btn" type="button" :aria-label="`Remove point ${i + 1}`" @click="removeRow(i)">
              <Icon name="x" :size="16" /></button></td>
          </tr>
          <tr v-if="!points.length"><td colspan="4" class="muted">No points yet. Type them, paste them, or drop a survey file here.</td></tr>
        </tbody>
      </table>
    </div>
    <div class="coord-tools">
      <button class="btn btn-secondary btn-sm" type="button" @click="addRow"><Icon name="plus" :size="14" />Add point</button>
      <button class="btn btn-ghost btn-sm" type="button" @click="pasting = !pasting"><Icon name="clipboard" :size="14" />Paste rows</button>
      <button class="btn btn-ghost btn-sm" type="button" @click="fileInput.click()"><Icon name="upload" :size="14" />Upload CSV or GeoJSON</button>
      <input ref="fileInput" type="file" accept=".csv,.txt,.json,.geojson" hidden @change="readFile($event.target.files[0]); $event.target.value = ''">
      <span class="hint" style="margin-left: auto">{{ points.length }} corners · the ring is closed automatically</span>
    </div>
    <div v-if="pasting" class="field" style="margin-top: 12px">
      <label>Paste "easting, northing" rows (from a spreadsheet or total station export)</label>
      <textarea v-model="pasteText" class="num" placeholder="335639.03, 3066479.34&#10;335639.75, 3066471.96&#10;…"></textarea>
      <div><button class="btn btn-primary btn-sm" type="button" @click="applyPaste">Use these points</button></div>
    </div>
    <p v-if="error" class="banner banner-error" style="margin: 12px 0 0"><Icon name="alert" :size="16" />{{ error }}</p>
  </div>
</template>

<style scoped>
.coord-editor { border-radius: var(--radius-md); transition: box-shadow .12s; }
.coord-editor.dragging { box-shadow: 0 0 0 3px rgba(15, 118, 110, .25); background: var(--color-primary-light); }
.coord-editor .tbl-wrap { max-height: 320px; overflow-y: auto; border: 1px solid var(--color-border); border-radius: var(--radius-md); }
</style>
