/**
 * Provides the site title from the backend settings,
 * with SSR‑safe initial value to avoid flicker.
 */
export const useSiteTitle = () => {
  const config = useRuntimeConfig()
  const apiBase = config.public.apiBase

  const { data } = useAsyncData('site-settings', () =>
    $fetch<{ site_title: string }>(`${apiBase}/api/settings`)
  )

  const title = computed(() => data.value?.site_title || 'Semantta')

  return { title }
}