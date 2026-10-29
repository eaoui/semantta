<template>
  <div>
    <!-- Back button -->
    <div class="flex items-center">
      <button @click="navigateTo(`/admin/profile?tab=${entityType || ''}`)"
        class="text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 pr-2"
        title="Back to Application Profile">
        <PhosphorIcon name="arrow-left" :ize="24" />
      </button>
      <h2 class="text-2xl font-bold text-gray-900 dark:text-gray-100">
        Edit Constraints – {{ entityDisplayLabel }}
      </h2>
    </div>

    <div v-if="loading" class="text-gray-500 dark:text-gray-400">Loading…</div>
    <div v-else-if="error" class="text-red-600 dark:text-red-400">{{ error }}</div>

    <form v-else @submit.prevent="save">
      <!-- Save button -->
      <div class="my-6">
        <button type="submit" :disabled="!hasChanges" class="px-4 py-2 rounded text-white"
          :class="hasChanges ? 'bg-blue-600 hover:bg-blue-700' : 'bg-gray-400 cursor-not-allowed'">
          Save Constraints
        </button>
        <p v-if="!hasChanges" class="text-sm text-gray-500 dark:text-gray-400 mt-1">No changes to save.</p>
      </div>

      <div class="flex gap-6">
        <!-- Left column -->
        <div class="flex-1 space-y-4">
          <div v-for="(config, pred) in leftConstraints" :key="pred"
            class="p-3 rounded border bg-white dark:bg-gray-800"
            :class="isDefault(pred) ? 'border-gray-300 dark:border-gray-600' : 'border-blue-500 dark:border-blue-400'">
            <div class="flex items-center gap-2 mb-1">
              <label class="font-medium text-gray-900 dark:text-gray-100">{{ config.label }}</label>
              <button v-if="!isDefault(pred)" type="button" @click="restoreDefault(pred)"
                class="text-gray-400 dark:text-gray-500 hover:text-blue-600 dark:hover:text-blue-400"
                title="Restore default values">
                <PhosphorIcon name="arrow-counter-clockwise" size="14" />
              </button>
            </div>

            <!-- Datatype picker -->
            <template v-if="config.type === 'datatype'">
              <EntitySelector entityType="datatype" :modelValue="formData[pred] || []"
                @update:modelValue="(val: string[]) => setFieldValue(pred, val)" placeholder="Search datatypes…" />
            </template>

            <!-- Class list -->
            <template v-else-if="config.type === 'class'">
              <EntitySelector entityType="class" :modelValue="formData[pred] || []"
                @update:modelValue="(val: string[]) => setFieldValue(pred, val)" placeholder="Search classes…" />
            </template>

            <!-- Property list -->
            <template v-else-if="config.type === 'property'">
              <EntitySelector entityType="property" :modelValue="formData[pred] || []"
                @update:modelValue="(val: string[]) => setFieldValue(pred, val)" placeholder="Search properties…" />
            </template>

            <!-- Dropdown -->
            <template v-else-if="config.type === 'dropdown'">
              <select v-model="formData[pred]" @change="markOverride(pred)" @input="markOverride(pred)"
                class="border border-gray-300 dark:border-gray-600 p-2 rounded w-full bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100">
                <option v-for="opt in config.options" :key="opt" :value="opt">{{ opt }}</option>
              </select>
            </template>

            <!-- Default text input -->
            <template v-else>
              <input v-model="formData[pred]" type="text" @input="markOverride(pred)"
                class="border border-gray-300 dark:border-gray-600 p-2 rounded w-full bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100" />
            </template>
          </div>
        </div>

        <!-- Right column (numeric fields) -->
        <div v-if="hasRightColumn" class="w-64 shrink-0 space-y-4">
          <div v-for="(config, pred) in rightConstraints" :key="pred"
            class="p-3 rounded border bg-white dark:bg-gray-800"
            :class="isDefault(pred) ? 'border-gray-300 dark:border-gray-600' : 'border-blue-500 dark:border-blue-400'">
            <div class="flex items-center gap-2 mb-1">
              <label class="font-medium text-gray-900 dark:text-gray-100">{{ config.label }}</label>
              <button v-if="!isDefault(pred)" type="button" @click="restoreDefault(pred)"
                class="text-gray-400 dark:text-gray-500 hover:text-blue-600 dark:hover:text-blue-400"
                title="Restore default values">
                <PhosphorIcon name="arrow-counter-clockwise" size="14" />
              </button>
            </div>
            <input v-model.number="formData[pred]" type="number" min="0" step="1" @input="markOverride(pred)"
              class="border border-gray-300 dark:border-gray-600 p-2 rounded w-full bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100" />
          </div>
        </div>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDisplay } from '@/composables/useDisplay'
import { useAppStore } from '@/stores/app'
import { constraintConfig } from '~/utils/constraintConfig'
import EntitySelector from '@/components/admin/EntitySelector.vue'
import { useToast } from '@/composables/useToast'

const route = useRoute()
const store = useAppStore()
const router = useRouter()
const { formatUri } = useDisplay()
const apiBase = useRuntimeConfig().public.apiBase
const toast = useToast()

const entityUri = ref('')
const entityType = ref('')
const entityDisplayLabel = computed(() => {
  const uri = entityUri.value
  const entity = store.profileEntities.find(item => item.uri === uri)

  if (store.displayFormat === 'label') {
    return entity?.label || formatUri(uri, 'label') || uri
  }

  return formatUri(uri) || uri
})
const original = ref<Record<string, string[]>>({})
const overrides = ref<Record<string, string>>({})
const loading = ref(true)
const error = ref('')

const formData = reactive<Record<string, any>>({})
const savedFormData = ref<Record<string, any>>({})

type ProfileFieldMode = 'default' | 'override'

const fieldModes = reactive<Record<string, ProfileFieldMode>>({})
const savedFieldModes = ref<Record<string, ProfileFieldMode>>({})

const relevantConstraints = computed(() => {
  const result: Record<string, any> = {}
  for (const pred in constraintConfig) {
    const config = constraintConfig[pred]
    if (config && config.appliesTo.includes(entityType.value)) {
      result[pred] = config
    }
  }
  return result
})

const leftConstraints = computed(() => {
  const result: Record<string, any> = {}
  for (const pred in relevantConstraints.value) {
    if (!['boolean', 'integer', 'number'].includes(relevantConstraints.value[pred].type)) {
      result[pred] = relevantConstraints.value[pred]
    }
  }
  return result
})

const rightConstraints = computed(() => {
  const result: Record<string, any> = {}
  for (const pred in relevantConstraints.value) {
    if (['integer', 'number'].includes(relevantConstraints.value[pred].type)) {
      result[pred] = relevantConstraints.value[pred]
    }
  }
  return result
})

const hasRightColumn = computed(() => Object.keys(rightConstraints.value).length > 0)

function getDefaultValue(pred: string): any {
  const config = constraintConfig[pred]
  if (!config) return undefined
  const orig = original.value[pred]

  if (orig !== undefined) {
    if (['class', 'property', 'datatype'].includes(config.type)) {
      return Array.isArray(orig) ? [...orig] : (orig ? [orig] : [])
    }
    if (config.type === 'boolean') {
      return Array.isArray(orig) ? orig.includes('true') : orig === 'true'
    }
    return Array.isArray(orig) ? (orig[0] != null ? String(orig[0]) : '') : (orig != null ? String(orig) : '')
  }

  if (['class', 'property', 'datatype'].includes(config.type)) return []
  if (config.type === 'boolean') return false
  if (config.type === 'integer' || config.type === 'number') return null
  return ''
}

function valuesAreEqual(a: any, b: any, type: string): boolean {
  if (['class', 'property', 'datatype'].includes(type)) {
    const arrA: string[] = Array.isArray(a) ? a : (a ? [a] : [])
    const arrB: string[] = Array.isArray(b) ? b : (b ? [b] : [])
    if (arrA.length !== arrB.length) return false
    const sortedA = [...arrA].sort()
    const sortedB = [...arrB].sort()
    return sortedA.every((v, i) => v === sortedB[i])
  }
  if (type === 'boolean') return a === b
  if (type === 'integer' || type === 'number') {
    const numA = (a != null && a !== '') ? Number(a) : null
    const numB = (b != null && b !== '') ? Number(b) : null
    return numA === numB
  }
  return a === b
}

const isDefault = (pred: string) =>
  (fieldModes[pred] ?? 'default') === 'default'

const hasChanges = computed(() => {
  for (const pred in relevantConstraints.value) {
    const config = constraintConfig[pred]
    if (!config) continue

    const current = formData[pred]
    const baseline = savedFormData.value[pred]
    const currentMode = fieldModes[pred] ?? 'default'
    const savedMode = savedFieldModes.value[pred] ?? 'default'

    if (currentMode !== savedMode) return true
    if (!valuesAreEqual(current, baseline, config.type)) return true
  }
  return false
})

function snapshotFormData() {
  const snap: Record<string, any> = {}

  for (const pred in relevantConstraints.value) {
    const val = formData[pred]
    snap[pred] = Array.isArray(val) ? [...val] : val
  }

  savedFormData.value = snap

  const modeSnapshot: Record<string, ProfileFieldMode> = {}

  for (const pred in relevantConstraints.value) {
    modeSnapshot[pred] = fieldModes[pred] ?? 'default'
  }

  savedFieldModes.value = modeSnapshot
}

async function restoreDefault(pred: string) {
  try {
    const latest = await $fetch<any>(
      `${apiBase}/api/profile/constraints/${encodeURIComponent(entityUri.value)}`,
    )

    const latestOriginal = latest.original || {}
    const nextOriginal = { ...original.value }

    if (Object.prototype.hasOwnProperty.call(latestOriginal, pred)) {
      nextOriginal[pred] = latestOriginal[pred]
    } else {
      delete nextOriginal[pred]
    }

    original.value = nextOriginal

    const defaultValue = getDefaultValue(pred)

    formData[pred] = Array.isArray(defaultValue)
      ? [...defaultValue]
      : defaultValue

    fieldModes[pred] = 'default'
  } catch (e: any) {
    toast.error(
      e?.data?.detail || e.message || 'Failed to restore default values',
    )
  }
}

function setFieldValue(pred: string, value: any) {
  formData[pred] = value
  fieldModes[pred] = 'override'
}

function markOverride(pred: string) {
  fieldModes[pred] = 'override'
}

onMounted(() => {
  const rawUri = route.query.uri
  if (!rawUri || typeof rawUri !== 'string') {
    router.replace('/admin/profile')
    return
  }
  entityUri.value = decodeURIComponent(rawUri)
  fetchConstraints()
})

async function fetchConstraints() {
  try {
    const res = await $fetch<any>(`${apiBase}/api/profile/constraints/${encodeURIComponent(entityUri.value)}`)
    entityType.value = res.type
    original.value = res.original || {}
    overrides.value = res.overrides || {}

    for (const pred of Object.keys(fieldModes)) {
      delete fieldModes[pred]
    }

    const receivedModes = res.field_modes || {}

    for (const pred in relevantConstraints.value) {
      fieldModes[pred] =
        receivedModes[pred] === 'override'
          ? 'override'
          : 'default'
    }

    for (const pred in relevantConstraints.value) {
      const config = relevantConstraints.value[pred]
      if (config.type === 'boolean') {
        formData[pred] = false
      } else if (config.type === 'integer' || config.type === 'number') {
        formData[pred] = null
      } else if (['class', 'property', 'datatype'].includes(config.type)) {
        formData[pred] = []
      } else {
        formData[pred] = ''
      }
    }

    for (const pred in original.value) {
      const config = constraintConfig[pred]
      if (!config) continue
      let vals = original.value[pred] ?? []
      if (['class', 'property', 'datatype'].includes(config.type) && !Array.isArray(vals)) {
        vals = [vals]
      }
      if (config.type === 'boolean') {
        formData[pred] = vals.includes('true')
      } else if (['class', 'property', 'datatype'].includes(config.type)) {
        formData[pred] = vals
      } else {
        formData[pred] = vals[0] || ''
      }
    }

    for (const pred in overrides.value) {
      if (fieldModes[pred] !== 'override') continue
      const config = constraintConfig[pred]
      if (!config) continue
      if (config.type === 'boolean') {
        formData[pred] = overrides.value[pred] === 'true'
      } else if (['class', 'property', 'datatype'].includes(config.type)) {
        const raw = overrides.value[pred]
        formData[pred] = Array.isArray(raw) ? raw : (raw ? [raw.trim()] : [])
      } else if (config.type === 'integer' || config.type === 'number') {
        formData[pred] = Number(overrides.value[pred])
      } else {
        formData[pred] = overrides.value[pred]
      }
    }

    // An explicitly empty override has state but may have no SHACL value.
    for (const pred in relevantConstraints.value) {
      if (
        fieldModes[pred] !== 'override' ||
        Object.prototype.hasOwnProperty.call(overrides.value, pred)
      ) {
        continue
      }

      const config = constraintConfig[pred]
      if (!config) continue

      if (['class', 'property', 'datatype'].includes(config.type)) {
        formData[pred] = []
      } else if (config.type === 'boolean') {
        formData[pred] = false
      } else if (
        config.type === 'integer' ||
        config.type === 'number'
      ) {
        formData[pred] = null
      } else {
        formData[pred] = ''
      }
    }

    snapshotFormData()
  } catch (e: any) {
    error.value = e.message || 'Failed to load constraints'
  } finally {
    loading.value = false
  }
}


async function save() {
  const payload: Record<string, any> = {}
  const fieldModesPayload: Record<string, ProfileFieldMode> = {}

  for (const pred in relevantConstraints.value) {
    const mode = fieldModes[pred] ?? 'default'
    fieldModesPayload[pred] = mode

    const isRelationshipField =
      pred === 'urn:domainClasses' ||
      pred === 'http://www.w3.org/ns/shacl#property'

    const value = mode === 'default'
      ? getDefaultValue(pred)
      : formData[pred]

    const isEmptyDefault =
      value == null ||
      value === '' ||
      (Array.isArray(value) && value.length === 0)

    // Do not turn an empty default into a stored empty SHACL constraint.
    // Empty relationship lists must still be submitted to synchronize links.
    if (
      mode === 'default' &&
      !isRelationshipField &&
      isEmptyDefault
    ) {
      continue
    }

    const config = constraintConfig[pred]
    if (!config) continue

    if (config.type === 'boolean') {
      const val = value
      if (val === true || val === 'true') {
        payload[pred] = 'true'
      }
    } else if (
      ['class', 'property', 'datatype'].includes(config.type)
    ) {
      const raw = value
      const arr = (
        Array.isArray(raw)
          ? raw
          : raw == null || raw === ''
            ? []
            : [raw]
      )
        .map(String)
        .filter(value => value.trim() !== '')

      if (config.multiple) {
        // An empty list is meaningful: it clears existing links
        // or removes a multi-valued constraint.
        payload[pred] = arr
      } else if (arr.length > 0) {
        payload[pred] = arr[0]
      } else if (mode === 'override') {
        payload[pred] = []
      }
    } else if (
      config.type === 'integer' ||
      config.type === 'number'
    ) {
      const val = formData[pred]
      if (val !== '' && val != null) {
        payload[pred] = val
      }
    } else {
      const val = formData[pred]
      if (val !== '' && val != null) {
        payload[pred] = String(val)
      }
    }
  }

  payload['__field_modes__'] = fieldModesPayload

  try {
    await $fetch(
      `${apiBase}/api/profile/constraints/${encodeURIComponent(entityUri.value)}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    )

    // Refresh shared Application Profile state without reloading the page.
    await store.fetchState()

    snapshotFormData()
    toast.success('Constraints saved')
  } catch (e: any) {
    toast.error(e?.data?.detail || e.message || 'Failed to save constraints')
  }
}

</script>