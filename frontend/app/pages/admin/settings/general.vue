<template>
  <div>
    <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-gray-100">General Settings</h2>

    <form @submit.prevent="save">
      <!-- Website Title -->
      <div class="mb-4">
        <label class="block mb-1 text-gray-700 dark:text-gray-300">Website Title</label>
        <input v-model="title" type="text"
          class="border border-gray-300 dark:border-gray-600 p-2 rounded w-full max-w-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
          placeholder="Semantta" />
      </div>

      <!-- Base IRI -->
      <div class="mb-4">
        <label class="block mb-1 text-gray-700 dark:text-gray-300">Base IRI</label>
        <input v-model="baseIri" type="url"
          class="border border-gray-300 dark:border-gray-600 p-2 rounded w-full max-w-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
          placeholder="https://example.com/data/" />
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">
          Local instances (urn:uuid:…) will use this IRI as their prefix.
          Changing the Base IRI only affects new instances.
          To update existing local data, use the button below.
        </p>

        <button type="button" @click="showConfirm = true"
          class="mt-2 bg-orange-600 text-white px-4 py-2 rounded hover:bg-orange-700">
          Apply to all local data
        </button>
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">
          Rewrites all locally created instance URIs to use the Base IRI.
          Imported metadata is not affected.
        </p>
      </div>

      <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
        Save Settings
      </button>
      <p v-if="saved" class="text-green-600 dark:text-green-400 mt-2">Settings saved.</p>
    </form>

    <ConfirmDialog :show="showConfirm" message="Apply Base IRI to all existing local instances? This cannot be undone."
      @confirm="applyBaseIri" @cancel="showConfirm = false" />

    <LoadingOverlay :show="!!loadingMsg" :message="loadingMsg" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import ConfirmDialog from '@/components/admin/ConfirmDialog.vue'
import LoadingOverlay from '@/components/shared/LoadingOverlay.vue'
import { useToast } from '@/composables/useToast'

const store = useAppStore()
const apiBase = useRuntimeConfig().public.apiBase
const toast = useToast()

const title = ref('Semantta')
const baseIri = ref('')
const saved = ref(false)
const showConfirm = ref(false)
const loadingMsg = ref('')

onMounted(async () => {
  try {
    const data = await $fetch<{ site_title: string; base_iri: string }>(`${apiBase}/api/settings`)
    title.value = data.site_title
    baseIri.value = data.base_iri
  } catch (e) {
    console.error('Failed to load settings', e)
  }
})

async function save() {
  await $fetch(`${apiBase}/api/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      site_title: title.value,
      base_iri: baseIri.value
    })
  })
  if (store.siteTitle !== undefined) store.siteTitle = title.value
  if (store.baseIri !== undefined) store.baseIri = baseIri.value
  saved.value = true
  setTimeout(() => (saved.value = false), 2000)
}

async function applyBaseIri() {
  showConfirm.value = false
  loadingMsg.value = 'Updating all local instance URIs…'
  try {
    const res = await $fetch<{ updated: number }>(`${apiBase}/api/settings/apply-base-iri`, { method: 'POST' })
    toast.success(`Updated ${res.updated} instance(s).`)
    await store.fetchState()
  } catch (e: any) {
    toast.error('Application failed: ' + (e?.message || e))
  } finally {
    loadingMsg.value = ''
  }
}
</script>