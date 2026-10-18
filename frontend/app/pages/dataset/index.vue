<template>
  <div>
    <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-gray-100">
      Dataset
    </h2>

    <div class="flex flex-col md:flex-row gap-6 items-start">
      <main class="w-full min-w-0 flex-1">

        <div v-if="store.instancesLoading" class="text-gray-500 dark:text-gray-400">
          Loading…
        </div>

        <p v-else-if="store.instancesError" class="text-red-600 dark:text-red-400">
          {{ store.instancesError }}
        </p>

        <div v-else-if="store.instances.length">
          <table class="w-full border-collapse border border-gray-300 dark:border-gray-600">
            <thead>
              <tr class="bg-gray-50 dark:bg-gray-700">
                <th class="border border-gray-300 dark:border-gray-600 p-2 text-left text-gray-700 dark:text-gray-300">
                  Name
                </th>

                <th class="border border-gray-300 dark:border-gray-600 p-2 text-left text-gray-700 dark:text-gray-300">
                  Types
                </th>
              </tr>
            </thead>

            <tbody>
              <tr v-for="inst in store.instances" :key="inst.uri" class="hover:bg-gray-50 dark:hover:bg-gray-800">
                <td class="border border-gray-300 dark:border-gray-600 p-2 text-sm">
                  <NuxtLink v-if="inst.uri && inst.uri !== 'undefined'"
                    :to="`/dataset/data?uri=${encodeURIComponent(inst.uri)}`"
                    class="text-blue-600 dark:text-blue-400 hover:underline block leading-6">
                    {{ instanceDisplayName(inst) }}
                  </NuxtLink>
                </td>

                <td class="border border-gray-300 dark:border-gray-600 p-2 text-sm text-gray-700 dark:text-gray-300">
                  <div class="flex flex-col items-start gap-1">
                    <a v-for="typeUri in inst.types" :key="typeUri" :href="typeUri" target="_blank"
                      rel="noopener noreferrer" class="block hover:underline">
                      {{ formatUri(typeUri) }}
                    </a>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>

          <Pagination :current-page="currentPage" :has-next="store.instancesHasMore" :loading="store.instancesLoading"
            @page-change="goToPage" />
        </div>

        <p v-else class="text-gray-500 dark:text-gray-400">
          No instances available.
        </p>
      </main>

      <InstanceFilterSidebar mode="dataset" v-model:search="searchQuery" v-model:selected-type="selectedType"
        :search-placeholder="'Search dataset…'" :type-options="typeOptions" :page-start="pageStart" :page-end="pageEnd"
        :total="store.instanceTotal" :has-non-countable-filters="hasNonCountableFilters"
        :show-count="!store.instancesLoading && !store.instancesError && store.instances.length > 0" />

    </div>
  </div>
</template>

<script setup lang="ts">
import {
  ref,
  computed,
  onMounted,
  watch,
} from 'vue'

import { useAppStore } from '@/stores/app'
import { usePublicDisplay } from '@/composables/usePublicDisplay'
import InstanceFilterSidebar from '@/components/shared/InstanceFilterSidebar.vue'
import Pagination from '@/components/shared/Pagination.vue'

const store = useAppStore()
const { formatUri } = usePublicDisplay()
const { fetchInstanceTypes } = useApi()

const uniqueTypes = ref<string[]>([])
const selectedType = ref('')

const typeOptions = computed(() =>
  uniqueTypes.value.map(uri => ({
    uri,
    label: formatUri(uri) || uri,
  })),
)

const hasNonCountableFilters = computed(() =>
  Boolean(searchQuery.value.trim() || selectedType.value),
)

const pageSize = 32
const currentPage = ref(1)
const pageCursors = ref<(string | null)[]>([null])
const searchQuery = ref('')

function instanceDisplayName(inst: {
  uri: string
  label?: string | null
}): string {
  return inst.label || formatUri(inst.uri)
}

const pageStart = computed(() =>
  store.instanceTotal === 0
    ? 0
    : (currentPage.value - 1) * pageSize + 1,
)

const pageEnd = computed(() =>
  store.instances.length === 0
    ? pageStart.value
    : pageStart.value +
    store.instances.length -
    1,
)

async function loadInstances() {
  const cursor =
    pageCursors.value[currentPage.value - 1] ?? null

  await store.fetchInstances({
    limit: pageSize,
    cursor: cursor || undefined,
    search: searchQuery.value,
    typeUri: selectedType.value || undefined,
    includeBlankNodes:
      store.publicShowBlankNodes,
  })

  if (
    store.instancesHasMore &&
    store.instancesNextCursor
  ) {
    pageCursors.value[currentPage.value] =
      store.instancesNextCursor
  }
}

async function goToPage(page: number) {
  if (
    page < 1 ||
    page === currentPage.value ||
    store.instancesLoading
  ) {
    return
  }

  currentPage.value = page
  await loadInstances()
}

watch(
  [searchQuery, selectedType],
  async () => {
    pageCursors.value = [null]

    if (currentPage.value !== 1) {
      currentPage.value = 1
    }

    await loadInstances()
  },
)

async function loadTypes() {
  try {
    const data = await fetchInstanceTypes()
    uniqueTypes.value = data.types
  } catch (error) {
    console.error('Failed to load instance types:', error)
  }
}

onMounted(async () => {
  if (!store.isReady) {
    await store.fetchState()
  }

  await Promise.all([
    loadTypes(),
    store.refreshInstanceCount(
      store.publicShowBlankNodes,
    ),
    loadInstances(),
  ])
})

useHead({
  title: 'Dataset',
})
</script>