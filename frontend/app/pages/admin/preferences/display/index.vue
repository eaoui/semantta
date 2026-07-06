<template>
  <div>
    <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-gray-100">Display Preferences</h2>

    <!-- Theme selection -->
    <div class="mb-6">
      <h3 class="text-lg font-semibold mb-2 text-gray-900 dark:text-gray-100">Theme</h3>
      <label class="mr-2 text-gray-700 dark:text-gray-300">Color mode:</label>
      <select
        v-model="themeMode"
        @change="applyTheme"
        class="border border-gray-300 dark:border-gray-600 rounded p-1 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
      >
        <option value="light">Light</option>
        <option value="dark">Dark</option>
        <option value="system">System</option>
      </select>
    </div>

    <!-- Admin display format -->
    <div class="mb-6">
      <h3 class="text-lg font-semibold mb-2 text-gray-900 dark:text-gray-100">Admin Display</h3>
      <label class="mr-2 text-gray-700 dark:text-gray-300">Display names as:</label>
      <select
        :value="store.displayFormat"
        @change="store.setDisplayFormat(($event.target as HTMLSelectElement).value)"
        class="border border-gray-300 dark:border-gray-600 rounded p-1 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
      >
        <option value="prefix">Prefixed name</option>
        <option value="label">Label</option>
        <option value="iri">IRI</option>
      </select>
    </div>

    <!-- Label subproperties -->
    <div class="mb-6">
      <h3 class="text-lg font-semibold mb-2 text-gray-900 dark:text-gray-100">Label Properties</h3>
      <p class="text-sm text-gray-600 dark:text-gray-400 mb-3">
        Subproperties of <code>rdfs:label</code> detected in imported ontologies.
        Uncheck any property you want to exclude from display.
        Deepest subproperty is preferred when available.
      </p>

      <div v-if="loadingLabels" class="text-gray-500 dark:text-gray-400">Loading label properties…</div>
      <div v-else-if="labelError" class="text-red-600 dark:text-red-400">{{ labelError }}</div>
      <div v-else class="space-y-2">
        <label
          v-for="prop in labelProperties"
          :key="prop.uri"
          class="flex items-center gap-2 cursor-pointer text-gray-700 dark:text-gray-300"
        >
          <input
            type="checkbox"
            :checked="!prop.excluded"
            @change="toggleLabelProperty(prop.uri, !prop.excluded)"
            class="h-4 w-4"
          />
          <span class="text-sm">{{ prop.uri }}</span>
        </label>
        <p v-if="labelProperties.length === 0" class="text-gray-500 dark:text-gray-400">
          No label subproperties found in imported ontologies.
        </p>
      </div>
    </div>

    <!-- Public display options -->
    <div class="mb-6">
      <h3 class="text-lg font-semibold mb-2 text-gray-900 dark:text-gray-100">Public Display</h3>
      <label class="flex items-center gap-2 cursor-pointer text-gray-700 dark:text-gray-300">
        <input
          type="checkbox"
          :checked="store.publicShowBlankNodes"
          @change="toggleBlankNodes"
          class="h-4 w-4"
        />
        <span class="text-sm">Display blank nodes as instances (not recommended)</span>
      </label>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import { useToast } from '@/composables/useToast'

const store = useAppStore()
const apiBase = useRuntimeConfig().public.apiBase
const toast = useToast()

// ---------- theme ----------
const themeMode = ref<'light' | 'dark' | 'system'>('system')

// Apply the theme and save to localStorage
function applyTheme() {
  const root = document.documentElement
  const isDark =
    themeMode.value === 'dark' ||
    (themeMode.value === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  root.classList.toggle('dark', isDark)
  localStorage.setItem('theme', themeMode.value)
}

// Listen for system preference changes
if (process.client) {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (themeMode.value === 'system') {
      applyTheme()
    }
  })
}

// Load saved theme on mount
onMounted(() => {
  const saved = localStorage.getItem('theme')
  if (saved === 'light' || saved === 'dark' || saved === 'system') {
    themeMode.value = saved
  }
  applyTheme()
})

// ---------- label properties ----------
interface LabelProp {
  uri: string
  excluded: boolean
}

const labelProperties = ref<LabelProp[]>([])
const loadingLabels = ref(true)
const labelError = ref('')

onMounted(async () => {
  try {
    const res = await $fetch<{ available: string[]; excluded: string[] }>(
      `${apiBase}/api/preferences/label-properties`
    )
    const excluded = new Set(res.excluded)
    labelProperties.value = res.available.map((uri) => ({
      uri,
      excluded: excluded.has(uri),
    }))
  } catch (e: any) {
    labelError.value = e.message || 'Failed to load label properties'
  } finally {
    loadingLabels.value = false
  }
})

async function toggleLabelProperty(uri: string, exclude: boolean) {
  try {
    await $fetch(`${apiBase}/api/preferences/label-properties/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uri, exclude }),
    })
    const prop = labelProperties.value.find((p) => p.uri === uri)
    if (prop) prop.excluded = exclude
  } catch (e: any) {
    toast.error('Failed to update: ' + (e.message || e))
  }
}

async function toggleBlankNodes(e: Event) {
  const checked = (e.target as HTMLInputElement).checked
  await store.setPublicBlankNodesDisplay(checked)
}
</script>