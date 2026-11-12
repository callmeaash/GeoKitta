import { createRouter, createWebHistory } from 'vue-router'
import { loadOfficer } from './auth.js'
import ViewerPage from './pages/ViewerPage.vue'

const routes = [
  { path: '/', component: ViewerPage },
  { path: '/officer/login', component: () => import('./pages/LoginPage.vue') },
  {
    path: '/officer',
    component: () => import('./pages/officer/OfficerLayout.vue'),
    meta: { officer: true },
    children: [
      { path: '', component: () => import('./pages/officer/DashboardPage.vue'), meta: { nav: 'dashboard' } },
      { path: 'owners', component: () => import('./pages/officer/OwnersPage.vue'), meta: { nav: 'owners' } },
      { path: 'owners/new', component: () => import('./pages/officer/RegisterOwnerPage.vue'), meta: { nav: 'new-owner' } },
      { path: 'owners/:id(\\d+)', component: () => import('./pages/officer/OwnerPage.vue'), meta: { nav: 'owners' } },
      { path: 'parcels/new', component: () => import('./pages/officer/RegisterParcelPage.vue'), meta: { nav: 'new-parcel' } },
      { path: 'parcels/:id(\\d+)/boundary', component: () => import('./pages/officer/UpdateBoundaryPage.vue'), meta: { nav: 'map' } },
      { path: 'parcels/:id(\\d+)/split', component: () => import('./pages/officer/SplitParcelPage.vue'), meta: { nav: 'map' } }
    ]
  },
  { path: '/:rest(.*)*', redirect: '/' }
]

export const router = createRouter({ history: createWebHistory(), routes })

// Officer pages need a signed-in officer; the API enforces the same rule on every request.
router.beforeEach(async to => {
  if (!to.matched.some(r => r.meta.officer)) return true
  if (await loadOfficer()) return true
  return { path: '/officer/login', query: { next: to.fullPath } }
})
