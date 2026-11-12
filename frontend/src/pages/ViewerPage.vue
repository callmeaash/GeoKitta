<script setup>
import { onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { auth, loadOfficer } from '../auth.js'
import { setTab, store } from '../store.js'
import Icon from '../components/Icon.vue'
import MapView from '../components/MapView.vue'
import SearchBox from '../components/SearchBox.vue'
import ToolRail from '../components/ToolRail.vue'
import BufferPanel from '../components/panels/BufferPanel.vue'
import DetailsPanel from '../components/panels/DetailsPanel.vue'
import LayersPanel from '../components/panels/LayersPanel.vue'
import MeasurePanel from '../components/panels/MeasurePanel.vue'
import SelectPanel from '../components/panels/SelectPanel.vue'

const PANELS = { details: DetailsPanel, select: SelectPanel, buffer: BufferPanel, measure: MeasurePanel,
  layers: LayersPanel }

const route = useRoute()
onMounted(() => {
  loadOfficer()
  if (PANELS[route.query.tab]) setTab(route.query.tab) // e.g. /?tab=buffer from the dashboard
})
</script>

<template>
  <div class="app">
    <header class="topbar">
      <a class="brand" href="/">
        <span class="brand-mark"><Icon name="pin" :size="20" /></span>
        <span><span class="brand-name">GeoKitta</span><span class="brand-sub">Cadastral Information System</span></span>
      </a>
      <SearchBox />
      <div class="top-actions">
        <RouterLink v-if="auth.officer" class="btn btn-secondary" to="/officer">
          <Icon name="grid" :size="16" /><span class="label-text">Officer workspace</span>
        </RouterLink>
        <RouterLink v-else class="btn btn-primary" to="/officer/login">
          <Icon name="user" :size="16" /><span class="label-text">Officer login</span>
        </RouterLink>
      </div>
    </header>

    <div class="strip">
      <Icon name="info" :size="14" />
      <span><strong>Demonstration system</strong> — all parcel and owner data is synthetic</span>
    </div>

    <div class="main">
      <ToolRail />
      <aside class="panel" :class="{ open: store.sheetOpen }" aria-live="polite">
        <button class="sheet-close" aria-label="Hide panel" @click="store.sheetOpen = false">
          <span class="handle"></span>
        </button>
        <component :is="PANELS[store.tab]" />
      </aside>
      <MapView />
    </div>
  </div>
</template>
