<template>
  <div>
    <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-gray-100">Advanced Settings</h2>

    <div class="p-4 border border-red-300 dark:border-red-600 bg-red-50 dark:bg-red-900/20 rounded max-w-lg">
      <p class="text-sm text-red-800 dark:text-red-300 mb-3">
        This will permanently delete all ontologies, metadata, application profile,
        preferences, and cached data. The system will return to its initial state.
      </p>
      <button @click="confirmPurge = true" class="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded">
        Purge All Data
      </button>
    </div>

    <ConfirmDialog :show="confirmPurge"
      message="Are you sure? This action cannot be undone. All data will be permanently lost." @confirm="purgeAllData"
      @cancel="confirmPurge = false" />

    <LoadingOverlay :show="!!loadingMsg" :message="loadingMsg" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ConfirmDialog from '@/components/admin/ConfirmDialog.vue'
import LoadingOverlay from '@/components/shared/LoadingOverlay.vue'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const apiBase = useRuntimeConfig().public.apiBase
const confirmPurge = ref(false)
const loadingMsg = ref('')

async function purgeAllData() {
  confirmPurge.value = false
  loadingMsg.value = 'Purging all data and resetting to factory mode…'
  try {
    await $fetch(`${apiBase}/api/admin/purge`, { method: 'POST' })
    await store.fetchState()
    alert('All data has been purged. System reset complete.')
    navigateTo('/admin')
  } catch (e: any) {
    alert('Purge failed: ' + (e?.message || e))
  } finally {
    loadingMsg.value = ''
  }
}
</script>