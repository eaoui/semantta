<template>
  <div>
    <!-- Back button -->
    <div class="flex items-center">
      <button @click="navigateTo(`/admin/profile?tab=${entityType || ''}`)"
        class="text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 pr-2"
        title="Back to Application Profile">
        <PhosphorIcon name="arrow-left" :ize="24" />
      </button>
      <h2 class="text-2xl font-bold text-gray-900 dark:text-gray-100">Edit Constraints – {{ formatUri(entityUri) }}</h2>
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
                @update:modelValue="(val: string[]) => formData[pred] = val" placeholder="Search datatypes…" />
            </template>

            <!-- Class list -->
            <template v-else-if="config.type === 'class'">
              <EntitySelector entityType="class" :modelValue="formData[pred] || []"
                @update:modelValue="(val: string[]) => formData[pred] = val" placeholder="Search classes…" />
            </template>

            <!-- Property list -->
            <template v-else-if="config.type === 'property'">
              <EntitySelector entityType="property" :modelValue="formData[pred] || []"
                @update:modelValue="(val: string[]) => formData[pred] = val" placeholder="Search properties…" />
            </template>

            <!-- Dropdown -->
            <template v-else-if="config.type === 'dropdown'">
              <select v-model="formData[pred]"
                class="border border-gray-300 dark:border-gray-600 p-2 rounded w-full bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100">
                <option v-for="opt in config.options" :key="opt" :value="opt">{{ opt }}</option>
              </select>
            </template>

            <!-- Default text input -->
            <template v-else>
              <input v-model="formData[pred]" type="text"
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
            <input v-model.number="formData[pred]" type="number" min="0" step="1"
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
import { constraintConfig } from '~/utils/constraintConfig'
import EntitySelector from '@/components/admin/EntitySelector.vue'
import { useToast } from '@/composables/useToast'

const route = useRoute()
const router = useRouter()
const { formatUri } = useDisplay()
const apiBase = useRuntimeConfig().public.apiBase
const toast = useToast()

const entityUri = ref('')
const entityType = ref('')
const original = ref<Record<string, string[]>>({})
const overrides = ref<Record<string, string>>({})
const loading = ref(true)
const error = ref('')

const formData = reactive<Record<string, any>>({})
const savedFormData = ref<Record<string, any>>({})

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

const isDefault = (pred: string) => {
  const config = constraintConfig[pred]
  if (!config) return true
  return valuesAreEqual(formData[pred], getDefaultValue(pred), config.type)
}

const hasChanges = computed(() => {
  for (const pred in relevantConstraints.value) {
    const config = constraintConfig[pred]
    if (!config) continue
    const current = formData[pred]
    const baseline = savedFormData.value[pred]
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
}

function restoreDefault(pred: string) {
  const defaultValue = getDefaultValue(pred)
  formData[pred] = Array.isArray(defaultValue) ? [...defaultValue] : defaultValue
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

    snapshotFormData()
  } catch (e: any) {
    error.value = e.message || 'Failed to load constraints'
  } finally {
    loading.value = false
  }
}

async function save() {
  const payload: Record<string, any> = {}
  for (const pred in relevantConstraints.value) {
    const config = constraintConfig[pred]
    if (!config) continue

    if (config.type === 'boolean') {
      const val = formData[pred]
      if (val === true || val === 'true') payload[pred] = 'true'
    } else if (['class', 'property', 'datatype'].includes(config.type)) {
      const arr = formData[pred] as string[]
      if (arr && arr.length) {
        if (pred === 'http://www.w3.org/ns/shacl#datatype' || pred === 'http://www.w3.org/ns/shacl#class') {
          payload[pred] = arr[0]
        } else {
          payload[pred] = arr
        }
      }
    } else if (config.type === 'integer' || config.type === 'number') {
      const val = formData[pred]
      if (val !== '' && val != null) payload[pred] = val
    } else {
      const val = formData[pred]
      if (val !== '' && val != null) payload[pred] = String(val)
    }
  }

  try {
    await $fetch(`${apiBase}/api/profile/constraints/${encodeURIComponent(entityUri.value)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    toast.success('Constraints saved')
    snapshotFormData()
  } catch (e: any) {
    toast.error(e?.data?.detail || e.message)
  }
}
</script>