<template>
  <div v-if="loading" class="text-gray-500 dark:text-gray-400">Loading instance…</div>
  <div v-else-if="error" class="text-red-600 dark:text-red-400">
    {{ error }}
    <button @click="fetchInstance" class="ml-2 underline text-blue-600 dark:text-blue-400">
      Retry
    </button>
  </div>
  <AdminMetadataForm
    v-else
    mode="edit"
    :classUris="classUris"
    :initialInstanceUri="instanceUri"
    :initialProperties="existingProperties"
    @submit="updateInstance"
  />

  <LoadingOverlay :show="!!loadingMsg" :message="loadingMsg" />
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import LoadingOverlay from '@/components/shared/LoadingOverlay.vue'
import { useToast } from '@/composables/useToast'

const store = useAppStore()
const route = useRoute()
const router = useRouter()
const apiBase = useRuntimeConfig().public.apiBase
const toast = useToast()

const instanceUri = ref('')
const classUris = ref<string[]>([])
const existingProperties = ref<Record<string, string[]>>({})
const loading = ref(true)
const error = ref('')
const loadingMsg = ref('')

onMounted(() => {
  const rawUri = route.query.uri
  if (!rawUri || typeof rawUri !== 'string') {
    router.replace('/admin/metadata/instances')
    return
  }
  instanceUri.value = decodeURIComponent(rawUri)
  fetchInstance()
})

async function fetchInstance() {
  loading.value = true
  error.value = ''
  try {
    const res = await $fetch<any>(
      `${apiBase}/api/instances/${encodeURIComponent(instanceUri.value)}`
    )
    if (!res.types || res.types.length === 0) {
      throw new Error('Instance has no rdf:type')
    }
    classUris.value = res.types
    existingProperties.value = res.properties as Record<string, string[]>
  } catch (e: any) {
    // Extract detail from the API error if available
    const detail = e?.data?.detail || e?.message || 'Unknown error'
    error.value = `Failed to load instance: ${detail}`
    toast.error(error.value)
  } finally {
    loading.value = false
  }
}

async function updateInstance(payload: {
  classUris: string[]
  instanceUri: string
  properties: Record<string, string[]>
}) {
  loadingMsg.value = 'Updating metadata instance…'
  try {
    await $fetch(
      `${apiBase}/api/instances/${encodeURIComponent(payload.instanceUri)}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          class_uris: payload.classUris,
          properties: payload.properties,
        }),
      }
    )
    toast.success('Instance updated')
    await store.fetchState()
    navigateTo('/admin/metadata/instances')
  } catch (e: any) {
    toast.error(e?.data?.detail || e.message)
  } finally {
    loadingMsg.value = ''
  }
}
</script>