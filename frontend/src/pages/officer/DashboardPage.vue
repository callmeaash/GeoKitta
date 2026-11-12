<script setup>
import { computed, onMounted, ref } from 'vue'
import { request } from '../../api.js'
import { auth } from '../../auth.js'
import Icon from '../../components/Icon.vue'
import { label, statusClass, txnLabel } from '../../utils/format.js'

const data = ref(null)
const error = ref('')
const nf = new Intl.NumberFormat('en-US')
const today = new Date().toISOString().slice(0, 10)
const firstName = computed(() => auth.officer?.full_name.split(' ')[0] || '')

const ACTIONS = {
  login: 'Signed in', owner_registered: 'Registered owner', pipeline_import: 'Imported demo data',
  parcel_registered: 'Registered parcel', boundary_updated: 'Updated boundary', parcel_split: 'Split parcel'
}
const actionText = a => {
  const base = ACTIONS[a.action] || label(a.action)
  if (a.details?.name) return `${base}: ${a.details.name}${a.details.lin ? ` (${a.details.lin})` : ''}`
  return a.details?.pin ? `${base} ${a.details.pin}${a.details.case_id ? ` · case ${a.details.case_id}` : ''}` : base
}
const when = iso => new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })

onMounted(async () => {
  try {
    data.value = await request('/api/officer/dashboard')
  } catch (e) {
    error.value = e.message
  }
})
</script>

<template>
  <main class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">Namaste, {{ firstName }}</h1>
        <p class="page-sub"><Icon name="calendar" :size="15" />{{ today }} · {{ auth.officer?.office || 'Officer' }}
          · Kathmandu Metropolitan City</p>
      </div>
      <div class="head-actions">
        <RouterLink class="btn btn-secondary" to="/"><Icon name="map" :size="16" />Open map</RouterLink>
        <RouterLink class="btn btn-primary" to="/officer/parcels/new"><Icon name="plus" :size="16" />Register parcel</RouterLink>
      </div>
    </div>

    <div v-if="error" class="banner banner-error"><Icon name="alert" :size="16" /><span>{{ error }}</span></div>

    <div class="stats">
      <div class="stat"><div class="lbl"><Icon name="parcel" :size="16" />Active parcels</div>
        <div class="val">{{ data ? nf.format(data.active_parcels) : '—' }}</div><div class="meta">All 32 wards</div></div>
      <div class="stat"><div class="lbl"><Icon name="users" :size="16" />Registered owners</div>
        <div class="val">{{ data ? nf.format(data.owners) : '—' }}</div><div class="meta">People, organisations and offices</div></div>
      <div class="stat warn"><div class="lbl"><Icon name="lock" :size="16" />Active rokka</div>
        <div class="val">{{ data ? nf.format(data.active_rokka) : '—' }}</div><div class="meta">Transfers blocked until released</div></div>
      <div class="stat"><div class="lbl"><Icon name="transfer" :size="16" />Deeds, last 30 days</div>
        <div class="val">{{ data ? nf.format(data.transactions_30_days) : '—' }}</div><div class="meta">By deed date</div></div>
    </div>

    <div class="quick">
      <RouterLink to="/officer/parcels/new"><span class="qi"><Icon name="plus" /></span><span>Register parcel<small>From survey coordinates</small></span></RouterLink>
      <RouterLink to="/officer/owners/new"><span class="qi"><Icon name="userPlus" /></span><span>Register owner<small>With duplicate check</small></span></RouterLink>
      <RouterLink to="/"><span class="qi"><Icon name="split" /></span><span>Update or split<small>Pick the parcel on the map</small></span></RouterLink>
      <RouterLink to="/?tab=buffer"><span class="qi"><Icon name="buffer" /></span><span>Setback search<small>Roads and rivers</small></span></RouterLink>
    </div>

    <div class="grid-2-wide">
      <section class="box flush">
        <div class="box-head"><div><h2 class="box-title">Recent transactions</h2>
          <p class="box-sub">Latest deeds and cases by deed date</p></div></div>
        <div class="tbl-wrap">
          <table class="tbl">
            <thead><tr><th>Case ID</th><th>Type</th><th>Kitta</th><th>Deed date</th><th>Officer</th><th>Status</th></tr></thead>
            <tbody>
              <tr v-for="t in data?.recent_transactions || []" :key="t.case_id">
                <td class="num">{{ t.case_id }}</td>
                <td>{{ txnLabel(t.txn_type) }}</td>
                <td class="num">
                  <RouterLink v-if="t.parcel_id" class="link" :to="{ path: '/', hash: `#parcel=${t.parcel_id}` }">
                    {{ t.kitta }} · W{{ t.ward }}</RouterLink>
                  <span v-else class="muted">—</span>
                </td>
                <td class="num">{{ t.deed_date || '—' }}</td>
                <td>{{ t.officer }}</td>
                <td><span class="status" :class="statusClass(t.status)">{{ label(t.status) }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="box">
        <div class="box-head"><div><h2 class="box-title">Recent activity</h2><p class="box-sub">From the audit log</p></div>
          <span class="status" :class="data?.open_issues ? 'st-amber' : 'st-green'">{{ data?.open_issues ?? '—' }} open issues</span>
        </div>
        <ul class="checklist">
          <li v-for="(a, i) in data?.recent_activity || []" :key="i">
            <Icon name="clock" :size="16" />
            <div><strong>{{ actionText(a) }}</strong><span>{{ a.officer }} · {{ when(a.created_at) }}</span></div>
          </li>
          <li v-if="data && !data.recent_activity.length"><div><span>No activity yet.</span></div></li>
        </ul>
      </section>
    </div>
  </main>
</template>
