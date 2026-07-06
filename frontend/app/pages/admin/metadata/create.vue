<template>
  <div>
    <div v-if="!store.isReady" class="text-gray-500 dark:text-gray-400">Loading…</div>
    <AdminMetadataForm v-else mode="create" @submit="createInstance" />

    <LoadingOverlay :show="!!loadingMsg" :message="loadingMsg" />
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

async function createInstance(payload: { classUris: string[]; instanceUri: string; properties: Record<string, string[]> }) {
  try {
    await $fetch(`${apiBase}/api/metadata/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        class_uris: payload.classUris,
        instance_uri: payload.instanceUri,
        properties: payload.properties
      })
    })
    toast.success('Instance created')
    await store.fetchState()
    navigateTo('/admin/metadata/instances')
  } catch (e: any) {
    toast.error(e?.data?.detail || e.message)
  }
}
</script>