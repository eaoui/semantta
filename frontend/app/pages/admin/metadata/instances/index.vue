<template>
  <div>
    <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-gray-100">Instances</h2>

    <!-- Create button -->
    <div class="mb-4">
      <NuxtLink to="/admin/metadata/create" class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
        Create Metadata
      </NuxtLink>
    </div>

    <!-- Filters -->
    <div class="mb-4 flex flex-wrap gap-4 items-end">

      <div>
        <SearchBox v-model="searchQuery" placeholder="Search instances…" />
      </div>

      <div>
        <label class="block text-sm mb-1 text-gray-700 dark:text-gray-300">Type:</label>
        <select v-model="selectedType"
          class="border border-gray-300 dark:border-gray-600 rounded p-1 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100">
          <option value="">All types</option>
          <option v-for="t in uniqueTypes" :key="t" :value="t">
            {{ formatUri(t) }}
          </option>
        </select>
      </div>

      <div>
        <label class="block text-sm mb-1 text-gray-700 dark:text-gray-300">Source:</label>
        <select v-model="sourceFilter"
          class="border border-gray-300 dark:border-gray-600 rounded p-1 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100">
          <option value="">All</option>
          <option value="imported">Imported</option>
          <option value="created">Created</option>
        </select>
      </div>

      <div>
        <label class="flex items-center gap-2 cursor-pointer text-gray-700 dark:text-gray-300">
          <input type="checkbox" v-model="showBlankNodes" class="h-4 w-4" />
          <span class="text-sm">Display blank nodes</span>
        </label>
      </div>
    </div>

    <div v-if="store.loading" class="text-gray-500 dark:text-gray-400">Loading…</div>
    <p v-else-if="store.error" class="text-red-600 dark:text-red-400">{{ store.error }}</p>
    <div v-else-if="filteredInstances.length">
      <p class="text-sm text-gray-600 dark:text-gray-400 mb-2">Showing {{ filteredInstances.length }} instance(s)</p>
      <table class="w-full border-collapse border border-gray-300 dark:border-gray-600">
        <thead>
          <tr class="bg-gray-50 dark:bg-gray-700">
            <th class="border border-gray-300 dark:border-gray-600 p-2 text-left text-gray-700 dark:text-gray-300">Name
            </th>
            <th class="border border-gray-300 dark:border-gray-600 p-2 text-left text-gray-700 dark:text-gray-300">Types
            </th>
            <th class="border border-gray-300 dark:border-gray-600 p-2 text-left text-gray-700 dark:text-gray-300">
              Source</th>
            <th class="border border-gray-300 dark:border-gray-600 p-2 text-left text-gray-700 dark:text-gray-300">
              Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="inst in filteredInstances" :key="inst.uri" class="hover:bg-gray-50 dark:hover:bg-gray-800">
            <td
              class="border border-gray-300 dark:border-gray-600 p-2 text-sm break-all text-gray-900 dark:text-gray-100">
              {{ instanceDisplayName(inst) }}
            </td>
            <td class="border border-gray-300 dark:border-gray-600 p-2 text-sm text-gray-700 dark:text-gray-300">
              {{inst.types.map((t: string) => formatUri(t)).join(', ')}}
            </td>
            <td
              class="border border-gray-300 dark:border-gray-600 p-2 text-sm capitalize text-gray-700 dark:text-gray-300">
              {{ inst.source || 'imported' }}
            </td>
            <td class="border border-gray-300 dark:border-gray-600 p-2 text-sm">
              <div class="flex gap-2">
                <PhosphorIcon name="star" size="16"
                  :class="inst.starred ? 'text-yellow-500 hover:text-yellow-600' : 'text-gray-400 hover:text-yellow-500'"
                  class="cursor-pointer" @click="store.toggleStar(inst.uri)" />
                <NuxtLink v-if="inst.uri && inst.uri !== 'undefined'"
                  :to="`/admin/metadata/instances/edit?uri=${encodeURIComponent(inst.uri)}`"
                  class="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300">
                  <PhosphorIcon name="pencil-simple" size="16" />
                </NuxtLink>
                <NuxtLink v-if="inst.uri && inst.uri !== 'undefined'"
                  :to="`/dataset/data?uri=${encodeURIComponent(inst.uri)}`" target="_blank"
                  class="text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
                  <PhosphorIcon name="eye" size="16" />
                </NuxtLink>
                <PhosphorIcon name="trash" size="16" class="text-red-600 hover:text-red-800 cursor-pointer"
                  @click="confirmDelete(inst.uri)" />
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="text-gray-500 dark:text-gray-400">No instances match the filters.</p>

    <AdminConfirmDialog :show="showConfirm" message="Delete this instance? This cannot be undone."
      @confirm="deleteInstance" @cancel="showConfirm = false" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useAppStore } from '@/stores/app'
import { useDisplay } from '@/composables/useDisplay'
import SearchBox from '@/components/shared/SearchBox.vue'

const store = useAppStore()
const { formatUri } = useDisplay()

function instanceDisplayName(inst: any): string {
  // In IRI mode, always show the full URI
  if (store.displayFormat === 'iri') {
    return inst.uri
  }
  // In label/prefix mode, prefer the human‑readable label
  if (inst.label && inst.label.trim()) {
    return inst.label
  }
  // Fallback: formatted URI (prefix/label based on current setting)
  return formatUri(inst.uri) || inst.uri
}

const showBlankNodes = ref(false)
const selectedType = ref('')
const searchQuery = ref('')
const sourceFilter = ref('')

const uniqueTypes = computed(() => {
  const types = store.instances.flatMap(inst => inst.types)
  return [...new Set(types)].sort()
})

const filteredInstances = computed(() => {
  let list = store.instances.filter(
    (inst) =>
      inst.uri &&
      inst.uri !== 'undefined' &&
      (inst.uri.startsWith('http') || inst.uri.startsWith('urn:'))
  )
  if (!showBlankNodes.value) {
    list = list.filter(inst => !inst.is_blank)
  }
  if (selectedType.value) {
    list = list.filter(inst => inst.types.includes(selectedType.value))
  }

  // Filter by search query (match against display name)
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase().trim()
    list = list.filter(inst => {
      const name = instanceDisplayName(inst).toLowerCase()
      return name.includes(q) || inst.uri.toLowerCase().includes(q)
    })
  }

  // Filter by source
  if (sourceFilter.value === 'imported') {
    list = list.filter(inst => inst.source !== 'created')
  } else if (sourceFilter.value === 'created') {
    list = list.filter(inst => inst.source === 'created')
  }

  // Sort starred instances first
  const starred = list.filter(i => i.starred)
  const unstarred = list.filter(i => !i.starred)
  list = [...starred, ...unstarred]

  return list
})

const showConfirm = ref(false)
const instanceToDelete = ref<string | null>(null)

function confirmDelete(uri: string) {
  instanceToDelete.value = uri
  showConfirm.value = true
}

async function deleteInstance() {
  if (!instanceToDelete.value) return
  showConfirm.value = false
  try {
    await store.deleteInstance(instanceToDelete.value)
  } catch (e) {
    console.error(e)
  }
}
</script>