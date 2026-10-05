<template>
  <div>
    <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-gray-100">
      Dataset
    </h2>

    <p class="text-sm text-gray-600 dark:text-gray-400 mb-4">
      Showing
      <template v-if="store.instanceTotal">
        {{ pageStart }}–{{ pageEnd }}
        of {{ store.instanceTotal }}
      </template>
      <template v-else>
        0
      </template>
      instance(s).
    </p>

    <div class="mb-4 max-w-md">
      <SearchBox v-model="searchQuery" placeholder="Search dataset…" />
    </div>

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
              <template v-for="(t, idx) in inst.types" :key="t">
                <a :href="t" target="_blank" rel="noopener noreferrer" class="hover:underline">
                  {{ formatUri(t) }}
                </a>

                <span v-if="idx < inst.types.length - 1">
                  ,
                </span>
              </template>
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
import SearchBox from '@/components/shared/SearchBox.vue'
import Pagination from '@/components/shared/Pagination.vue'

const store = useAppStore()
const { formatUri } = usePublicDisplay()

const pageSize = 50
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

watch(searchQuery, async () => {
  pageCursors.value = [null]

  if (currentPage.value !== 1) {
    currentPage.value = 1
  }

  await loadInstances()
})

onMounted(async () => {
  if (!store.isReady) {
    await store.fetchState()
  }

  await loadInstances()
})

useHead({
  title: 'Dataset',
})
</script>