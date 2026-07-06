<template>
  <div>
    <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-gray-100">{{ pageTitle }}</h2>
    <p class="text-sm text-gray-600 dark:text-gray-400 mb-4">{{ instanceUri }}</p>

    <!-- Tabs -->
    <div class="flex gap-2 mb-4">
      <button @click="activeTab = 'description'"
        :class="activeTab === 'description' ? 'bg-blue-600 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'"
        class="px-3 py-1 rounded">
        Description
      </button>
      <button @click="activeTab = 'graph'"
        :class="activeTab === 'graph' ? 'bg-blue-600 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'"
        class="px-3 py-1 rounded">
        Graph
      </button>
      <button @click="activeTab = 'syntax'"
        :class="activeTab === 'syntax' ? 'bg-blue-600 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'"
        class="px-3 py-1 rounded">
        Syntax
      </button>
    </div>

    <!-- Description tab -->
    <div v-if="activeTab === 'description'">
      <div v-if="loadingDesc" class="text-gray-500 dark:text-gray-400">Loading…</div>
      <div v-else-if="descError" class="text-red-600 dark:text-red-400">{{ descError }}</div>
      <div v-else>
        <h3 class="font-semibold mb-2 text-gray-900 dark:text-gray-100">Types</h3>
        <ul class="list-disc ml-5 mb-4 text-gray-700 dark:text-gray-300">
          <li v-for="t in instanceTypes" :key="t">
            <a :href="t" target="_blank" class="hover:underline">{{ formatUri(t) }}</a>
          </li>
        </ul>

        <h3 class="font-semibold mb-2 text-gray-900 dark:text-gray-100">Properties</h3>
        <div class="space-y-2">
          <template v-for="pred in orderedPropertyKeys" :key="pred">
            <div class="border-b border-gray-200 dark:border-gray-700 pb-2">
              <a :href="pred" target="_blank" class="font-medium text-gray-700 dark:text-gray-300 hover:underline">{{
                formatUri(pred) }}</a>
              <div class="ml-4">
                <template v-for="v in instanceProperties[pred]" :key="v">
                  <!-- Regular URI value -->
                  <template v-if="!isBlankNode(String(v))">
                    <NuxtLink v-if="isExistingInstance(String(v))"
                      :to="`/dataset/data?uri=${encodeURIComponent(String(v))}`"
                      class="text-blue-600 dark:text-blue-400 hover:underline text-sm block">
                      {{ displayValue(String(v)) }}
                    </NuxtLink>
                    <span v-else class="text-sm block text-gray-700 dark:text-gray-300">
                      {{ displayValue(String(v)) }}
                    </span>
                  </template>

                  <!-- Pass‑through blank node? -->
                  <template v-if="isBlankNode(String(v)) && isPassThroughBlankNode(String(v), pred)">
                    <div v-for="subVal in bnodeData[String(v)].properties[pred]" :key="subVal" class="ml-2 text-sm">
                      <NuxtLink v-if="isExistingInstance(String(subVal))"
                        :to="`/dataset/data?uri=${encodeURIComponent(String(subVal))}`"
                        class="text-blue-600 dark:text-blue-400 hover:underline block">{{
                          getValueDisplayLabel(String(subVal)) }}</NuxtLink>
                      <span v-else class="block">{{ getValueDisplayLabel(String(subVal)) }}</span>
                    </div>
                  </template>

                  <!-- Regular Blank node card -->
                  <div v-else-if="isBlankNode(String(v))"
                    class="rounded p-2 mt-1 bg-gray-50 dark:bg-gray-800 text-gray-700 dark:text-gray-300"> <template
                      v-if="bnodeData && bnodeData[String(v)]">
                      <p v-if="bnodeData[String(v)].types.length"
                        class="text-sm italic text-gray-600 dark:text-gray-400">
                        <template v-for="(typeUri, idx) in bnodeData[String(v)].types" :key="typeUri">
                          <a :href="typeUri" target="_blank" class="hover:underline">{{ formatUri(typeUri) }}</a><span
                            v-if="showSeparator(idx, bnodeData[String(v)].types.length)">, </span>
                        </template>
                      </p>
                      <div v-for="(bvals, bpred) in bnodeData[String(v)].properties" :key="bpred" class="ml-2 text-sm">
                        <a :href="String(bpred)" target="_blank"
                          class="font-medium text-gray-600 dark:text-gray-400 hover:underline">{{
                            formatUri(String(bpred)) || bpred }}</a>:
                        <span>
                          <template v-for="bv in bvals" :key="bv">
                            <div>
                              <NuxtLink v-if="getBnodeValueDisplay(String(bv)).isInstance"
                                :to="`/dataset/data?uri=${encodeURIComponent(String(bv))}`"
                                class="text-blue-600 dark:text-blue-400 hover:underline text-sm block">
                                {{ getBnodeValueDisplay(String(bv)).label }}
                              </NuxtLink>
                              <span v-else class="text-sm block">
                                {{ getBnodeValueDisplay(String(bv)).label }}
                              </span>
                            </div>
                          </template>
                        </span>
                      </div>
                    </template>
                    <p v-else class="text-sm text-gray-400 dark:text-gray-500">
                      No details available for this blank node.
                    </p>
                  </div>
                </template>
              </div>
            </div>
          </template>
        </div>
        <p v-if="Object.keys(instanceProperties).length === 0" class="text-gray-500 dark:text-gray-400">No properties.
        </p>
      </div>
    </div>

    <!-- Graph tab -->
    <div v-show="activeTab === 'graph'">
      <div v-if="graphLoading" class="text-gray-500 dark:text-gray-400">Building graph…</div>
      <div v-else-if="graphError" class="text-red-600 dark:text-red-400">{{ graphError }}</div>
      <GraphView v-show="activeTab === 'graph'" :visible="activeTab === 'graph'" :instanceUri="instanceUri"
        :instanceProperties="instanceProperties" :bnodeData="bnodeData" :formatUri="formatUri"
        :isBlankNode="isBlankNode" :getDisplayLabel="displayValue" @loading="onGraphLoading" @error="onGraphError" />
    </div>

    <!-- Syntax tab -->
    <div v-if="activeTab === 'syntax'">
      <div class="flex items-center gap-3 mb-3">
        <label class="text-sm text-gray-700 dark:text-gray-300">Format:</label>
        <select v-model="syntaxFormat" @change="loadSyntax"
          class="border border-gray-300 dark:border-gray-600 rounded p-1 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100">
          <option v-for="(mime, key) in formatMime" :key="key" :value="key">{{ key }}</option>
        </select>
      </div>
      <div v-if="loadingSyntax" class="text-gray-500 dark:text-gray-400">Loading syntax…</div>
      <div v-else-if="syntaxError" class="text-red-600 dark:text-red-400">{{ syntaxError }}</div>
      <div v-else>
        <div class="relative">
          <div class="absolute top-2 right-2 flex gap-2 z-10">
            <button @click="copySyntax"
              class="text-xs bg-gray-200 dark:bg-gray-600 hover:bg-gray-300 dark:hover:bg-gray-500 px-2 py-1 rounded text-gray-700 dark:text-gray-200">
              Copy
            </button>
            <button @click="downloadSyntax"
              class="text-xs bg-gray-200 dark:bg-gray-600 hover:bg-gray-300 dark:hover:bg-gray-500 px-2 py-1 rounded text-gray-700 dark:text-gray-200">
              Download
            </button>
          </div>
          <pre
            class="bg-gray-100 dark:bg-gray-800 p-4 rounded text-sm overflow-x-auto text-gray-900 dark:text-gray-100">
        <code v-text="syntaxData"></code>
      </pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePublicDisplay } from '@/composables/usePublicDisplay'
import { useAppStore } from '@/stores/app'
import GraphView from '@/components/shared/GraphView.vue'

const route = useRoute()
const router = useRouter()
const { formatUri } = usePublicDisplay()
const store = useAppStore()
const apiBase = useRuntimeConfig().public.apiBase

const instanceUri = ref('')
const activeTab = ref('description')

onMounted(() => {
  const rawUri = route.query.uri
  if (!rawUri || typeof rawUri !== 'string') {
    router.replace('/dataset')
    return
  }
  instanceUri.value = decodeURIComponent(rawUri)
  refreshView()
})

const loadingDesc = ref(true)
const descError = ref('')
const bnodeData = ref<Record<string, any>>({})

const storeInstance = computed(() => store.instances.find((i: any) => i.uri === instanceUri.value))
const instanceTypes = computed(() => storeInstance.value?.types || [])
const instanceProperties = computed(() => storeInstance.value?.properties || {})

const syntaxLoaded = ref(false)
const graphLoaded = ref(false)

const syntaxData = ref('')
const loadingSyntax = ref(false)
const syntaxError = ref('')
const syntaxFormat = ref('turtle')

const formatMime: Record<string, string> = {
  turtle: 'text/turtle',
  xml: 'application/rdf+xml',
  jsonld: 'application/ld+json',
  nt: 'application/n-triples',
}

const graphLoading = ref(false)
const graphError = ref('')

const orderedPropertyKeys = computed(() => {
  // Build set of active property URIs from the profile
  const activePropertyUris = new Set<string>()
  for (const entity of store.profileEntities) {
    if (
      entity.active &&
      (entity.type === 'object_property' ||
        entity.type === 'datatype_property' ||
        entity.type === 'annotation_property')
    ) {
      activePropertyUris.add(entity.uri)
    }
  }

  // Build a map: property URI → order
  const orderMap: Record<string, number> = {}
  for (const entity of store.profileEntities) {
    if (
      entity.order != null &&
      activePropertyUris.has(entity.uri)
    ) {
      orderMap[entity.uri] = entity.order
    }
  }

  // Filter, then sort by order (unordered properties come last)
  return Object.keys(instanceProperties.value)
    .filter((uri) => activePropertyUris.has(uri))
    .sort((a, b) => {
      const oa = orderMap[a] ?? 9999
      const ob = orderMap[b] ?? 9999
      return oa - ob
    })
})

/** Safe filename derived from the instance label or URI */
const syntaxFileName = computed(() => {
  // Prefer the human‑readable label, strip unsafe characters
  if (storeInstance.value?.label) {
    const safe = storeInstance.value.label.replace(/[^a-zA-Z0-9\-_\.]/g, '_').replace(/_{2,}/g, '_').replace(/^_|_$/g, '')
    if (safe) return safe
  }
  // Fallback: extract the local part of the URI
  const uri = instanceUri.value
  const parts = uri.split(/[/#]/)
  const last = parts[parts.length - 1] || 'instance'
  const safe = last.replace(/[^a-zA-Z0-9\-_\.]/g, '_').replace(/_{2,}/g, '_').replace(/^_|_$/g, '')
  return safe || 'instance'
})

const pageTitle = computed(() => {
  return storeInstance.value?.label || 'Metadata'
})

useHead({ title: () => pageTitle.value })

function isExistingInstance(uri: string): boolean {
  return store.instances.some((i: any) => i.uri === uri)
}

function displayValue(uri: string): string {
  if (storeInstance.value?.label && uri === instanceUri.value) {
    return storeInstance.value.label as string
  }
  const inst = store.instances.find((i: any) => i.uri === uri)
  if (inst?.label) return inst.label as string
  return formatUri(uri) as string
}

function isBlankNode(uri: string): boolean {
  return uri.startsWith('urn:bnid:')
}

function showSeparator(index: number | string, length: number): boolean {
  const numIndex = typeof index === 'string' ? parseInt(index, 10) : index
  return numIndex < length - 1
}

function getBnodeValueDisplay(uri: string): { label: string; isInstance: boolean } {
  return {
    label: displayValue(uri),
    isInstance: isExistingInstance(uri),
  }
}

/**
 * A pass‑through blank node is one that has no type and only re‑uses
 * the same property that already points to it.
 */
function isPassThroughBlankNode(bnodeUri: string, propertyUri: string): boolean {
  const bnode = bnodeData.value?.[bnodeUri]
  if (!bnode) return false
  if (bnode.types && bnode.types.length > 0) return false
  const props = bnode.properties || {}
  const propKeys = Object.keys(props)
  return propKeys.length === 1 && propKeys[0] === propertyUri
}

/** Get the display label for a value that is a URI (not a blank node). */
function getValueDisplayLabel(uri: string): string {
  const inst = store.instances.find((i: any) => i.uri === uri)
  return inst?.label || formatUri(uri)
}

async function refreshView() {
  loadingDesc.value = true
  descError.value = ''
  try {
    // If the instance is already in the store, use its data
    if (storeInstance.value) {
      // Blank‑node data might not be in the store – fetch it once
      const res = await $fetch<any>(`${apiBase}/api/instances/${encodeURIComponent(instanceUri.value)}`)
      bnodeData.value = res.bnodes || {}
    } else {
      // Not in store – fetch instance and blank‑node data in one call
      await store.fetchState()
      if (!storeInstance.value) {
        const res = await $fetch<any>(`${apiBase}/api/instances/${encodeURIComponent(instanceUri.value)}`)
        if (!res || !res.types || res.types.length === 0) {
          descError.value = 'Instance not found.'
          loadingDesc.value = false
          return
        }
        bnodeData.value = res.bnodes || {}
      } else {
        // Instance appeared after fetchState, still need bnodeData
        const res = await $fetch<any>(`${apiBase}/api/instances/${encodeURIComponent(instanceUri.value)}`)
        bnodeData.value = res.bnodes || {}
      }
    }
  } catch (e: any) {
    descError.value = e.message || 'Failed to load instance'
  } finally {
    loadingDesc.value = false
  }
}

watch(
  () => route.query.uri,
  async (newUri) => {
    if (newUri) {
      instanceUri.value = decodeURIComponent(newUri as string)
      activeTab.value = 'description'
      // Reset lazy‑load flags – GraphView and syntax will re‑build on demand
      syntaxLoaded.value = false
      graphLoaded.value = false
      syntaxData.value = ''
      await refreshView()
    }
  }
)

async function loadSyntax() {
  loadingSyntax.value = true
  syntaxError.value = ''
  try {
    const res = await $fetch<string>(
      `${apiBase}/api/instances/${encodeURIComponent(instanceUri.value)}/syntax?format=${syntaxFormat.value}`,
      { responseType: 'text' }
    )
    syntaxData.value = res
  } catch (e: any) {
    syntaxError.value = e.message || 'Failed to load syntax'
  } finally {
    loadingSyntax.value = false
  }
}

async function copySyntax() {
  try {
    await navigator.clipboard.writeText(syntaxData.value)
    alert('Copied to clipboard')
  } catch {
    alert('Failed to copy')
  }
}

function downloadSyntax() {
  const mime = formatMime[syntaxFormat.value] || 'text/plain'
  const blob = new Blob([syntaxData.value], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const ext = syntaxFormat.value === 'turtle' ? 'ttl' : syntaxFormat.value === 'jsonld' ? 'json' : syntaxFormat.value
  a.download = `${syntaxFileName.value}.${ext}`
  a.click()
  URL.revokeObjectURL(url)
}

function onGraphLoading(val: boolean) { graphLoading.value = val }
function onGraphError(msg: string) { graphError.value = msg }

watch(activeTab, async (newTab) => {
  if (newTab === 'syntax' && !syntaxLoaded.value) {
    await loadSyntax()
    syntaxLoaded.value = true
  }
  if (newTab === 'graph' && !graphLoaded.value) {
    graphLoaded.value = true
  }
})
</script>