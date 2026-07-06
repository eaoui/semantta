// plugins/title.client.ts
// Sets the browser tab title for admin pages using the route path.

import type { RouteLocationNormalized } from 'vue-router'
import { getAdminPageTitle } from '@/utils/pageTitle'
import { useAppStore } from '@/stores/app'

export default defineNuxtPlugin(() => {
  const router = useRouter()
  const store = useAppStore()

  router.afterEach((to: RouteLocationNormalized) => {
    if (to.path.startsWith('/admin')) {
      const pageName = getAdminPageTitle(to.path)
      document.title = `Semantta - ${pageName}`
    }
  })
})