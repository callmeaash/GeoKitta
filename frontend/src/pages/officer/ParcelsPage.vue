<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { request } from '../../api.js'
import Icon from '../../components/Icon.vue'
import { fmt, label } from '../../utils/format.js'

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
  if (!query) {
    hits.value = []
    state.value = 'idle'
    return
  }
  const mine = ++seq
  state.value = 'loading'
  try {
    const found = await request(`/api/parcels/search?q=${encodeURIComponent(query)}`)
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
</script>

<template>
  <main class="page">
    <div class="page-head">
      <div>
        <div class="crumbs"><RouterLink to="/officer">Dashboard</RouterLink><Icon name="chevronRight" :size="12" />Parcels</div>
        <h1 class="page-title">Parcels</h1>
        <p class="page-sub">Find a registered parcel to update its boundary, split it or correct its details.</p>
      </div>
      <div class="head-actions">
        <RouterLink class="btn btn-secondary" to="/"><Icon name="map" :size="16" />Pick on the map</RouterLink>
        <RouterLink class="btn btn-ghost" to="/officer/parcels/new"><Icon name="plus" :size="16" />Register new land</RouterLink>
      </div>
    </div>

    <section class="box">
      <div class="field" style="margin-bottom: 0">
        <label for="parcel-q">PIN, kitta number, or ward and kitta</label>
        <input id="parcel-q" v-model="q" type="search" placeholder="e.g. KTM-09-010-0100, 4/123 or ward 4 kitta 123" autocomplete="off">
        <span class="hint">On the map, an officer can also click any parcel and choose “Open parcel record”.</span>
      </div>
    </section>

    <section v-if="state !== 'idle'" class="box flush">
      <div class="box-head"><div><h2 class="box-title">
        {{ state === 'loading' ? 'Searching…' : state === 'error' ? 'Search failed' : `${hits.length} parcels` }}</h2>
        <p class="box-sub">Kitta numbers repeat across map sheets; the PIN is unique</p></div></div>
      <div class="tbl-wrap">
        <table class="tbl">
          <thead><tr><th>Kitta</th><th>Ward</th><th>PIN</th><th>Map sheet</th><th>Land use</th><th>Area</th><th></th></tr></thead>
          <tbody>
            <tr v-for="p in hits" :key="p.id" class="row-link" @click="router.push(`/officer/parcels/${p.id}`)">
              <td class="num"><RouterLink class="link" :to="`/officer/parcels/${p.id}`" @click.stop>{{ p.kitta }}</RouterLink></td>
              <td class="num">{{ p.ward }}</td>
              <td class="num">{{ p.pin }}</td>
              <td class="num">{{ p.map_sheet }}</td>
              <td>{{ label(p.land_use) }}</td>
              <td class="num">{{ fmt(p.area_m2) }} m²</td>
              <td><Icon name="chevronRight" :size="16" /></td>
            </tr>
            <tr v-if="state === 'done' && !hits.length"><td colspan="7" class="muted">No active parcel matches. Check the PIN or ward and kitta.</td></tr>
          </tbody>
        </table>
      </div>
    </section>
  </main>
</template>
