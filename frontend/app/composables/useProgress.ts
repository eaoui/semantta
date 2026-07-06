/**
 * Polls the backend /api/progress endpoint every 500ms
 * to display live operation phases (e.g. during imports).
 */
export function useProgress() {
  const apiBase = useRuntimeConfig().public.apiBase
  const phase = ref('')

  let timer: ReturnType<typeof setInterval> | null = null

  function startPolling() {
    stopPolling()
    timer = setInterval(async () => {
      try {
        const res = await $fetch<{ phase: string }>(`${apiBase}/api/progress`)
        phase.value = res.phase
      } catch (e) {
        // ignore polling errors
      }
    }, 500)
  }

  function stopPolling() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
    phase.value = ''
  }

  onUnmounted(stopPolling)

  return { phase, startPolling, stopPolling }
}