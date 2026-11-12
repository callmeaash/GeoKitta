<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { request } from '../../api.js'
import Icon from '../../components/Icon.vue'
import CoordinateEditor from '../../components/officer/CoordinateEditor.vue'
import PreviewMap from '../../components/officer/PreviewMap.vue'
import ValidationList from '../../components/officer/ValidationList.vue'
import { fmt, label, sourceLabel } from '../../utils/format.js'

const route = useRoute()
const router = useRouter()
const id = Number(route.params.id)
const parcel = ref(null)
const loadError = ref('')
const points = ref([])
const crs = ref('utm')
const form = reactive({ reason: 'Boundary correction after field survey', surveyor: '', updateArea: false })
const check = ref(null)
const checking = ref(false)
const saving = ref(false)
const errors = ref([])
const confirmOverlap = ref(false)

onMounted(async () => {
  try {
    parcel.value = await request(`/api/parcels/${id}`)
  } catch (e) {
    loadError.value = e.status === 404 ? 'This parcel is not active (it may have been split).' : e.message
  }
})

function loadCurrent() { // a starting point for typed corrections; the corners still come from the survey
  points.value = parcel.value.geometry.coordinates[0].slice(0, -1).map(p => [p[0], p[1]])
  crs.value = 'wgs84'
}

const ready = computed(() => points.value.filter(p => p[0] != null && p[1] != null).length >= 3)
const shapes = computed(() => [
  { geometry: parcel.value?.geometry, kind: 'old' },
  ...(check.value ? [{ geometry: check.value.geometry, kind: 'new' },
    ...check.value.report.overlaps.map(o => ({ geometry: o.geometry, kind: 'overlap' }))] : [])
])
const change = computed(() => check.value?.report.area_m2 ? check.value.report.area_m2 - check.value.old_area_m2 : null)
const body = accept => ({ points: points.value.filter(p => p[0] != null && p[1] != null), crs: crs.value,
  reason: form.reason, surveyor: form.surveyor || null, update_registered_area: form.updateArea,
  registered_area: form.updateArea ? check.value?.report.area_m2 : null, accept_issues: accept })

let timer
let seq = 0
watch([points, crs], () => {
  clearTimeout(timer)
  timer = setTimeout(runCheck, 400)
}, { deep: true })

async function runCheck() {
  if (!ready.value) {
    check.value = null
    return
  }
  const mine = ++seq
  checking.value = true
  try {
    const r = await request(`/api/officer/parcels/${id}/boundary/check`, {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body(false))
    })
    if (mine === seq) check.value = r
  } catch (e) {
    if (mine === seq) check.value = { geometry: null, report: { checks: [{ id: 'input', status: 'fail', title: 'Cannot read the coordinates', detail: e.message }], overlaps: [] } }
  } finally {
    if (mine === seq) checking.value = false
  }
}

async function save(accept = false) {
  errors.value = []
  saving.value = true
  try {
    const res = await fetch(`/api/officer/parcels/${id}/boundary`, {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body(accept))
    })
    const data = await res.json()
    if (res.ok) {
      router.push({ path: `/officer/parcels/${id}`, query: { saved: `Boundary of ${data.pin} updated, case ${data.case_id}. The old boundary is kept in history.` } })
    } else if (res.status === 409 && data.report) {
      check.value = { ...check.value, report: data.report }
      confirmOverlap.value = true
    } else {
      errors.value = Array.isArray(data.detail) ? data.detail.map(d => d.msg) : [data.detail]
    }
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <main class="page">
    <div class="page-head">
      <div>
        <div class="crumbs"><RouterLink to="/officer">Dashboard</RouterLink><Icon name="chevronRight" :size="12" /><RouterLink to="/officer/parcels">Parcels</RouterLink><Icon name="chevronRight" :size="12" />
          <RouterLink :to="`/officer/parcels/${id}`">Kitta {{ parcel?.kitta || '…' }}</RouterLink><Icon name="chevronRight" :size="12" />Update boundary</div>
        <h1 class="page-title">Update boundary{{ parcel ? ` — Kitta ${parcel.kitta}` : '' }}</h1>
        <p class="page-sub"><span class="tag">Boundary update</span> The old boundary is kept in the parcel's history.</p>
      </div>
      <div class="head-actions"><RouterLink class="btn btn-secondary" :to="{ path: '/', hash: `#parcel=${id}` }"><Icon name="map" :size="16" />Show on map</RouterLink></div>
    </div>
    <div v-if="loadError" class="banner banner-error"><Icon name="alert" :size="16" /><span>{{ loadError }}</span></div>
    <div v-if="errors.length" class="banner banner-error"><Icon name="alert" :size="16" /><span>{{ errors.join(' ') }}</span></div>

    <div v-if="parcel" class="grid-2">
      <div class="stack">
        <section class="box">
          <div class="box-head"><h2 class="box-title"><Icon name="file" :size="18" />Current record</h2></div>
          <dl class="kv wide" style="margin: 0">
            <dt>Kitta / PIN</dt><dd>{{ parcel.kitta }} · {{ parcel.pin }}</dd>
            <dt>Ward / sheet</dt><dd>Ward {{ parcel.ward }} · Map sheet {{ parcel.map_sheet }}</dd>
            <dt>Registered area</dt><dd>{{ fmt(parcel.area_m2) }} m²<span class="sub">Boundary encloses {{ fmt(parcel.boundary_area_m2) }} m²</span></dd>
            <dt>Land use</dt><dd>{{ label(parcel.land_use) }}</dd>
            <dt>Last survey</dt><dd>{{ sourceLabel(parcel.geometry_source) }}<span v-if="parcel.accuracy_m" class="sub">±{{ parcel.accuracy_m }} m</span></dd>
          </dl>
        </section>
        <section class="box">
          <div class="box-head"><div><h2 class="box-title"><Icon name="parcel" :size="18" />New survey coordinates</h2>
            <p class="box-sub">Corners from the new field survey, in order around the parcel.</p></div>
            <button class="btn btn-ghost btn-sm" type="button" @click="loadCurrent"><Icon name="edit" :size="14" />Start from current corners</button></div>
          <CoordinateEditor v-model:points="points" v-model:crs="crs" />
          <div class="form-grid" style="margin-top: 16px">
            <div class="field"><label for="surveyor">Surveyor</label><input id="surveyor" v-model="form.surveyor" placeholder="Name of the surveyor"></div>
            <div class="field"><label for="reason">Reason</label>
              <select id="reason" v-model="form.reason"><option>Boundary correction after field survey</option><option>Court order</option><option>Road widening</option></select></div>
            <label class="check span-2"><input v-model="form.updateArea" type="checkbox">Also set the registered area to the new boundary area</label>
          </div>
        </section>
      </div>
      <div class="stack sticky">
        <section class="box">
          <div class="box-head"><h2 class="box-title"><Icon name="map" :size="18" />Old and new boundary</h2></div>
          <PreviewMap :shapes="shapes" :height="360">
            <span><i class="sw sw-old"></i>Old boundary</span><span><i class="sw sw-new"></i>New boundary</span>
            <span v-if="check?.report.overlaps.length"><i class="sw sw-overlap"></i>Overlap</span>
          </PreviewMap>
        </section>
        <section v-if="change !== null" class="box">
          <div class="compare-big">
            <div><div class="cv">{{ fmt(check.old_area_m2) }} m²</div><div class="cl">Old boundary</div></div>
            <Icon name="arrowRight" :size="20" />
            <div><div class="cv">{{ fmt(check.report.area_m2) }} m²</div><div class="cl">New boundary</div></div>
            <span class="delta status" :class="Math.abs(change) < 1 ? 'st-green' : 'st-amber'">{{ change >= 0 ? '+' : '' }}{{ fmt(change) }} m²</span>
          </div>
        </section>
        <section class="box">
          <div class="box-head"><h2 class="box-title"><Icon name="checkCircle" :size="18" />Validation</h2></div>
          <ValidationList :checks="check?.report.checks || []" :busy="checking" />
        </section>
      </div>
    </div>

    <div v-if="parcel" class="footer-bar">
      <span class="left"><Icon name="info" :size="16" />Saving keeps the old boundary in history and updates the quadtree in the same transaction.</span>
      <RouterLink class="btn btn-ghost" :to="`/officer/parcels/${id}`">Cancel</RouterLink>
      <button class="btn btn-primary" :disabled="saving || !check || !check.report.ok && !check.report.overlaps.length" @click="save(false)">
        <Icon name="check" :size="16" />{{ saving ? 'Saving…' : 'Save new boundary' }}</button>
    </div>

    <div v-if="confirmOverlap" class="modal-backdrop open" role="dialog" aria-modal="true">
      <div class="modal">
        <div class="modal-head"><span class="modal-icon red"><Icon name="alert" :size="20" /></span>
          <div><h2>The new boundary overlaps neighbouring parcels</h2><p>Correct the coordinates, or save and record the overlap for review.</p></div></div>
        <div class="modal-body"><ul class="checklist">
          <li v-for="o in check.report.overlaps" :key="o.parcel_id" class="err"><Icon name="alert" :size="16" />
            <div><strong>Kitta {{ o.kitta }} · {{ o.pin }}</strong><span>{{ fmt(o.area_m2) }} m² shared</span></div></li></ul></div>
        <div class="modal-foot">
          <button class="btn btn-primary" @click="confirmOverlap = false">Fix the coordinates</button>
          <button class="btn btn-danger" :disabled="saving" @click="confirmOverlap = false; save(true)">Save and flag for review</button>
        </div>
      </div>
    </div>
  </main>
</template>
