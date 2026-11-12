<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auth, initials, logout } from '../../auth.js'
import Icon from '../../components/Icon.vue'

const route = useRoute()
const router = useRouter()
const NAV = [
  { id: 'dashboard', label: 'Dashboard', icon: 'grid', to: '/officer' },
  { id: 'map', label: 'Map', icon: 'map', to: '/' },
  { id: 'owners', label: 'Owners', icon: 'users', to: '/officer/owners' },
  { id: 'new-owner', label: 'Register owner', icon: 'userPlus', to: '/officer/owners/new' }
]
const active = computed(() => route.meta.nav)
const role = computed(() => [auth.officer?.office, auth.officer?.is_admin ? 'Admin' : null].filter(Boolean).join(' · '))

async function signOut() {
  await logout()
  router.replace('/officer/login')
}
</script>

<template>
  <div class="o-app">
    <aside class="sidebar" aria-label="Officer navigation">
      <RouterLink class="sb-brand" to="/officer">
        <span class="brand-mark"><Icon name="pin" :size="18" /></span>
        <span><span class="brand-name">GeoKitta</span><span class="brand-sub">Officer workspace</span></span>
      </RouterLink>
      <nav class="sb-nav">
        <RouterLink v-for="n in NAV" :key="n.id" :to="n.to" :class="{ active: active === n.id }"
                    :aria-current="active === n.id ? 'page' : null">
          <Icon :name="n.icon" :size="18" /><span>{{ n.label }}</span>
        </RouterLink>
      </nav>
      <div v-if="auth.officer" class="sb-user">
        <span class="avatar">{{ initials(auth.officer.full_name) }}</span>
        <div><div class="u-name">{{ auth.officer.full_name }}</div><div class="u-role">{{ role }}</div></div>
        <button class="icon-btn" aria-label="Sign out" title="Sign out" @click="signOut"><Icon name="logout" :size="18" /></button>
      </div>
    </aside>
    <div class="o-main">
      <div class="strip"><Icon name="info" :size="14" />
        <span><strong>Demonstration system</strong> — all parcel and owner data is synthetic</span></div>
      <RouterView />
    </div>
  </div>
</template>
