<template>
  <div>
    <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-gray-100">Metadata Imports</h2>

    <ImportBox title="Import Metadata File" accept=".nt,.txt,.ttl,.rdf,.xml,.jsonld,.json,.trig,.trix,.nq"
      buttonText="Import" @upload="upload">
      <div class="mt-3 space-y-2">
        <label v-if="hasExistingMetadata"
          class="flex items-center gap-2 cursor-pointer text-gray-700 dark:text-gray-300">
          <input type="checkbox" v-model="mergeInstances" class="h-4 w-4" />
          <span class="text-sm">Integrate into existing metadata (Recommended)</span>
        </label>
        <label class="flex items-center gap-2 cursor-pointer text-gray-700 dark:text-gray-300">
          <input type="checkbox" v-model="integrateVocab" class="h-4 w-4" />
          <span class="text-sm">Integrate all vocabularies into Application Profile</span>
        </label>
      </div>
    </ImportBox>

    <!-- File list -->
    <div v-if="store.metadataFiles.length">
      <h3 class="text-lg font-semibold mb-2 text-gray-900 dark:text-gray-100">Imported Metadata Files</h3>
      <div class="space-y-3">
        <ItemCard v-for="mf in store.metadataFiles" :key="mf.filename" :title="mf.filename">
          <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">
            Instances: {{ mf.instances_count }} · Triples: {{ mf.triples_count }}
          </p>
          <div class="flex flex-wrap gap-1 mt-2">
            <span v-for="ns in mf.namespaces" :key="ns" class="text-xs px-1.5 py-0.5 rounded border" :class="ontologyBaseNamespaces.includes(ns)
              ? 'bg-green-100 dark:bg-green-900 border-green-300 dark:border-green-700 text-green-800 dark:text-green-200'
              : 'bg-gray-100 dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300'"
              :title="ns">{{ ns }}</span>
          </div>
          <div class="mt-2 flex gap-4 text-sm">
            <span
              :class="mf.vocab_integrated ? 'text-green-600 dark:text-green-400' : 'text-orange-600 dark:text-orange-400'">
              {{ mf.vocab_integrated ? '✓ Vocab integrated' : '✗ Vocab not integrated' }}
            </span>
            <span v-if="hasMultipleSources"
              :class="mf.instances_merged ? 'text-green-600 dark:text-green-400' : 'text-orange-600 dark:text-orange-400'">
              {{ mf.instances_merged ? '✓ Merged' : '✗ Standalone' }}
            </span>
          </div>

          <template #actions>
            <a :href="`${apiBase}/api/metadata/raw/${encodeURIComponent(mf.filename)}`" target="_blank"
              class="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300">
              <PhosphorIcon name="file-code" size="16" />
            </a>
            <PhosphorIcon name="trash" size="16" class="text-red-600 hover:text-red-800 cursor-pointer"
              @click="selectedFile = mf.filename; confirmDelete = true" />
          </template>

          <template v-if="!mf.vocab_integrated || (hasMultipleSources && !mf.instances_merged)" #footer>
            <button v-if="!mf.vocab_integrated" @click="integrateVocabForFile(mf.filename)"
              class="text-sm bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 px-2 py-1 rounded hover:bg-blue-200 dark:hover:bg-blue-800">
              Integrate vocabulary now
            </button>
            <button v-if="hasMultipleSources && !mf.instances_merged" @click="mergeMetadataForFile(mf.filename)"
              class="text-sm bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 px-2 py-1 rounded hover:bg-blue-200 dark:hover:bg-blue-800">
              Merge metadata now
            </button>
          </template>
        </ItemCard>
      </div>
    </div>

    <ConfirmDialog :show="confirmDelete"
      message="Delete this metadata file? Its content will be removed from the system." @confirm="handleDeleteFile"
      @cancel="confirmDelete = false; selectedFile = ''" />

    <LoadingOverlay :show="!!loadingMsg" :message="phase || loadingMsg" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
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

const integrateVocab = ref(false)
const mergeInstances = ref(true)
const loadingMsg = ref('')
const selectedFile = ref('')
const confirmDelete = ref(false)

const hasExistingMetadata = computed(() => store.instances.length > 0 || store.metadataFiles.length > 0)
const hasMultipleSources = computed(() => store.instances.length > 0 || store.metadataFiles.length > 1)

// Ontology base namespaces (derived from each ontology's IRI)
const ontologyBaseNamespaces = computed(() =>
  store.ontologies.map((onto) => {
    const idx = Math.max(onto.iri.lastIndexOf('/'), onto.iri.lastIndexOf('#'))
    return idx >= 0 ? onto.iri.substring(0, idx + 1) : onto.iri
  })
)

async function upload(file: File) {
  loadingMsg.value = 'Importing metadata…'
  startPolling()
  try {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('integrate_vocab', String(integrateVocab.value))
    formData.append('merge_instances', String(hasExistingMetadata.value ? mergeInstances.value : false))
    await $fetch(`${apiBase}/api/metadata/upload`, { method: 'POST', body: formData })
    await store.fetchState()
  } catch (e: any) {
    toast.error(e?.data?.detail || e.message)
  } finally {
    stopPolling()
    loadingMsg.value = ''
  }
}

async function handleDeleteFile() {
  if (!selectedFile.value) return
  confirmDelete.value = false
  loadingMsg.value = 'Removing metadata file…'
  try {
    await store.deleteMetadataFile(selectedFile.value)
    selectedFile.value = ''
  } finally {
    loadingMsg.value = ''
  }
}

async function integrateVocabForFile(filename: string) {
  try {
    await $fetch(`${apiBase}/api/metadata/file/${encodeURIComponent(filename)}/integrate-vocab`, { method: 'POST' })
    await store.fetchState()
  } catch (e: any) { toast.error(e.message) }
}

async function mergeMetadataForFile(filename: string) {
  try {
    await $fetch(`${apiBase}/api/metadata/file/${encodeURIComponent(filename)}/merge-metadata`, { method: 'POST' })
    await store.fetchState()
  } catch (e: any) { toast.error(e.message) }
}
</script>