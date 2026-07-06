<template>
  <div class="flex gap-6">
    <!-- Left: main area -->
    <div class="flex-1 min-w-0">
      <div class="mb-4">
        <button v-if="store.instances.length > 0" @click="generateProfile"
          class="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700">
          Generate profile from metadata
        </button>
      </div>

      <!-- Tabs -->
      <ul class="flex gap-1 mb-4">
        <li v-for="tab in mainTabs" :key="tab" @click="activeTab = tab"
          class="px-3 py-1 rounded cursor-pointer transition-colors"
          :class="activeTab === tab ? 'bg-gray-400 dark:bg-gray-500 text-white font-semibold' : 'bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600'">
          {{ tabLabel(tab) }}
        </li>
      </ul>

      <!-- Active entities table -->
      <table class="w-full border-collapse border border-gray-300 dark:border-gray-600">
        <thead>
          <tr class="bg-gray-50 dark:bg-gray-700">
            <th v-if="isPropertyTab"
              class="border border-gray-300 dark:border-gray-600 p-2 text-left w-8 text-gray-700 dark:text-gray-300">
            </th>
            <th class="border border-gray-300 dark:border-gray-600 p-2 text-left text-gray-700 dark:text-gray-300">URI
            </th>
            <th v-if="activeTab === 'individual'"
              class="border border-gray-300 dark:border-gray-600 p-2 text-left text-gray-700 dark:text-gray-300">Types
            </th>
            <th v-if="isPropertyTab"
              class="border border-gray-300 dark:border-gray-600 p-2 text-left text-gray-700 dark:text-gray-300">Domain
            </th>
            <th class="border border-gray-300 dark:border-gray-600 p-2 text-left text-gray-700 dark:text-gray-300">
              Source</th>
            <th class="border border-gray-300 dark:border-gray-600 p-2 text-left w-24 text-gray-700 dark:text-gray-300">
              Actions</th>
          </tr>
        </thead>

        <SortableTbody v-if="isPropertyTab" :key="sortableKey" v-model="filteredLocalEntities"
          @orderChanged="saveNewOrder">
          <ProfileEntityRow v-for="entity in filteredLocalEntities" :key="entity.uri" :entity="entity" :draggable="true"
            :showDomain="true" @remove="removeEntity" />
        </SortableTbody>

        <tbody v-else>
          <ProfileEntityRow v-for="entity in sortedActiveEntities" :key="entity.uri" :entity="entity" :draggable="false"
            :showTypes="activeTab === 'individual'" @remove="removeEntity" />
        </tbody>
      </table>

      <p v-if="(isPropertyTab ? filteredLocalEntities : sortedActiveEntities).length === 0"
        class="text-gray-500 dark:text-gray-400 mt-2">
        No active entities of this type.
      </p>
    </div>

    <!-- Right sidebar -->
    <aside class="w-72 shrink-0">
      <div class="mb-6">
        <h3 class="text-lg font-semibold mb-2 text-gray-900 dark:text-gray-100">Filter Entities</h3>
        <div class="space-y-3">
          <SearchBox v-model="searchQuery" placeholder="Filter entities…" />
          <select v-model="sourceFilter"
            class="border border-gray-300 dark:border-gray-600 rounded px-3 py-2 w-full bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100">
            <option v-for="opt in sourceOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </div>
      </div>

      <div class="sticky top-0">
        <h3 class="text-lg font-semibold mb-2 text-gray-900 dark:text-gray-100">Add Entity</h3>
        <div class="max-h-96 overflow-y-auto overflow-x-hidden border border-gray-300 dark:border-gray-600 rounded py-2 dark:bg-gray-800">
          <button v-for="entity in filteredInactiveEntities" :key="entity.uri"
            class="flex items-stretch justify-between py-1 hover:text-blue-600 dark:hover:text-blue-400 text-sm cursor-pointer border-b border-gray-200 dark:border-gray-700 last:border-0 hover:bg-gray-100 dark:hover:bg-gray-700 w-full"
            :class="{ 'text-gray-500 dark:text-gray-400': !entity.in_onto && entity.ontology !== 'System' }"
            @click="addEntity(entity.uri)" title="Add entity">
            <span class="pl-2 py-2 text-left leading-4 text-gray-900 dark:text-gray-100 break-all">{{ formatUri(entity.uri)
            }}</span>
          </button>
          <p v-if="!filteredInactiveEntities.length" class="text-gray-500 dark:text-gray-400 text-sm mt-2">
            No inactive entities of this type.
          </p>
        </div>
      </div>
    </aside>

    <LoadingOverlay :show="!!loadingMsg" :message="loadingMsg" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useDisplay } from '@/composables/useDisplay'
import type { ProfileEntityItem } from '@/types'
import SortableTbody from '@/components/admin/SortableTbody.vue'
import ProfileEntityRow from '@/components/admin/ProfileEntityRow.vue'
import LoadingOverlay from '@/components/shared/LoadingOverlay.vue'
import SearchBox from '@/components/shared/SearchBox.vue'
import { useToast } from '@/composables/useToast'

const store = useAppStore()
const { formatUri } = useDisplay()
const apiBase = useRuntimeConfig().public.apiBase
const route = useRoute()
const router = useRouter()
const loadingMsg = ref('')
const toast = useToast()

const activeTab = computed({
  get: () => (route.query.tab as string) || 'class',
  set: (tab: string) => router.replace({ query: { ...route.query, tab } })
})

const searchQuery = ref('')
const sourceFilter = ref('all')

const sourceOptions = computed(() => {
  const options: { label: string; value: string }[] = [{ label: 'All', value: 'all' }]
  for (const o of store.ontologies) {
    options.push({ label: o.title || o.filename, value: o.filename })
  }
  options.push({ label: 'Metadata-only', value: 'metadata' })
  return options
})

const mainTabs = computed(() => {
  const types = new Set(store.profileEntities.map(e => e.type))
  const base = ['class', 'object_property', 'datatype_property', 'annotation_property', 'datatype']
  if (types.has('individual')) base.push('individual')
  return base
})

const isPropertyTab = computed(() =>
  ['object_property', 'datatype_property', 'annotation_property'].includes(activeTab.value)
)

function entityMatchesSearch(entity: ProfileEntityItem, query: string): boolean {
  if (!query) return true
  const q = query.toLowerCase()
  const display = entity.uri.toLowerCase()
  return display.includes(q) || entity.uri.toLowerCase().includes(q)
}

function entityMatchesSource(entity: ProfileEntityItem): boolean {
  const sources = entity.sources || []
  if (sourceFilter.value === 'all') return true
  if (sourceFilter.value === 'metadata') {
    return sources.length === 1 && sources[0] === 'Metadata'
  }
  return sources.includes(sourceFilter.value)
}

function entityMatchesFilters(entity: ProfileEntityItem): boolean {
  return entityMatchesSearch(entity, searchQuery.value) && entityMatchesSource(entity)
}

const displayedActiveEntities = computed(() =>
  store.profileEntities.filter(e => e.type === activeTab.value && e.active)
)

const localEntities = ref<ProfileEntityItem[]>([])
watch(displayedActiveEntities, (val) => { localEntities.value = [...val] }, { immediate: true })

const filteredLocalEntities = computed(() => localEntities.value.filter(entityMatchesFilters))

const sortedActiveEntities = computed(() => localEntities.value.filter(entityMatchesFilters))

const inactiveByType = computed(() => {
  const groups: Record<string, ProfileEntityItem[]> = {}
  for (const e of store.profileEntities) {
    if (!e.active) {
      const arr = groups[e.type] ?? (groups[e.type] = [])
      arr.push(e)
    }
  }
  return groups
})

const filteredInactiveEntities = computed(() => {
  const list = inactiveByType.value[activeTab.value] || []
  return list.filter(entityMatchesFilters)
})

function sourceLabel(sources?: string[]): string {
  if (!sources || sources.length === 0) return '—'
  return sources.map(src => {
    if (src === 'Metadata') return 'Metadata-only'
    if (src === 'System') return 'System'
    const onto = store.ontologies.find(o => o.filename === src)
    return onto?.title || src
  }).join(', ')
}

const sortableKey = computed(() =>
  activeTab.value + '-' + displayedActiveEntities.value.map(e => e.uri).join(',')
)

function tabLabel(type: string): string {
  const overrides: Record<string, string> = {
    'object_property': 'Object Properties',
    'datatype_property': 'Data Properties',
    'annotation_property': 'Annotation Properties',
    'datatype': 'Datatypes',
    'individual': 'Individuals',
    'class': 'Classes'
  }
  return overrides[type] || type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) + 's'
}

async function addEntity(uri: string) {
  const entity = store.profileEntities.find(e => e.uri === uri)
  if (!entity) return

  if (entity.type === 'class') {
    await store.addClass(uri)
  } else if (entity.type === 'datatype') {
    await store.addDatatype(uri)
  } else if (entity.type === 'individual') {
    await store.addIndividual(uri)
  } else {
    await store.addPropertyGlobal(uri)
  }
  await store.fetchState()
}

async function removeEntity(uri: string) {
  const entity = store.profileEntities.find(e => e.uri === uri)
  if (!entity) return

  if (entity.type === 'class') {
    await store.removeClass(uri)
  } else if (entity.type === 'datatype') {
    await store.removeDatatype(uri)
  } else if (entity.type === 'individual') {
    await store.removeIndividual(uri)
  } else {
    await store.removePropertyGlobal(uri)
  }
  await store.fetchState()
}

async function generateProfile() {
  loadingMsg.value = 'Generating application profile from metadata…'
  try {
    await store.generateProfileFromMetadata()
    await store.fetchState()
    toast.success('Profile generated from metadata')
  }
  catch {
    toast.error('Generation failed')
  } finally {
    loadingMsg.value = ''
  }
}

async function saveNewOrder(list: ProfileEntityItem[]) {
  const filteredUris = new Set(filteredLocalEntities.value.map(e => e.uri))
  const nonFiltered = localEntities.value.filter(e => !filteredUris.has(e.uri))
  localEntities.value = [...nonFiltered, ...list]

  const items = localEntities.value.map((entity, index) => ({ uri: entity.uri, order: index }))
  if (!items.length) return
  await $fetch(`${apiBase}/api/profile/update-order`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items })
  })
  await store.fetchState()
}
</script>