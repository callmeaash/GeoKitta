<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { request } from '../../api.js'
import Icon from '../../components/Icon.vue'
import CoordinateEditor from '../../components/officer/CoordinateEditor.vue'
import OwnerPicker from '../../components/officer/OwnerPicker.vue'
import PreviewMap from '../../components/officer/PreviewMap.vue'
import ValidationList from '../../components/officer/ValidationList.vue'
import { toRopani } from '../../utils/area.js'
import { fmt } from '../../utils/format.js'

const router = useRouter()
const SOURCES = [
  { id: 'ts', label: 'Field survey – total station (±0.05 m)', source: 'field_survey', accuracy: 0.05 },
  { id: 'gnss', label: 'Field survey – GNSS RTK (±0.03 m)', source: 'field_survey', accuracy: 0.03 },
  { id: 'map', label: 'Digitised from map sheet (±1.0 m)', source: 'digitized', accuracy: 1.0 }
]

const form = reactive({ ward: '', map_sheet: '', kitta: '', parcel_type: 'private', land_use: 'residential',
  registered_area: '', source: 'ts', deed_ref: '', remarks: '' })
const points = ref([])
const crs = ref('utm')
const owners = ref([])
const picker = ref(null)
const check = ref(null)
const checking = ref(false)
const saving = ref(false)
const errors = ref([])
const confirmOverlap = ref(false)

const ready = computed(() => points.value.filter(p => p[0] != null && p[1] != null).length >= 3)
const shapes = computed(() => !check.value ? [] : [
  { geometry: check.value.geometry, kind: 'proposed' },
  ...check.value.report.overlaps.map(o => ({ geometry: o.geometry, kind: 'overlap' }))
])

let timer
let seq = 0
watch([points, crs, () => form.registered_area], () => {
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
    const result = await request('/api/officer/parcels/check', {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ points: points.value.filter(p => p[0] != null && p[1] != null), crs: crs.value,
        registered_area: Number(form.registered_area) || null })
    })
    if (mine !== seq) return
    check.value = result
    const s = result.suggestion
    if (s?.ward && !form.ward) Object.assign(form, { ward: s.ward, map_sheet: s.map_sheet })
    if (!form.registered_area && result.report.area_m2) form.registered_area = result.report.area_m2
  } catch (e) {
    if (mine === seq) check.value = { geometry: null, report: { checks: [{ id: 'input', status: 'fail', title: 'Cannot read the coordinates', detail: e.message }], overlaps: [] } }
  } finally {
    if (mine === seq) checking.value = false
  }
}

async function save(accept = false) {
  errors.value = []
  if (!picker.value?.ok) errors.value.push('Add the owners; their shares must add up to exactly 1.')
  if (!form.ward || !/^\d{9}$/.test(String(form.map_sheet))) errors.value.push('Ward and a 9-digit map sheet code are needed.')
  if (!ready.value) errors.value.push('Enter at least 3 corner points.')
  if (errors.value.length) return
  const src = SOURCES.find(s => s.id === form.source)
  saving.value = true
  try {
    const res = await fetch('/api/officer/parcels', {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        points: points.value.filter(p => p[0] != null && p[1] != null), crs: crs.value,
        ward: Number(form.ward), map_sheet: String(form.map_sheet), kitta: Number(form.kitta) || null,
        parcel_type: form.parcel_type, land_use: form.land_use, registered_area: Number(form.registered_area),
        geometry_source: src.source, accuracy_m: src.accuracy, deed_ref: form.deed_ref || null,
        remarks: form.remarks || null, owners: owners.value.map(o => ({ owner_id: o.id, share: o.share.trim() })),
        accept_issues: accept
      })
    })
    const data = await res.json()
    if (res.status === 201) {
      router.push({ path: `/officer/parcels/${data.parcel_id}`, query: { saved: `Kitta ${data.kitta} registered (${data.pin}), case ${data.case_id}.` } })
    } else if (res.status === 409 && data.report) {
      check.value = { ...check.value, report: data.report }
      confirmOverlap.value = true
    } else {
      errors.value = Array.isArray(data.detail) ? data.detail.map(d => d.msg.replace(/^Value error, /, '')) : [data.detail]
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
        <div class="crumbs"><RouterLink to="/officer">Dashboard</RouterLink><Icon name="chevronRight" :size="12" /><RouterLink to="/officer/parcels">Parcels</RouterLink><Icon name="chevronRight" :size="12" />Register parcel</div>
        <h1 class="page-title">Register parcel</h1>
        <p class="page-sub">For land not yet in the register. To change an existing parcel, find it under <RouterLink class="link" to="/officer/parcels">Parcels</RouterLink>.
          The boundary comes from surveyed corners and is validated before it can be saved.</p>
      </div>
    </div>
    <div v-if="errors.length" class="banner banner-error" role="alert"><Icon name="alert" :size="16" />
      <div><strong>Cannot save yet</strong><span v-for="e in errors" :key="e" style="display: block">{{ e }}</span></div></div>

    <div class="grid-2">
      <div class="stack">
        <section class="box">
          <div class="box-head"><div><h2 class="box-title"><Icon name="parcel" :size="18" />Boundary coordinates</h2>
            <p class="box-sub">Corner points from the field survey, in order around the parcel.</p></div></div>
          <CoordinateEditor v-model:points="points" v-model:crs="crs" />
          <div class="field" style="margin: 14px 0 0; max-width: 360px"><label for="src">Survey source</label>
            <select id="src" v-model="form.source"><option v-for="s in SOURCES" :key="s.id" :value="s.id">{{ s.label }}</option></select></div>
        </section>

        <section class="box">
          <div class="box-head"><h2 class="box-title"><Icon name="file" :size="18" />Parcel details</h2>
            <span v-if="check?.suggestion?.ward" class="tag tag-teal">Ward and sheet from neighbouring parcels</span></div>
          <div class="form-grid">
            <div class="field"><label>District / municipality</label><input class="input" value="Kathmandu (27) · KMC" readonly></div>
            <div class="field"><label for="ward">Ward</label>
              <select id="ward" v-model.number="form.ward"><option value="">Choose</option><option v-for="w in 32" :key="w" :value="w">{{ w }}</option></select></div>
            <div class="field"><label for="sheet">Map sheet code</label><input id="sheet" v-model="form.map_sheet" class="num" maxlength="9" placeholder="272040120"></div>
            <div class="field"><label for="kitta">Kitta No.</label>
              <input id="kitta" v-model="form.kitta" class="num" type="number" min="1" :placeholder="check?.suggestion?.kitta ? `next free: ${check.suggestion.kitta}` : 'next free number'">
              <span class="hint">Leave empty for the next free number on the sheet</span></div>
            <div class="field"><label for="ptype">Parcel type</label>
              <select id="ptype" v-model="form.parcel_type"><option value="private">Private</option><option value="public">Public</option><option value="government">Government</option><option value="guthi">Guthi</option></select></div>
            <div class="field"><label for="use">Land use</label>
              <select id="use" v-model="form.land_use"><option value="residential">Residential</option><option value="commercial">Commercial</option><option value="agricultural">Agricultural</option><option value="institutional">Institutional</option><option value="other">Other</option></select></div>
            <div class="field"><label for="reg">Registered area</label>
              <div class="input-wrap"><input id="reg" v-model="form.registered_area" class="num" type="number" min="0" step="0.01"><span class="suffix">m²</span></div>
              <span class="hint">{{ form.registered_area ? `${toRopani(Number(form.registered_area))} ropani-aana-paisa-daam` : 'Filled from the boundary; change it to the deed area' }}</span></div>
            <div class="field"><label for="deed">Deed reference (optional)</label><input id="deed" v-model="form.deed_ref"></div>
          </div>
        </section>

        <section class="box">
          <div class="box-head"><h2 class="box-title"><Icon name="users" :size="18" />Owners</h2></div>
          <OwnerPicker ref="picker" v-model="owners" />
        </section>
      </div>

      <div class="stack sticky">
        <section class="box">
          <div class="box-head"><div><h2 class="box-title"><Icon name="map" :size="18" />Preview</h2>
            <p class="box-sub">Updates as you edit the coordinates.</p></div></div>
          <PreviewMap :shapes="shapes" :height="400">
            <span><i class="sw sw-proposed"></i>New parcel</span><span><i class="sw sw-parcel"></i>Existing parcels</span>
            <span v-if="check?.report.overlaps.length"><i class="sw sw-overlap"></i>Overlap</span>
          </PreviewMap>
        </section>
        <section class="box">
          <div class="box-head"><h2 class="box-title"><Icon name="checkCircle" :size="18" />Validation</h2>
            <span v-if="check?.report.area_m2" class="tag">{{ fmt(check.report.area_m2) }} m² calculated</span></div>
          <ValidationList :checks="check?.report.checks || []" :busy="checking" />
        </section>
      </div>
    </div>

    <div class="footer-bar">
      <span class="left"><Icon name="info" :size="16" />Saving creates a registration case, the ownership records and the quadtree entry in one step.</span>
      <RouterLink class="btn btn-ghost" to="/officer">Cancel</RouterLink>
      <button class="btn btn-primary" :disabled="saving || !check?.report.ok && !check?.report.overlaps.length" @click="save(false)">
        <Icon name="check" :size="16" />{{ saving ? 'Saving…' : 'Register parcel' }}</button>
    </div>

    <div v-if="confirmOverlap" class="modal-backdrop open" role="dialog" aria-modal="true">
      <div class="modal">
        <div class="modal-head"><span class="modal-icon red"><Icon name="alert" :size="20" /></span>
          <div><h2>The boundary overlaps existing parcels</h2>
            <p>Correct the coordinates, or save it and record the overlap as an open issue for review.</p></div></div>
        <div class="modal-body">
          <ul class="checklist">
            <li v-for="o in check.report.overlaps" :key="o.parcel_id" class="err"><Icon name="alert" :size="16" />
              <div><strong>Kitta {{ o.kitta }} · {{ o.pin }}</strong><span>{{ fmt(o.area_m2) }} m² shared</span></div></li>
          </ul>
        </div>
        <div class="modal-foot">
          <button class="btn btn-primary" @click="confirmOverlap = false">Fix the coordinates</button>
          <button class="btn btn-danger" :disabled="saving" @click="confirmOverlap = false; save(true)">Save and flag for review</button>
        </div>
      </div>
    </div>
  </main>
</template>
