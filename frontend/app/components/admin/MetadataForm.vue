<template>
  <div>
    <div class="flex">
      <button @click="navigateTo('/admin/metadata/instances')"
        class="mb-4 inline-flex items-center text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 pr-4"
        title="Back to Instances">
        <PhosphorIcon name="arrow-left" size="24" />
      </button>
      <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-gray-100">{{ mode === 'create' ? 'Create Metadata' :
        'Edit Metadata' }}</h2>
    </div>

    <!-- Instance URI -->
    <div class="mb-4">
      <label class="block mb-1 text-gray-700 dark:text-gray-300">Instance URI</label>
      <input :value="instanceUri" disabled
        class="border border-gray-300 dark:border-gray-600 p-2 rounded w-full bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400" />
    </div>

    <!-- Classes selection -->
    <div class="mb-4">
      <label class="block mb-1 text-gray-700 dark:text-gray-300">Classes</label>
      <EntitySelector v-model="selectedClasses" :availableClasses="classes" @change="onClassSelectionChange"
        placeholder="Search classes…" />
      <p v-if="selectedClasses.length === 0" class="text-red-500 dark:text-red-400 text-sm mt-1">
        Please select at least one class.
      </p>
    </div>

    <!-- Loading / message -->
    <div v-if="loadingProps" class="text-gray-500 dark:text-gray-400">Loading properties…</div>
    <div v-else-if="properties.length === 0 && selectedClasses.length"
      class="text-yellow-600 dark:text-yellow-400 mt-2">
      No active properties for the selected class(es). Enable them in the
      <NuxtLink to="/admin/profile" class="underline">Application Profile</NuxtLink>.
    </div>

    <!-- Dynamic form -->
    <form v-if="properties.length" @submit.prevent="handleSubmit">
      <div v-for="prop in properties" :key="prop.uri"
        class="mb-4 p-3 border border-gray-300 dark:border-gray-600 rounded">
        <label :for="'prop-' + prop.uri" class="block mb-1 font-medium text-gray-900 dark:text-gray-100">
          {{ getPropDisplayLabel(prop) }}
        </label>

        <div v-for="(value, index) in getPropValues(prop.uri)" :key="index" class="flex gap-2 mb-2 items-center">
          <!-- Datatype property -->
          <template v-if="prop.type === 'datatype'">
            <input v-model="getPropValues(prop.uri)[index]" :type="inputType(prop.datatype)"
              :step="inputType(prop.datatype) === 'number' ? 'any' : undefined"
              class="border border-gray-300 dark:border-gray-600 p-2 rounded flex-1 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              @input="validateField(prop.uri)" />
          </template>

          <!-- Object property (with suggestions) -->
          <template v-else>
            <div class="relative flex-1">
              <input v-model="getPropValues(prop.uri)[index]"
                @input="filterSuggestions(prop.uri, index, ($event.target as HTMLInputElement).value); validateField(prop.uri)"
                @focus="openSuggestion(prop.uri, index)" @blur="hideSuggestion(prop.uri, index)"
                class="border border-gray-300 dark:border-gray-600 p-2 rounded w-full bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                autocomplete="off" />
              <ul v-if="activeSuggestion === `${prop.uri}_${index}` && filteredSuggestions[prop.uri]?.length"
                class="absolute z-10 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded shadow max-h-40 overflow-auto w-full mt-1">
                <li v-for="sug in filteredSuggestions[prop.uri]" :key="sug.uri"
                  @mousedown.prevent="selectSuggestion(prop.uri, index, sug.uri)"
                  class="p-1 hover:bg-gray-100 dark:hover:bg-gray-600 cursor-pointer text-gray-900 dark:text-gray-100">
                  {{ sug.label }} ({{ sug.uri }})
                </li>
              </ul>
            </div>

            <button v-if="!getPropValues(prop.uri)[index]" type="button"
              @click="openCreatePanel(prop.uri, index, prop.ranges)"
              class="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300"
              title="Create new instance">
              <PhosphorIcon name="plus" size="16" />
            </button>
            <button v-if="getPropValues(prop.uri)[index]" type="button" @click="openEditPanel(prop.uri, index)"
              class="text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
              title="Edit linked instance">
              <PhosphorIcon name="pencil-simple" size="16" />
            </button>
          </template>

          <PhosphorIcon v-if="prop.allowMultiple && getPropValues(prop.uri).length > 1"
            @click="removeValue(prop.uri, index)" name="x" size="16"
            class="text-red-500 hover:text-red-700 cursor-pointer" />
        </div>

        <button v-if="prop.allowMultiple" @click="addValue(prop.uri)" type="button"
          class="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:underline text-sm mt-1">
          <PhosphorIcon name="list-plus" size="24" />
          Add value
        </button>

        <div v-if="validationErrors[prop.uri]" class="mt-1 text-sm text-red-600 dark:text-red-400">
          <span v-for="msg in validationErrors[prop.uri]" :key="msg" class="block">{{ msg }}</span>
        </div>
      </div>

      <button type="submit" :disabled="selectedClasses.length === 0"
        class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed">
        {{ mode === 'create' ? 'Create Instance' : 'Update Instance' }}
      </button>
    </form>

    <SlideOverPanel :show="panelState !== null" :level="(props.nestingLevel || 0)" @close="closePanel">
      <div v-if="panelState">
        <AdminMetadataForm :mode="panelState.mode" :nestingLevel="(props.nestingLevel || 0) + 1"
          :allowedClassUris="panelState.allowedClasses" :classUris="panelState.classUris"
          :initialInstanceUri="panelState.instanceUri" :initialProperties="panelState.existingProperties"
          @submit="onPanelSubmit" @cancel="closePanel" />
      </div>
    </SlideOverPanel>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import SlideOverPanel from '~/components/shared/SlideOverPanel.vue'
import EntitySelector from '~/components/admin/EntitySelector.vue'
import { useDisplay } from '@/composables/useDisplay'

const store = useAppStore()
const { formatUri } = useDisplay()
const apiBase = useRuntimeConfig().public.apiBase

interface ClassOption { uri: string; label: string }
interface PropDef {
  uri: string; label: string; type: string; datatype: string | null; ranges: string[];
  suggestions: { uri: string; label: string }[]; allowMultiple: boolean;
  constraints: Record<string, any>;
}

const props = defineProps<{
  mode: 'create' | 'edit'
  classUris?: string[]
  initialInstanceUri?: string
  initialProperties?: Record<string, string[]>
  allowedClassUris?: string[]
  nestingLevel?: number
}>()

const emit = defineEmits<{
  submit: [payload: { classUris: string[]; instanceUri: string; properties: Record<string, string[]> }]
  cancel: []
  'panel-state-changed': [open: boolean]
}>()

const classes = ref<ClassOption[]>([])
const availableClasses = computed(() => {
  if (props.allowedClassUris && props.allowedClassUris.length > 0) {
    return classes.value.filter(c => props.allowedClassUris!.includes(c.uri))
  }
  return classes.value
})

const selectedClasses = ref<string[]>(props.classUris || [])
const generatedUuid = ref(crypto.randomUUID())
const instanceUri = computed(() => {
  if (props.initialInstanceUri) return props.initialInstanceUri
  const base = store.baseIri || ''
  if (!base) return `urn:uuid:${generatedUuid.value}`
  return `${base.endsWith('/') ? base : base + '/'}${generatedUuid.value}`
})
const properties = ref<PropDef[]>([])
const loadingProps = ref(false)

const formData = reactive<Record<string, string[]>>({})
const activeSuggestion = ref<string | null>(null)
const filteredSuggestions = reactive<Record<string, any[]>>({})

interface PanelState {
  propUri: string
  index: number
  mode: 'create' | 'edit'
  instanceUri?: string
  allowedClasses?: string[]
  classUris?: string[]
  existingProperties?: Record<string, string[]>
}
const panelState = ref<PanelState | null>(null)

function getPropDisplayLabel(prop: PropDef): string {
  // In 'label' mode, use the ontology label (from backend); otherwise, format the URI
  if (store.displayFormat === 'label') return prop.label
  return formatUri(prop.uri)   // uses current store.displayFormat by default
}

function getPropValues(propUri: string): string[] {
  if (!formData[propUri]) {
    formData[propUri] = ['']
  }
  return formData[propUri]
}

const validationErrors = reactive<Record<string, string[]>>({})

function validateField(propUri: string) {
  const propDef = properties.value.find(p => p.uri === propUri)
  const values = getPropValues(propUri).filter(v => v.trim() !== '')
  const errors: string[] = []
  if (!propDef) return

  const constraints = propDef.constraints || {}
  if (!propDef.allowMultiple && values.length > 1) {
    errors.push('Only one value allowed.')
  }
  if (constraints.minCount != null && values.length < constraints.minCount) {
    errors.push(`At least ${constraints.minCount} value(s) required.`)
  }
  if (constraints.maxCount != null && values.length > constraints.maxCount) {
    errors.push(`At most ${constraints.maxCount} value(s) allowed.`)
  }

  for (const val of values) {
    if (propDef.type === 'datatype' && propDef.datatype) {
      const dt = propDef.datatype.toLowerCase()
      if (dt.includes('integer') && !/^-?\d+$/.test(val)) {
        errors.push('Must be an integer.')
        break
      }
      if ((dt.includes('decimal') || dt.includes('float') || dt.includes('double')) && isNaN(Number(val))) {
        errors.push('Must be a number.')
        break
      }
      if (dt.includes('date') && !/^\d{4}-\d{2}-\d{2}$/.test(val)) {
        errors.push('Must be a valid date (YYYY-MM-DD).')
        break
      }
    }

    if (constraints.pattern) {
      const flags = constraints.flags || ''
      const regex = new RegExp(constraints.pattern, flags)
      if (!regex.test(val)) {
        errors.push(`Value must match pattern: ${constraints.pattern}`)
        break
      }
    }
    if (constraints.minLength != null && val.length < constraints.minLength) {
      errors.push(`Minimum length is ${constraints.minLength}.`)
    }
    if (constraints.maxLength != null && val.length > constraints.maxLength) {
      errors.push(`Maximum length is ${constraints.maxLength}.`)
    }
    if (constraints.nodeKind) {
      const nk = constraints.nodeKind
      const isIRI = val.startsWith('http://') || val.startsWith('urn:')
      if (nk === 'http://www.w3.org/ns/shacl#IRI' && !isIRI) {
        errors.push('Value must be an IRI.')
      } else if (nk === 'http://www.w3.org/ns/shacl#Literal' && isIRI) {
        errors.push('Value must be a literal.')
      } else if (nk === 'http://www.w3.org/ns/shacl#BlankNode' && !val.startsWith('urn:bnid:')) {
        errors.push('Value must be a blank node.')
      }
    }
  }

  if (errors.length) {
    validationErrors[propUri] = errors
  } else {
    delete validationErrors[propUri]
  }
}

function validateAllFields(): boolean {
  for (const prop of properties.value) {
    validateField(prop.uri)
  }
  return Object.keys(validationErrors).length === 0
}

onMounted(async () => {
  try {
    const res = await $fetch<ClassOption[]>(`${apiBase}/api/create-form/classes`)
    classes.value = res
  } catch (e) {
    console.error('Failed to load classes', e)
  }
  if (props.mode === 'edit' && selectedClasses.value.length) {
    await fetchPropertiesForClasses()
    if (props.initialProperties) {
      for (const [pred, vals] of Object.entries(props.initialProperties)) {
        formData[pred] = Array.isArray(vals) ? [...vals] : [String(vals)]
      }
    }
    sortProperties()
  }
})

async function onClassSelectionChange() {
  await fetchPropertiesForClasses()
}

async function fetchPropertiesForClasses() {
  if (selectedClasses.value.length === 0) {
    properties.value = []
    return
  }
  loadingProps.value = true
  try {
    const allProps: PropDef[] = []
    for (const classUri of selectedClasses.value) {
      const data = await $fetch<{ class_uri: string; properties: PropDef[] }>(
        `${apiBase}/api/create-form/properties?class_uri=${encodeURIComponent(classUri)}`
      )
      allProps.push(...data.properties)
    }
    const unique = new Map<string, PropDef>()
    for (const p of allProps) {
      if (!unique.has(p.uri)) unique.set(p.uri, p)
    }
    properties.value = Array.from(unique.values())

    for (const prop of properties.value) {
      const arr = getPropValues(prop.uri)
      if (arr.length === 0) arr.push('')
      filteredSuggestions[prop.uri] = prop.suggestions || []
    }
    sortProperties()
  } catch (e) {
    console.error('Failed to load properties', e)
  } finally {
    loadingProps.value = false
  }
}

function inputType(datatype: string | null): string {
  if (!datatype) return 'text'
  const dt = datatype.toLowerCase()
  if (dt.includes('integer') || dt.includes('decimal') || dt.includes('float') || dt.includes('double'))
    return 'number'
  if (dt.includes('date') || dt.includes('time')) return 'date'
  if (dt.includes('boolean')) return 'checkbox'
  return 'text'
}

function addValue(propUri: string) {
  getPropValues(propUri).push('')
}

function removeValue(propUri: string, index: number) {
  getPropValues(propUri).splice(index, 1)
  validateField(propUri)
}

function openSuggestion(propUri: string, index: number) {
  activeSuggestion.value = `${propUri}_${index}`
}

function hideSuggestion(propUri: string, index: number) {
  setTimeout(() => {
    if (activeSuggestion.value === `${propUri}_${index}`) {
      activeSuggestion.value = null
    }
  }, 200)
}

function filterSuggestions(propUri: string, index: number, query: string) {
  const all = properties.value.find(p => p.uri === propUri)?.suggestions || []
  if (!query) {
    filteredSuggestions[propUri] = all
  } else {
    const q = query.toLowerCase()
    filteredSuggestions[propUri] = all.filter(s => s.label.toLowerCase().includes(q) || s.uri.toLowerCase().includes(q))
  }
  openSuggestion(propUri, index)
}

function selectSuggestion(propUri: string, index: number, uri: string) {
  getPropValues(propUri)[index] = uri
  activeSuggestion.value = null
  validateField(propUri)
}

function openCreatePanel(propUri: string, index: number, ranges: string[]) {
  let allowed: string[] = []
  if (ranges.length > 0) {
    allowed = ranges.filter(r => classes.value.some(c => c.uri === r))
  }
  panelState.value = {
    propUri,
    index,
    mode: 'create',
    allowedClasses: allowed.length > 0 ? allowed : undefined,
  }
}

async function openEditPanel(propUri: string, index: number) {
  const uri = getPropValues(propUri)[index]
  if (!uri) return
  try {
    const res = await $fetch<any>(`${apiBase}/api/instances/${encodeURIComponent(uri)}`)
    panelState.value = {
      propUri,
      index,
      mode: 'edit',
      instanceUri: uri,
      allowedClasses: undefined,
      classUris: res.types,
      existingProperties: res.properties as Record<string, string[]>,
    }
  } catch (e) {
    console.error('Failed to fetch instance', e)
  }
}

function closePanel() {
  panelState.value = null
}

async function onPanelSubmit(payload: { classUris: string[]; instanceUri: string; properties: Record<string, string[]> }) {
  if (!panelState.value) return
  const { propUri, index, mode } = panelState.value
  try {
    if (mode === 'create') {
      const res = await $fetch<{ uri: string }>(`${apiBase}/api/metadata/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          class_uris: payload.classUris,
          instance_uri: payload.instanceUri,
          properties: payload.properties,
        }),
      })
      getPropValues(propUri)[index] = res.uri
    } else {
      await $fetch(`${apiBase}/api/instances/${encodeURIComponent(payload.instanceUri)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          class_uris: payload.classUris,
          properties: payload.properties,
        }),
      })
      getPropValues(propUri)[index] = payload.instanceUri
    }
    closePanel()
    store.fetchState()
  } catch (e: any) {
    alert('Operation failed: ' + (e.message || e))
  }
}

function sortProperties() {
  properties.value.sort((a, b) => {
    const aFilled = getPropValues(a.uri).some(v => v.trim() !== '')
    const bFilled = getPropValues(b.uri).some(v => v.trim() !== '')
    if (aFilled && !bFilled) return -1
    if (!aFilled && bFilled) return 1
    return 0
  })
}

watch(() => panelState.value, (val) => {
  emit('panel-state-changed', val !== null)
})

watch(selectedClasses, () => {
  onClassSelectionChange()
}, { deep: true })

function handleSubmit() {
  const cleanProps: Record<string, string[]> = {}
  for (const pred of Object.keys(formData)) {
    const vals = getPropValues(pred).filter(v => v.trim() !== '')
    if (vals.length > 0) {
      cleanProps[pred] = vals
    }
  }
  if (!validateAllFields()) return
  emit('submit', {
    classUris: selectedClasses.value,
    instanceUri: instanceUri.value,
    properties: cleanProps,
  })
}
</script>