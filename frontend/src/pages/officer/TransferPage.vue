<script setup>
import BsDateInput from '../../components/BsDateInput.vue'
import BsDate from '../../components/BsDate.vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { request } from '../../api.js'
import Icon from '../../components/Icon.vue'
import OwnerPicker from '../../components/officer/OwnerPicker.vue'
import RokkaDialog from '../../components/officer/RokkaDialog.vue'
import ValidationList from '../../components/officer/ValidationList.vue'
import { toRopani } from '../../utils/area.js'
import { bsText, fmt, label, shareLabel, todayAd, txnLabel } from '../../utils/format.js'
import { sumShares } from '../../utils/survey.js'

const route = useRoute()
const router = useRouter()
const id = Number(route.params.id)
const DEEDS = ['rajinama', 'hal_ko_bakaspatra', 'danpatra', 'ansha_banda', 'namasari', 'chhod_patra']
const today = todayAd()

const rec = ref(null)
const own = ref(null)
const error = ref('')
const owners = ref([])
const form = reactive({ deed_type: 'rajinama', deed_date: today, deed_ref: '', remarks: '' })
const saving = ref(false)
const errors = ref([])
const releasing = ref(null)

async function load() {
  try {
    ;[rec.value, own.value] = await Promise.all([request(`/api/officer/parcels/${id}`),
      request(`/api/officer/parcels/${id}/ownership`)])
  } catch (e) {
    error.value = e.message
  }
}
onMounted(load)

const lastDate = computed(() => own.value?.current.map(o => o.valid_from).sort().at(-1) || null)
const total = computed(() => sumShares(owners.value.map(o => o.share)))
const sameAsNow = computed(() => {
  if (!own.value || !owners.value.length) return false
  const now = own.value.current.map(o => `${o.owner_id}:${o.share}`).sort().join()
  return owners.value.map(o => `${o.id}:${o.share.trim()}`).sort().join() === now
})
const checks = computed(() => {
  if (!own.value) return []
  const rokka = own.value.rokka
  const sharesOk = owners.value.length && total.value && total.value[0] === total.value[1]
  return [
    rokka.length
      ? { id: 'rokka', status: 'fail', title: 'Active rokka', detail: `${rokka[0].requested_by_name} since ${bsText(rokka[0].start_date)}. Release it (fukuwa) first.` }
      : { id: 'rokka', status: 'pass', title: 'No active rokka on this parcel', detail: 'Transfers are allowed.' },
    sharesOk
      ? { id: 'shares', status: sameAsNow.value ? 'fail' : 'pass', title: sameAsNow.value ? 'Nothing changes' : 'New shares add up to 1', detail: sameAsNow.value ? 'The new owners and shares are the same as now.' : `${owners.value.length} owner(s).` }
      : { id: 'shares', status: 'fail', title: 'Shares must add up to exactly 1', detail: owners.value.length ? 'For example 1/2 + 1/2.' : 'Add the new owners.' },
    form.deed_date && lastDate.value && form.deed_date < lastDate.value
      ? { id: 'date', status: 'fail', title: 'Deed date is too early', detail: `The current owners hold the parcel since ${bsText(lastDate.value)}.` }
      : { id: 'date', status: form.deed_date && form.deed_date <= today ? 'pass' : 'fail', title: 'Deed date', detail: form.deed_date ? `${bsText(form.deed_date)} (${form.deed_date} AD)` : 'Enter a valid deed date.' }
  ]
})
const ok = computed(() => checks.value.length && checks.value.every(c => c.status === 'pass'))

async function save() {
  errors.value = []
  saving.value = true
  try {
    const r = await request(`/api/officer/parcels/${id}/transfer`, {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...form, deed_ref: form.deed_ref || null, remarks: form.remarks || null,
        owners: owners.value.map(o => ({ owner_id: o.id, share: o.share.trim() })) })
    })
    router.push({ path: `/officer/parcels/${id}`, query: { saved: `${txnLabel(form.deed_type)} recorded, case ${r.case_id}.` } })
  } catch (e) {
    errors.value = [e.message]
  } finally {
    saving.value = false
  }
}

async function released() {
  releasing.value = null
  await load()
}
</script>

<template>
  <main class="page">
    <div class="page-head">
      <div>
        <div class="crumbs"><RouterLink to="/officer">Dashboard</RouterLink><Icon name="chevronRight" :size="12" />
          <RouterLink to="/officer/parcels">Update parcel</RouterLink><Icon name="chevronRight" :size="12" />
          <RouterLink :to="`/officer/parcels/${id}`">Kitta {{ rec?.kitta || '…' }}</RouterLink><Icon name="chevronRight" :size="12" />Transfer ownership</div>
        <h1 class="page-title">Transfer ownership{{ rec ? ` — Kitta ${rec.kitta}` : '' }}</h1>
        <p v-if="rec" class="page-sub">Ward {{ rec.ward }} · PIN {{ rec.pin }} · {{ fmt(rec.area_m2) }} m² ({{ toRopani(rec.area_m2) }} ropani)</p>
      </div>
      <div class="head-actions"><RouterLink class="btn btn-secondary" :to="`/officer/parcels/${id}/history`"><Icon name="clock" :size="16" />History</RouterLink></div>
    </div>
    <div v-if="error" class="banner banner-error"><Icon name="alert" :size="16" /><span>{{ error }}</span></div>
    <div v-if="rec && rec.status !== 'active'" class="banner banner-info"><Icon name="info" :size="16" /><span>This parcel is retired and cannot be transferred.</span></div>

    <div v-for="r in own?.rokka || []" :key="r.id" class="banner banner-error" role="alert">
      <Icon name="lock" :size="18" />
      <div><strong>Transfer blocked — active rokka</strong>
        <span>Requested by {{ r.requested_by_name }} ({{ label(r.requested_by_type) }}) on {{ bsText(r.start_date) }}{{ r.reason ? ` as ${r.reason}` : '' }}.
          Release the rokka (fukuwa) before transferring.</span></div>
      <button class="btn btn-secondary btn-sm" style="margin-left: auto" @click="releasing = r">Release (fukuwa)</button>
    </div>
    <div v-if="errors.length" class="banner banner-error"><Icon name="alert" :size="16" /><span>{{ errors.join(' ') }}</span></div>

    <div v-if="rec && own" class="grid-2">
      <div class="stack">
        <section class="box flush">
          <div class="box-head"><h2 class="box-title"><Icon name="users" :size="18" />Current owners</h2></div>
          <div class="tbl-wrap"><table class="tbl">
            <thead><tr><th>Owner</th><th>LIN</th><th>Share</th><th>Since</th><th>By</th></tr></thead>
            <tbody>
              <tr v-for="o in own.current" :key="o.owner_id">
                <td><RouterLink class="link" :to="`/officer/owners/${o.owner_id}`">{{ o.full_name }}</RouterLink></td>
                <td class="num">{{ o.lin }}</td><td class="num">{{ shareLabel(o.share) }}</td>
                <td><BsDate :date="o.valid_from" /></td><td>{{ o.txn_type ? txnLabel(o.txn_type) : '—' }}</td>
              </tr>
            </tbody>
          </table></div>
        </section>

        <section class="box">
          <div class="box-head"><h2 class="box-title"><Icon name="file" :size="18" />Deed</h2></div>
          <div class="form-grid">
            <div class="field span-2"><label for="deed">Deed type</label>
              <select id="deed" v-model="form.deed_type"><option v-for="d in DEEDS" :key="d" :value="d">{{ txnLabel(d) }}</option></select></div>
            <div class="field"><label for="ddate">Deed date</label><BsDateInput id="ddate" v-model="form.deed_date" :max="today" :min="lastDate || '1950-01-01'" /></div>
            <div class="field"><label for="dref">Deed reference no.</label><input id="dref" v-model="form.deed_ref" placeholder="e.g. RJ-2026-00123"></div>
            <div class="field span-2"><label for="rem">Remarks</label><input id="rem" v-model="form.remarks"></div>
          </div>
        </section>

        <section class="box">
          <div class="box-head"><div><h2 class="box-title"><Icon name="userPlus" :size="18" />New owners</h2>
            <p class="box-sub">The complete list after the deed. Shares must add up to exactly 1 (e.g. 1/2 + 1/2).</p></div></div>
          <OwnerPicker v-model="owners" />
        </section>
      </div>

      <div class="stack sticky">
        <section class="box">
          <div class="box-head"><h2 class="box-title"><Icon name="checkCircle" :size="18" />Checks</h2></div>
          <ValidationList :checks="checks" />
        </section>
        <section class="box">
          <div class="box-head"><h2 class="box-title"><Icon name="parcel" :size="18" />Parcel</h2>
            <RouterLink class="link" :to="{ path: '/', hash: `#parcel=${id}` }">Open map</RouterLink></div>
          <dl class="kv wide" style="margin: 0">
            <dt>Land use</dt><dd>{{ label(rec.land_use) }}</dd>
            <dt>Parcel type</dt><dd>{{ label(rec.parcel_type) }}</dd>
            <dt>Last change</dt><dd><BsDate :date="lastDate" /></dd>
          </dl>
        </section>
      </div>
    </div>

    <div v-if="rec && own" class="footer-bar">
      <span class="left"><Icon name="info" :size="16" />The current owners' periods end on the deed date and the new owners' periods start.</span>
      <RouterLink class="btn btn-ghost" :to="`/officer/parcels/${id}`">Cancel</RouterLink>
      <button class="btn btn-primary" :disabled="!ok || saving || rec.status !== 'active'" @click="save">
        <Icon name="transfer" :size="16" />{{ saving ? 'Saving…' : 'Record transfer' }}</button>
    </div>
    <RokkaDialog v-if="releasing" mode="release" :rokka="releasing" :parcel-id="id" @done="released" @close="releasing = null" />
  </main>
</template>
