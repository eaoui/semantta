<template>
  <NuxtLayout>
    <NuxtPage />
  </NuxtLayout>

  <LoadingOverlay
    :show="isStartupLoading"
    title="Loading"
    message="Loading data…"
  />
</template>

<script setup lang="ts">
import { useAppStore } from '@/stores/app'
import LoadingOverlay from '@/components/shared/LoadingOverlay.vue'

const store = useAppStore()
const isStartupLoading = ref(true)

onMounted(async () => {
  try {
    await store.fetchState()
  } finally {
    isStartupLoading.value = false
  }
})
</script>