<script setup>
import { selectParcel, setTab, startDraw, store } from '../../store.js'
import { fmt, label, measuredFrom, sourceLabel } from '../../utils/format.js'
import { toRopani } from '../../utils/area.js'
import { auth } from '../../auth.js'
import Icon from '../Icon.vue'
import OwnershipCard from '../OwnershipCard.vue'
import StatsNote from '../StatsNote.vue'

function nearby() {
  const d = store.details
  setTab('buffer')
  store.drawResult = { purpose: 'buffer', kind: 'point', latlngs: [[d.centre[1], d.centre[0]]], nearby: true }
}

const setbackText = s => `${fmt(s.distance_m)} m from the ${measuredFrom(s.measured_from)}; the ${s.source} rule ` +
  `keeps ${fmt(s.rule_distance_m)} m from the ${measuredFrom(s.measured_from)}`
</script>

<template>
  <div v-if="store.detailsLoading && !store.details" class="empty">
    <div class="empty-art"><Icon name="pin" :size="32" /></div>
    <h3>Loading parcel…</h3>
  </div>

  <div v-else-if="store.details" class="details">
    <div class="panel-head">
      <span class="eyebrow">Parcel details</span>
      <button class="icon-btn" aria-label="Close details" @click="selectParcel(null)"><Icon name="x" /></button>
    </div>
    <div class="panel-body">
      <button v-if="store.results" class="link back" @click="setTab(store.results.tab)">
        <Icon name="arrowLeft" :size="14" /> Back to {{ store.results.list.count }} results
      </button>
      <h2 class="title">Kitta No. {{ store.details.kitta }}</h2>
      <p class="subtitle">Ward {{ store.details.ward }} · {{ store.details.municipality }}</p>
      <dl class="kv">
        <dt>PIN</dt><dd>{{ store.details.pin }}</dd>
        <dt>Map sheet</dt><dd>{{ store.details.map_sheet }}</dd>
        <dt>Parcel type</dt><dd>{{ label(store.details.parcel_type) }}</dd>
        <dt>Land use</dt><dd>{{ label(store.details.land_use) }}</dd>
        <dt>Area</dt>
        <dd>{{ fmt(store.details.area_m2) }} m²
          <span class="sub">{{ toRopani(store.details.area_m2) }} ropani-aana-paisa-daam</span></dd>
        <dt>Boundary</dt>
        <dd>{{ fmt(store.details.boundary_area_m2) }} m²
          <span class="sub">Area enclosed by the surveyed boundary</span></dd>
        <dt>Geometry</dt>
        <dd>{{ sourceLabel(store.details.geometry_source) }}
          <span v-if="store.details.accuracy_m" class="sub">Accuracy ±{{ store.details.accuracy_m }} m</span></dd>
      </dl>
      <div class="divider"></div>

      <div v-for="s in store.details.setbacks" :key="s.feature_id + s.feature_type" class="card card-warning">
        <Icon name="alert" :size="16" />
        <div>
          <strong>Within {{ label(s.feature_type).toLowerCase() }} setback{{ s.name ? ` of ${s.name}` : '' }}</strong>
          <span><i class="swatch-inline"></i>{{ setbackText(s) }}</span>
        </div>
      </div>
      <div v-if="!store.details.setbacks.length" class="card card-success">
        <Icon name="checkCircle" :size="16" />
        <div><strong>Outside road and river setbacks</strong><span>Checked against the current setback rules.</span></div>
      </div>
      <OwnershipCard v-if="auth.officer" :parcel-id="store.details.id" />
      <div v-else class="card card-neutral">
        <Icon name="lock" :size="16" />
        <div><strong>Owner information is restricted</strong><span>Available to authorised officers only.</span></div>
      </div>

      <div class="actions">
        <button class="btn btn-primary" @click="store.flyTo = { geometry: store.details.geometry }">
          <Icon name="zoom" :size="16" /> Zoom to parcel
        </button>
        <div class="row">
          <button class="btn btn-secondary" @click="setTab('measure'); startDraw('line', 'measure')">
            <Icon name="ruler" :size="16" /> Measure
          </button>
          <button class="btn btn-secondary" @click="nearby"><Icon name="buffer" :size="16" /> Nearby</button>
        </div>
        <div v-if="auth.officer" class="row">
          <RouterLink class="btn btn-secondary" :to="`/officer/parcels/${store.details.id}/boundary`">
            <Icon name="edit" :size="16" /> Update boundary</RouterLink>
          <RouterLink class="btn btn-secondary" :to="`/officer/parcels/${store.details.id}/split`">
            <Icon name="split" :size="16" /> Split</RouterLink>
        </div>
      </div>
      <StatsNote :stats="store.identifyStats" />
    </div>
  </div>

  <div v-else class="empty">
    <div class="empty-art"><Icon name="pin" :size="32" /></div>
    <h3>No parcel selected</h3>
    <p v-if="store.detailsError">{{ store.detailsError }}</p>
    <p v-else>Click a parcel on the map, or search for a PIN or kitta number.</p>
  </div>
</template>
