<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { request } from '../../api.js'
import Icon from '../../components/Icon.vue'
import OwnershipCard from '../../components/OwnershipCard.vue'
import RokkaDialog from '../../components/officer/RokkaDialog.vue'
import PreviewMap from '../../components/officer/PreviewMap.vue'
import { toRopani } from '../../utils/area.js'
import { fmt, label, sourceLabel, statusClass, txnLabel } from '../../utils/format.js'

const route = useRoute()
const id = computed(() => Number(route.params.id))
const rec = ref(null)
const error = ref('')
const editing = ref(false)
const form = reactive({ parcel_type: '', land_use: '', registered_area: '', reason: '' })
const saving = ref(false)
const message = ref(typeof route.query.saved === 'string' ? route.query.saved : '')
const warning = ref('')
const formError = ref('')
const placing = ref(false)
const ownershipKey = ref(0)

async function rokkaPlaced(r) {
  placing.value = false
  message.value = `Rokka placed, case ${r.case_id}. Transfers are blocked until it is released.`
  ownershipKey.value++
  await load()
}

async function load() {
  error.value = ''
  try {
    rec.value = await request(`/api/officer/parcels/${id.value}`)
  } catch (e) {
    rec.value = null
    error.value = e.status === 404 ? 'No parcel with this ID.' : e.message
  }
}
watch(id, load, { immediate: true })

const active = computed(() => rec.value?.status === 'active')
const shapes = computed(() => (rec.value ? [{ geometry: rec.value.geometry, kind: active.value ? 'new' : 'old' }] : []))

function startEdit() {
  Object.assign(form, { parcel_type: rec.value.parcel_type, land_use: rec.value.land_use,
    registered_area: rec.value.area_m2, reason: '' })
  formError.value = ''
  editing.value = true
}

async function saveDetails() {
  formError.value = ''
  const body = { reason: form.reason.trim() }
  if (form.parcel_type !== rec.value.parcel_type) body.parcel_type = form.parcel_type
  if (form.land_use !== rec.value.land_use) body.land_use = form.land_use
  if (Number(form.registered_area) !== rec.value.area_m2) body.registered_area = Number(form.registered_area)
  if (Object.keys(body).length === 1) {
    formError.value = 'Nothing has changed.'
    return
  }
  if (body.reason.length < 3) {
    formError.value = 'Give a reason for the correction (it is recorded in the case).'
    return
  }
  saving.value = true
  try {
    const r = await request(`/api/officer/parcels/${id.value}`, {
      method: 'PATCH', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    })
    message.value = `Details corrected, case ${r.case_id}.`
    warning.value = r.warning ? `Recorded for review: ${r.warning}` : ''
    editing.value = false
    await load()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <main class="page">
    <div class="page-head">
      <div>
        <div class="crumbs"><RouterLink to="/officer">Dashboard</RouterLink><Icon name="chevronRight" :size="12" />
          <RouterLink to="/officer/parcels">Parcels</RouterLink><Icon name="chevronRight" :size="12" />{{ rec?.pin || '…' }}</div>
        <h1 class="page-title">{{ rec ? `Kitta ${rec.kitta} · Ward ${rec.ward}` : error ? 'Parcel' : 'Loading…' }}
          <span v-if="rec" class="status" :class="active ? 'st-green' : 'st-grey'">{{ label(rec.status) }}</span></h1>
        <p v-if="rec" class="page-sub">{{ rec.pin }} · Map sheet {{ rec.map_sheet }} · Kathmandu Metropolitan City</p>
      </div>
      <div v-if="rec" class="head-actions">
        <RouterLink class="btn btn-secondary" :to="{ path: '/', hash: `#parcel=${rec.id}` }"><Icon name="map" :size="16" />Show on map</RouterLink>
        <RouterLink class="btn btn-secondary" :to="`/officer/parcels/${rec.id}/history`"><Icon name="clock" :size="16" />History</RouterLink>
        <template v-if="active">
          <RouterLink class="btn btn-secondary" :to="`/officer/parcels/${rec.id}/transfer`"><Icon name="transfer" :size="16" />Transfer ownership</RouterLink>
          <RouterLink class="btn btn-secondary" :to="`/officer/parcels/${rec.id}/split`"><Icon name="split" :size="16" />Split</RouterLink>
          <RouterLink class="btn btn-primary" :to="`/officer/parcels/${rec.id}/boundary`"><Icon name="edit" :size="16" />Update boundary</RouterLink>
        </template>
      </div>
    </div>

    <div v-if="message" class="banner banner-success" role="status"><Icon name="checkCircle" :size="16" /><span>{{ message }}</span></div>
    <div v-if="warning" class="banner banner-warning"><Icon name="alert" :size="16" /><span>{{ warning }}</span></div>
    <div v-if="error" class="banner banner-error"><Icon name="alert" :size="16" /><span>{{ error }}</span></div>
    <div v-if="rec && !active" class="banner banner-info"><Icon name="info" :size="16" />
      <span>This parcel was retired<template v-if="rec.children.length"> when it was split into
        <template v-for="(c, n) in rec.children" :key="c.id"><RouterLink class="link" :to="`/officer/parcels/${c.id}`">kitta {{ c.kitta }}</RouterLink>{{ n < rec.children.length - 1 ? ', ' : '' }}</template></template>.
        It can no longer be changed.</span></div>

    <div v-if="rec" class="grid-2">
      <div class="stack">
        <section class="box">
          <div class="box-head"><h2 class="box-title"><Icon name="file" :size="18" />Record</h2>
            <button v-if="active && !editing" class="btn btn-ghost btn-sm" @click="startEdit"><Icon name="edit" :size="14" />Correct details</button></div>
          <dl v-if="!editing" class="kv wide" style="margin: 0">
            <dt>Parcel type</dt><dd>{{ label(rec.parcel_type) }}</dd>
            <dt>Land use</dt><dd>{{ label(rec.land_use) }}</dd>
            <dt>Registered area</dt><dd>{{ fmt(rec.area_m2) }} m²<span class="sub">{{ toRopani(rec.area_m2) }} ropani-aana-paisa-daam</span></dd>
            <dt>Boundary area</dt><dd>{{ fmt(rec.boundary_area_m2) }} m²<span class="sub">{{ rec.boundary_versions }} earlier boundary version(s) in history</span></dd>
            <dt>Geometry</dt><dd>{{ sourceLabel(rec.geometry_source) }}<span v-if="rec.accuracy_m" class="sub">±{{ rec.accuracy_m }} m</span></dd>
            <dt>Last changed</dt><dd>{{ new Date(rec.updated_at).toLocaleDateString('en-CA') }}</dd>
          </dl>
          <form v-else @submit.prevent="saveDetails">
            <div class="form-grid">
              <div class="field"><label for="ptype">Parcel type</label>
                <select id="ptype" v-model="form.parcel_type"><option value="private">Private</option><option value="public">Public</option><option value="government">Government</option><option value="guthi">Guthi</option></select></div>
              <div class="field"><label for="use">Land use</label>
                <select id="use" v-model="form.land_use"><option value="residential">Residential</option><option value="commercial">Commercial</option><option value="agricultural">Agricultural</option><option value="institutional">Institutional</option><option value="other">Other</option></select></div>
              <div class="field"><label for="area">Registered area</label>
                <div class="input-wrap"><input id="area" v-model="form.registered_area" type="number" min="0" step="0.01" class="num"><span class="suffix">m²</span></div>
                <span class="hint">Boundary encloses {{ fmt(rec.boundary_area_m2) }} m²</span></div>
              <div class="field"><label for="reason">Reason</label><input id="reason" v-model="form.reason" placeholder="e.g. land use changed on the ground"></div>
            </div>
            <p class="hint" style="margin-top: 0">Saved as a samsodhan (correction) case. The boundary itself changes only through new survey coordinates.</p>
            <div v-if="formError" class="banner banner-error"><Icon name="alert" :size="16" /><span>{{ formError }}</span></div>
            <div class="res-actions">
              <button class="btn btn-primary btn-sm" type="submit" :disabled="saving"><Icon name="check" :size="14" />{{ saving ? 'Saving…' : 'Save correction' }}</button>
              <button class="btn btn-ghost btn-sm" type="button" @click="editing = false">Cancel</button>
            </div>
          </form>
        </section>

        <section class="box">
          <OwnershipCard :key="ownershipKey" :parcel-id="rec.id" />
          <button v-if="active" class="btn btn-ghost btn-sm" @click="placing = true"><Icon name="lock" :size="14" />Place rokka (hold)</button>
        </section>

        <section class="box flush">
          <div class="box-head"><div><h2 class="box-title">Cases</h2><p class="box-sub">Registrations, deeds, boundary updates and splits</p></div></div>
          <div class="tbl-wrap">
            <table class="tbl">
              <thead><tr><th>Case ID</th><th>Type</th><th>Date</th><th>Officer</th><th>Status</th></tr></thead>
              <tbody>
                <tr v-for="c in rec.cases" :key="c.case_id" :title="c.remarks || ''">
                  <td class="num">{{ c.case_id }}</td><td>{{ txnLabel(c.txn_type) }}</td><td class="num">{{ c.deed_date || '—' }}</td>
                  <td>{{ c.officer }}</td><td><span class="status" :class="statusClass(c.status)">{{ label(c.status) }}</span></td>
                </tr>
                <tr v-if="!rec.cases.length"><td colspan="5" class="muted">No cases recorded for this parcel.</td></tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <div class="stack sticky">
        <section class="box">
          <div class="box-head"><h2 class="box-title"><Icon name="map" :size="18" />Boundary</h2></div>
          <PreviewMap :shapes="shapes" :height="340"><span><i class="sw" :class="active ? 'sw-new' : 'sw-old'"></i>This parcel</span><span><i class="sw sw-parcel"></i>Neighbours</span></PreviewMap>
        </section>
        <section v-if="rec.open_issues.length" class="box">
          <div class="box-head"><h2 class="box-title"><Icon name="alert" :size="18" />Open issues</h2></div>
          <ul class="checklist">
            <li v-for="(i, n) in rec.open_issues" :key="n" :class="i.severity === 'error' ? 'err' : 'warn'"><Icon name="alert" :size="16" />
              <div><strong>{{ label(i.type) }}</strong><span>{{ i.detail || 'Found by validation' }}</span></div></li>
          </ul>
        </section>
        <section v-if="rec.parents.length || rec.children.length" class="box">
          <div class="box-head"><h2 class="box-title"><Icon name="split" :size="18" />Lineage</h2></div>
          <p v-if="rec.parents.length" class="note" style="margin-top: 0">Created by splitting
            <RouterLink v-for="p in rec.parents" :key="p.id" class="link" :to="`/officer/parcels/${p.id}`">kitta {{ p.kitta }} ({{ p.pin }})</RouterLink>.</p>
          <p v-if="rec.children.length" class="note" style="margin-top: 0">Split into
            <template v-for="(c, n) in rec.children" :key="c.id"><RouterLink class="link" :to="`/officer/parcels/${c.id}`">kitta {{ c.kitta }}</RouterLink>{{ n < rec.children.length - 1 ? ', ' : '.' }}</template></p>
        </section>
      </div>
    </div>
    <RokkaDialog v-if="placing" mode="place" :parcel-id="rec.id" @done="rokkaPlaced" @close="placing = false" />
  </main>
</template>
