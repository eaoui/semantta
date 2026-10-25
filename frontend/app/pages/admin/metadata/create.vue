<template>
  <div>
    <div v-if="!store.isReady" class="text-gray-500 dark:text-gray-400">Loading…</div>
    <AdminMetadataForm v-else mode="create" :submitting="!!loadingMsg" :serverValidationError="serverValidationError"
      @submit="createInstance" />

    <LoadingOverlay :show="!!loadingMsg" title="Loading" :message="loadingMsg" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useAppStore } from '@/stores/app'
import LoadingOverlay from '@/components/shared/LoadingOverlay.vue'
import { useToast } from '@/composables/useToast'

const store = useAppStore()
const apiBase = useRuntimeConfig().public.apiBase
const loadingMsg = ref('')
const toast = useToast()

const serverValidationError = ref<string | null>(null)

async function createInstance(payload: {
  classUris: string[]
  instanceUri: string
  properties: Record<string, string[]>
}) {
  if (loadingMsg.value) return

  loadingMsg.value = 'Validating and saving the data...'
  serverValidationError.value = null

  try {
    await $fetch(`${apiBase}/api/metadata/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        class_uris: payload.classUris,
        instance_uri: payload.instanceUri,
        properties: payload.properties,
      }),
    })

    toast.success('Instance created')
    await store.fetchState()
    await navigateTo('/admin/metadata/instances')
  } catch (error: any) {
    const message =
      typeof error?.data?.detail === 'string'
        ? error.data.detail
        : typeof error?.message === 'string'
          ? error.message
          : 'Failed to create instance.'

    serverValidationError.value = message
    toast.error(message)
  } finally {
    loadingMsg.value = ''
  }
}
</script>