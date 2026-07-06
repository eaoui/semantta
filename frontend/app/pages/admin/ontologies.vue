<template>
  <div>
    <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-gray-100">Ontologies</h2>

    <ImportBox title="Import Ontology" accept=".rdf,.owl,.xml,.ttl,.nt,.nq,.jsonld,.json,.trig,.trix"
      buttonText="Import" @upload="handleUpload" />

    <div v-if="isLoading" class="text-gray-500 dark:text-gray-400">Loading…</div>
    <p v-else-if="store.error" class="text-red-600 dark:text-red-400">{{ store.error }}</p>

    <div v-else-if="store.ontologies.length" class="space-y-3">
      <ItemCard v-for="onto in store.ontologies" :key="onto.filename" :title="onto.title || onto.filename"
        :version="onto.version" :description="onto.iri">
        <!-- Namespaces -->
        <div v-if="onto.namespaces.length" class="flex flex-wrap gap-1 mt-2">
          <span v-for="ns in onto.namespaces" :key="ns"
            class="text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 px-1.5 py-0.5 rounded border border-gray-300 dark:border-gray-600"
            :title="ns">{{ ns }}</span>
        </div>

        <!-- Top‑right actions -->
        <template #actions>
          <a :href="`${apiBase}/api/ontology/raw/${encodeURIComponent(onto.filename)}`" target="_blank"
            class="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300">
            <PhosphorIcon name="file-code" size="16" />
          </a>
          <PhosphorIcon name="trash" size="16" class="text-red-600 hover:text-red-800 cursor-pointer"
            @click="selectedFile = onto.filename; confirmDelete = true" />
        </template>
      </ItemCard>
    </div>

    <p v-else class="text-gray-500 dark:text-gray-400">No ontologies imported yet.</p>

    <ConfirmDialog :show="confirmDelete" message="Delete this ontology? All related data will be removed."
      @confirm="handleDelete" @cancel="confirmDelete = false; selectedFile = ''" />

    <LoadingOverlay :show="!!loadingMsg" :message="phase || loadingMsg" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import ImportBox from '@/components/admin/ImportBox.vue'
import ItemCard from '@/components/admin/ItemCard.vue'
import ConfirmDialog from '@/components/admin/ConfirmDialog.vue'
import LoadingOverlay from '@/components/shared/LoadingOverlay.vue'
import { useProgress } from '@/composables/useProgress'
import { useToast } from '@/composables/useToast'

const store = useAppStore()
const apiBase = useRuntimeConfig().public.apiBase
const toast = useToast()
const { phase, startPolling, stopPolling } = useProgress()

const loadingMsg = ref('')
const isLoading = ref(true)
const selectedFile = ref('')
const confirmDelete = ref(false)

onMounted(async () => {
  if (!store.isReady) await store.fetchState()
  isLoading.value = false
})

async function handleUpload(file: File) {
  loadingMsg.value = 'Importing ontology…'
  startPolling()
  try {
    await store.uploadOntology(file)
  } catch (e: any) {
    toast.error(e?.data?.detail || e.message)
  } finally {
    stopPolling()
    loadingMsg.value = ''
  }
}

async function handleDelete() {
  if (!selectedFile.value) return
  confirmDelete.value = false
  loadingMsg.value = 'Deleting ontology and rebuilding caches…'
  try {
    await store.deleteOntology(selectedFile.value)
    selectedFile.value = ''
  } finally {
    loadingMsg.value = ''
  }
}
</script>