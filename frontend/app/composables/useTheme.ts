// composables/useTheme.ts – a shared composable for theme management
export const useTheme = () => {
  const themeMode = ref<'light' | 'dark' | 'system'>('system')

  const apply = () => {
    const root = document.documentElement
    const isDark = themeMode.value === 'dark' ||
      (themeMode.value === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
    root.classList.toggle('dark', isDark)
    localStorage.setItem('theme', themeMode.value)
  }

  // Listen to system changes when in system mode
  if (process.client) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
      if (themeMode.value === 'system') apply()
    })
  }

  // Load from localStorage on client
  if (process.client) {
    const saved = localStorage.getItem('theme')
    if (saved === 'light' || saved === 'dark' || saved === 'system') {
      themeMode.value = saved
    }
    apply()
  }

  return { themeMode, apply }
}