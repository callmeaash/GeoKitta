<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { request } from '../../api.js'
import Icon from '../../components/Icon.vue'
import { districtName, label } from '../../utils/format.js'

const route = useRoute()
const router = useRouter()
const q = ref(typeof route.query.q === 'string' ? route.query.q : '')
const hits = ref([])
const state = ref('idle')
let timer
let seq = 0

async function run() {
  const query = q.value.trim()
  router.replace({ query: query ? { q: query } : {} })
  if (query.length < 2) {
    hits.value = []
    state.value = 'idle'
    return
  }
  const mine = ++seq
  state.value = 'loading'
  try {
    const found = await request(`/api/officer/owners?q=${encodeURIComponent(query)}`)
    if (mine === seq) {
      hits.value = found
      state.value = 'done'
    }
  } catch {
    if (mine === seq) state.value = 'error'
  }
}

watch(q, () => {
  clearTimeout(timer)
  timer = setTimeout(run, 250)
}, { immediate: true })

const match = h => (h.distance === 0 ? 'exact' : h.edits === 0 ? 'other spelling' : h.edits < 1 ? 'starts with'
  : `${Math.round(h.edits)} edit${h.edits >= 2 ? 's' : ''}`)
</script>

<template>
  <main class="page">
    <div class="page-head">
      <div>
        <div class="crumbs"><RouterLink to="/officer">Dashboard</RouterLink><Icon name="chevronRight" :size="12" />Owners</div>
        <h1 class="page-title">Owners</h1>
        <p class="page-sub">Search by name or LIN. Spelling variants are found too (Shreshtha, Lakshmi, Vishnu).</p>
      </div>
      <div class="head-actions">
        <RouterLink class="btn btn-primary" to="/officer/owners/new"><Icon name="userPlus" :size="16" />Register owner</RouterLink>
      </div>
    </div>

    <section class="box">
      <div class="field" style="margin-bottom: 0">
        <label for="owner-q">Name or LIN</label>
        <input id="owner-q" v-model="q" type="search" placeholder="e.g. Ram Bahadur Shreshtha or 27-000123-M"
               autocomplete="off">
      </div>
    </section>

    <section v-if="state !== 'idle'" class="box flush">
      <div class="box-head"><div><h2 class="box-title">
        {{ state === 'loading' ? 'Searching…' : state === 'error' ? 'Search failed' : `${hits.length} owners` }}</h2>
        <p class="box-sub">Closest names first; namesakes are told apart by LIN and date of birth</p></div></div>
      <div class="tbl-wrap">
        <table class="tbl">
          <thead><tr><th>Name</th><th>LIN</th><th>Type</th><th>Date of birth</th><th>District</th><th>Parcels</th><th>Match</th></tr></thead>
          <tbody>
            <tr v-for="h in hits" :key="h.id" class="row-link" @click="router.push(`/officer/owners/${h.id}`)">
              <td><RouterLink class="link" :to="`/officer/owners/${h.id}`" @click.stop>{{ h.full_name }}</RouterLink></td>
              <td class="num">{{ h.lin }}</td>
              <td>{{ label(h.owner_type) }}</td>
              <td class="num">{{ h.date_of_birth || '—' }}</td>
              <td>{{ districtName(h.district_code) }}</td>
              <td class="num">{{ h.parcels }}</td>
              <td><span class="tag" :class="{ 'tag-teal': h.distance === 0 }">{{ match(h) }}</span></td>
            </tr>
            <tr v-if="state === 'done' && !hits.length"><td colspan="7" class="muted">No owners match. Check the spelling or try the LIN.</td></tr>
          </tbody>
        </table>
      </div>
    </section>
  </main>
</template>
