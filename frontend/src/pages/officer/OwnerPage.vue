<script setup>
import BsDate from '../../components/BsDate.vue'
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { request } from '../../api.js'
import Icon from '../../components/Icon.vue'
import { districtName, fmt, label, shareLabel, txnLabel } from '../../utils/format.js'

const route = useRoute()
const owner = ref(null)
const error = ref('')

watch(() => route.params.id, async id => {
  owner.value = null
  error.value = ''
  try {
    owner.value = await request(`/api/officer/owners/${id}`)
  } catch (e) {
    error.value = e.status === 404 ? 'No owner with this ID.' : e.message
  }
}, { immediate: true })
</script>

<template>
  <main class="page">
    <div class="page-head">
      <div>
        <div class="crumbs"><RouterLink to="/officer">Dashboard</RouterLink><Icon name="chevronRight" :size="12" />
          <RouterLink to="/officer/owners">Owners</RouterLink><Icon name="chevronRight" :size="12" />{{ owner?.lin || '…' }}</div>
        <h1 class="page-title">{{ owner?.full_name || (error ? 'Owner' : 'Loading…') }}</h1>
        <p v-if="owner" class="page-sub">{{ label(owner.owner_type) }} · LIN {{ owner.lin }}
          <template v-if="owner.full_name_ne"> · {{ owner.full_name_ne }}</template></p>
      </div>
    </div>
    <div v-if="owner && route.query.created" class="banner banner-success" role="status"><Icon name="checkCircle" :size="16" />
      <span>Owner saved with LIN <strong style="display: inline">{{ owner.lin }}</strong>.</span></div>
    <div v-if="error" class="banner banner-error"><Icon name="alert" :size="16" /><span>{{ error }}</span></div>

    <div v-if="owner" class="grid-side">
      <section class="box">
        <div class="box-head"><h2 class="box-title"><Icon name="user" :size="18" />Owner</h2></div>
        <dl class="kv wide">
          <dt>LIN</dt><dd>{{ owner.lin }}</dd>
          <dt>Type</dt><dd>{{ label(owner.owner_type) }}</dd>
          <template v-if="owner.owner_type === 'individual'">
            <dt>Gender</dt><dd>{{ label(owner.gender) }}</dd>
            <dt>Date of birth</dt><dd><BsDate :date="owner.date_of_birth" show-ad /></dd>
          </template>
          <dt>Citizenship No.</dt><dd>{{ owner.citizenship_no || '—' }}</dd>
          <dt>District</dt><dd>{{ districtName(owner.district_code) }}</dd>
          <dt>Address</dt><dd>{{ owner.address || '—' }}</dd>
          <dt>Phone</dt><dd>{{ owner.phone || '—' }}</dd>
        </dl>
      </section>

      <div class="stack">
        <section class="box flush">
          <div class="box-head"><div><h2 class="box-title">Current parcels</h2>
            <p class="box-sub">{{ owner.current.length }} held now</p></div></div>
          <div class="tbl-wrap">
            <table class="tbl">
              <thead><tr><th>Kitta</th><th>PIN</th><th>Land use</th><th>Area</th><th>Share</th><th>Since</th><th>Deed</th><th></th></tr></thead>
              <tbody>
                <tr v-for="h in owner.current" :key="h.parcel.id + h.valid_from">
                  <td class="num">{{ h.parcel.kitta }} · W{{ h.parcel.ward }}</td>
                  <td class="num">{{ h.parcel.pin }}</td>
                  <td>{{ label(h.parcel.land_use) }}</td>
                  <td class="num">{{ fmt(h.parcel.area_m2) }} m²</td>
                  <td class="num">{{ shareLabel(h.share) }}</td>
                  <td><BsDate :date="h.valid_from" /></td>
                  <td>{{ h.txn_type ? txnLabel(h.txn_type) : '—' }}</td>
                  <td><RouterLink class="link" :to="{ path: '/', hash: `#parcel=${h.parcel.id}` }">Map</RouterLink></td>
                </tr>
                <tr v-if="!owner.current.length"><td colspan="8" class="muted">No parcels held now.</td></tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="owner.past.length" class="box flush">
          <div class="box-head"><div><h2 class="box-title">Past parcels</h2>
            <p class="box-sub">Sold, given, partitioned or split</p></div></div>
          <div class="tbl-wrap">
            <table class="tbl">
              <thead><tr><th>Kitta</th><th>PIN</th><th>Share</th><th>From</th><th>To</th><th>Acquired by</th></tr></thead>
              <tbody>
                <tr v-for="h in owner.past" :key="h.parcel.id + h.valid_from">
                  <td class="num">{{ h.parcel.kitta }} · W{{ h.parcel.ward }}</td>
                  <td class="num">{{ h.parcel.pin }}</td>
                  <td class="num">{{ shareLabel(h.share) }}</td>
                  <td><BsDate :date="h.valid_from" /></td>
                  <td><BsDate :date="h.valid_to" /></td>
                  <td>{{ h.txn_type ? txnLabel(h.txn_type) : '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  </main>
</template>
