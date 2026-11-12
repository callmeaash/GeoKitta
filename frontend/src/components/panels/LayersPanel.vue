<script setup>
import { store } from '../../store.js'
</script>

<template>
  <div class="panel-head"><span class="eyebrow">Layers</span></div>
  <div class="panel-body">
    <div class="section-title">Base map</div>
    <label class="check"><input v-model="store.layers.base" type="radio" value="light">Light (muted OpenStreetMap)</label>
    <label class="check"><input v-model="store.layers.base" type="radio" value="osm">OpenStreetMap standard</label>

    <div class="section-title">Overlays</div>
    <label class="check"><input v-model="store.layers.parcels" type="checkbox">Parcel outlines</label>
    <label class="check"><input v-model="store.layers.labels" type="checkbox">Kitta numbers (zoom 19+)</label>
    <label class="check"><input v-model="store.layers.zones" type="checkbox">Setback and buffer zones</label>

    <p class="note">
      Base map © OpenStreetMap contributors. Parcels, owners and records are synthetic.
    </p>
  </div>
</template>
