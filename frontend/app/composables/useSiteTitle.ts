import { computed } from 'vue'
import { useAppStore } from '@/stores/app'

export const useSiteTitle = () => {
  const store = useAppStore()

  // Display name used in the public site's interface.
  const title = computed(
    () => store.siteTitle?.trim() || 'Semantta',
  )

  // Browser title must not use the fallback brand name.
  const browserTitle = computed(() => {
    if (!store.isReady) return 'Loading...'

    const configuredTitle = store.siteTitle?.trim()

    return configuredTitle && configuredTitle !== 'Semantta'
      ? configuredTitle
      : 'Loading...'
  })

  return { title, browserTitle }
}