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

    <div :class="isRootForm
      ? 'grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_17rem]'
      : ''">
      <div class="min-w-0">
        <!-- Form-level summary for errors -->
        <div v-if="serverSummaryErrors.length"
          class="mb-4 rounded border border-red-500 bg-red-50 p-3 text-sm text-red-700 dark:border-red-500 dark:bg-red-950/30 dark:text-red-300"
          role="alert">
          <p v-for="(message, index) in serverSummaryErrors" :key="`${index}-${message}`">
            {{ message }}
          </p>
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
          <EntitySelector v-model="selectedClasses" :available-entities="availableClasses"
            :invalid="selectedClasses.length === 0 || classValidationErrors.length > 0" placeholder="Search classes…" />
          <p v-if="hasNoActiveRangeClasses" class="mt-2 text-sm text-amber-700 dark:text-amber-400">
            No active classes satisfy this property's Range Classes. Go to
            <NuxtLink to="/admin/profile" class="font-medium underline">
              Application Profile
            </NuxtLink>
            to either change this property's Range Classes or activate its existing range classes.
          </p>
          <p v-if="classValidationErrors.length" class="mt-1 text-sm text-red-600 dark:text-red-400">
            <span v-for="(message, index) in classValidationErrors" :key="`${index}-${message}`" class="block">
              {{ message }}
            </span>
          </p>
          <p v-else-if="selectedClasses.length === 0" class="mt-1 text-sm text-yellow-500 dark:text-yellow-400">
            Please select at least one class.
          </p>
        </div>

        <!-- Loading / message -->
        <div v-if="loadingProps" class="text-gray-500 dark:text-gray-400">
          Loading properties…
        </div>

        <div v-else-if="
          propertiesLoaded &&
          properties.length === 0 &&
          selectedClasses.length > 0
        " class="mt-2 text-yellow-600 dark:text-yellow-400">
          No active properties for the selected class(es). Enable them in the
          <NuxtLink to="/admin/profile" class="underline">
            Application Profile
          </NuxtLink>.
        </div>

        <!-- Dynamic form -->
        <form v-if="properties.length > 0 && !loadingProps" @submit.prevent="handleSubmit">
          <p v-if="propertySearch.trim() && visibleProperties.length === 0"
            class="mb-4 text-sm text-gray-500 dark:text-gray-400">
            No properties match "{{ propertySearch }}".
          </p>
          <div v-for="prop in visibleProperties" :key="prop.uri"
            class="mb-4 p-3 border border-gray-300 dark:border-gray-600 rounded" :class="hasFieldError(prop.uri)
              ? 'border-red-500! dark:border-red-500! ring-1 ring-red-500/30'
              : ''">
            <label :for="'prop-' + prop.uri" class="block mb-1 font-medium text-gray-900 dark:text-gray-100">
              {{ getPropDisplayLabel(prop) }}
            </label>

            <div v-for="(value, index) in getPropValues(prop.uri)" :key="index" class="flex gap-2 mb-2 items-center">
              <!-- Datatype property -->
              <template v-if="prop.type === 'datatype'">
                <select v-if="isBooleanDatatype(getPropDatatype(prop))"
                  :value="toLexicalString(getPropValues(prop.uri)[index])"
                  class="border border-gray-300 dark:border-gray-600 p-2 rounded flex-1 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                  :class="hasFieldError(prop.uri)
                    ? 'border-red-500! dark:border-red-500! ring-1 ring-red-500/30'
                    : ''" :aria-invalid="hasFieldError(prop.uri)" @change="setPropValue(
                      prop.uri,
                      index,
                      ($event.target as HTMLSelectElement).value
                    ); onPropertyInput(prop.uri)">
                  <option value="">Select a value</option>
                  <option value="true">True</option>
                  <option value="false">False</option>
                </select>

                <input v-else :value="toLexicalString(getPropValues(prop.uri)[index])"
                  :type="inputType(getPropDatatype(prop))"
                  :step="inputType(getPropDatatype(prop)) === 'number' ? 'any' : undefined"
                  class="border border-gray-300 dark:border-gray-600 p-2 rounded flex-1 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                  :class="hasFieldError(prop.uri)
                    ? 'border-red-500! dark:border-red-500! ring-1 ring-red-500/30'
                    : ''" :aria-invalid="hasFieldError(prop.uri)" @input="setPropValue(
                      prop.uri,
                      index,
                      ($event.target as HTMLInputElement).value
                    ); onPropertyInput(prop.uri)" />
              </template>


              <!-- Object property (with suggestions) -->
              <template v-else>
                <div class="relative flex-1">
                  <input v-model="getPropValues(prop.uri)[index]"
                    @input="filterSuggestions(prop.uri, index, ($event.target as HTMLInputElement).value); onPropertyInput(prop.uri)"
                    @focus="openSuggestion(prop.uri, index)" @blur="hideSuggestion(prop.uri, index)"
                    class="border border-gray-300 dark:border-gray-600 p-2 rounded w-full bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                    :class="hasFieldError(prop.uri)
                      ? 'border-red-500! dark:border-red-500! ring-1 ring-red-500/30'
                      : ''" :aria-invalid="hasFieldError(prop.uri)" autocomplete="off" />
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
                  <PhosphorIcon v-if="openingPanelActionKey === getPanelActionKey(prop.uri, index)" name="circle-notch"
                    size="16" class="animate-spin" aria-hidden="true" />
                  <PhosphorIcon v-else name="plus" size="16" aria-hidden="true" />
                </button>
                <button v-if="getPropValues(prop.uri)[index]" type="button" @click="openEditPanel(prop.uri, index)"
                  class="text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                  title="Edit linked instance">
                  <PhosphorIcon v-if="openingPanelActionKey === getPanelActionKey(prop.uri, index)" name="circle-notch"
                    size="16" class="animate-spin" aria-hidden="true" />
                  <PhosphorIcon v-else name="pencil-simple" size="16" aria-hidden="true" />
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

            <div v-if="getFieldMessages(prop.uri).length" class="mt-1 text-sm text-red-600 dark:text-red-400">
              <span v-for="(message, index) in getFieldMessages(prop.uri)" :key="`${index}-${message}`" class="block">
                {{ message }}
              </span>
            </div>
          </div>

          <button v-if="!isRootForm" type="submit" :disabled="selectedClasses.length === 0 || props.submitting"
            class="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50">
            {{ mode === 'create' ? 'Create Instance' : 'Update Instance' }}
          </button>
        </form>

      </div>

      <!-- Sidebar -->
      <aside v-if="isRootForm"
        class="w-full self-start space-y-4 rounded-lg border border-gray-300 bg-white p-4 dark:border-gray-600 dark:bg-gray-800 lg:sticky lg:top-4">
        <button type="submit" :form="formId" :disabled="selectedClasses.length === 0 ||
          properties.length === 0 ||
          loadingProps ||
          props.submitting
          "
          class="w-full rounded bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50">
          {{ mode === 'create' ? 'Create Instance' : 'Update Instance' }}
        </button>

        <button v-if="mode === 'edit'" type="button" :disabled="props.submitting" @click="emit('delete-request')"
          class="w-full rounded bg-red-600 px-4 py-2 font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50">
          <PhosphorIcon name="trash" size="16" class="mr-2 inline-block" aria-hidden="true" />
          Delete Instance
        </button>

        <div>
          <label class="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
            Filter properties
          </label>
          <SearchBox v-model="propertySearch" placeholder="Filter properties…" />
        </div>
      </aside>
    </div>

    <SlideOverPanel :show="panelState !== null" :level="(props.nestingLevel || 0)" @close="closePanel"
      @opened="onPanelOpened">
      <div v-if="panelState">
        <AdminMetadataForm :mode="panelState.mode" :nestingLevel="(props.nestingLevel || 0) + 1"
          :allowedClassUris="panelState.allowedClasses" :classUris="panelState.classUris"
          :initialInstanceUri="panelState.instanceUri" :initialProperties="panelState.existingProperties"
          :serverValidationError="panelServerValidationError" :submitting="!!panelLoadingMsg" @submit="onPanelSubmit"
          @cancel="closePanel" />
      </div>
    </SlideOverPanel>

    <LoadingOverlay :show="!!panelLoadingMsg" title="Loading" :message="panelLoadingMsg" />
  </div>
</template>

<script setup lang="ts">
import {
  ref,
  reactive,
  computed,
  watch,
  onMounted,
  onBeforeUnmount,
  nextTick,
} from 'vue'
import { useAppStore } from '@/stores/app'
import { useDisplay } from '@/composables/useDisplay'
import { useToast } from '@/composables/useToast'
import SlideOverPanel from '~/components/shared/SlideOverPanel.vue'
import EntitySelector from '~/components/admin/EntitySelector.vue'
import SearchBox from '@/components/shared/SearchBox.vue'
import LoadingOverlay from '@/components/shared/LoadingOverlay.vue'

const store = useAppStore()
const { formatUri } = useDisplay()
const apiBase = useRuntimeConfig().public.apiBase
const toast = useToast()

interface ClassOption {
  uri: string
  label: string
  superClasses?: string[]
}

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
  submitting?: boolean
  serverValidationError?: string | null
}>()

const formId = `metadata-form-${useId()}`

const isRootForm = computed(
  () => (props.nestingLevel ?? 0) === 0,
)

const propertySearch = ref('')

const emit = defineEmits<{
  submit: [payload: {
    classUris: string[]
    instanceUri: string
    properties: Record<string, string[]>
    editablePropertyUris: string[]
  }]
  cancel: []
  'panel-state-changed': [open: boolean]
  'delete-request': []
}>()

const classes = ref<ClassOption[]>([])
const availableClasses = computed(() => {
  if (props.allowedClassUris === undefined) {
    return classes.value
  }

  const allowed = new Set(props.allowedClassUris)

  return classes.value.filter(c => allowed.has(c.uri))
})
const hasNoActiveRangeClasses = computed(
  () =>
    props.allowedClassUris !== undefined &&
    props.allowedClassUris.length === 0,
)
const selectedClasses = ref<string[]>(props.classUris || [])
const isSingleMatchingRangeClass = computed(() =>
  props.mode === 'create' &&
  (props.nestingLevel ?? 0) > 0 &&
  props.allowedClassUris !== undefined &&
  availableClasses.value.length === 1
)

watch(
  [isSingleMatchingRangeClass, availableClasses],
  () => {
    if (!isSingleMatchingRangeClass.value) return

    const onlyClass = availableClasses.value[0]
    if (!onlyClass) return

    if (
      selectedClasses.value.length !== 1 ||
      selectedClasses.value[0] !== onlyClass.uri
    ) {
      selectedClasses.value = [onlyClass.uri]
    }
  },
  { immediate: true },
)

const generatedUuid = ref(crypto.randomUUID())
const instanceUri = computed(() => {
  if (props.initialInstanceUri) return props.initialInstanceUri
  const base = store.baseIri || ''
  if (!base) return `urn:uuid:${generatedUuid.value}`
  return `${base.endsWith('/') ? base : base + '/'}${generatedUuid.value}`
})
const properties = ref<PropDef[]>([])
const loadingProps = ref(selectedClasses.value.length > 0)
const propertiesLoaded = ref(false)

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

const panelLoadingMsg = ref('')

const openingPanelActionKey = ref<string | null>(null)

function getPanelActionKey(propUri: string, index: number): string {
  return `${propUri}_${index}`
}

async function waitForIndicatorPaint(): Promise<void> {
  await nextTick()

  // Allow the loading icon to render before opening the panel.
  await new Promise<void>((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => resolve())
    })
  })
}

function onPanelOpened(): void {
  openingPanelActionKey.value = null
}

function getPropDisplayLabel(prop: PropDef): string {
  // In 'label' mode, use the ontology label (from backend); otherwise, format the URI
  if (store.displayFormat === 'label') return prop.label
  return formatUri(prop.uri)   // uses current store.displayFormat by default
}

const visibleProperties = computed(() => {
  const query = propertySearch.value.trim().toLowerCase()

  if (!query) {
    return properties.value
  }

  return properties.value.filter(prop =>
    [
      getPropDisplayLabel(prop),
      prop.label,
      prop.uri,
    ].some(value => value.toLowerCase().includes(query)),
  )
})

function getPropValues(propUri: string): string[] {
  const existing = formData[propUri] as unknown[] | undefined

  if (!existing || existing.length === 0) {
    const values = ['']
    formData[propUri] = values
    return values
  }

  if (existing.some(value => typeof value !== 'string')) {
    const values = existing.map(toLexicalString)
    formData[propUri] = values
    return values
  }

  return existing as string[]
}

function toLexicalString(value: unknown): string {
  if (value == null) return ''

  if (
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean' ||
    typeof value === 'bigint'
  ) {
    return String(value)
  }

  return ''
}

function setPropValue(
  propUri: string,
  index: number,
  value: string,
): void {
  getPropValues(propUri)[index] = value
}

const validationErrors = reactive<Record<string, string[]>>({})
const serverFieldErrors = reactive<Record<string, string[]>>({})
const classValidationErrors = ref<string[]>([])
const serverSummaryErrors = ref<string[]>([])
const panelServerValidationError = ref<string | null>(null)

type LiveValidationStage = 'selection' | 'metadata'

const localToastSignatures = new Map<string, string>()
const liveValidationFailures: Record<LiveValidationStage, string | null> = {
  selection: null,
  metadata: null,
}

let liveValidationTimer: ReturnType<typeof setTimeout> | undefined
let liveValidationRevision = 0
let propertyFetchRevision = 0

function getErrorMessage(error: unknown, fallback: string): string {
  const e = error as {
    data?: { detail?: unknown }
    message?: unknown
  } | null

  const detail = e?.data?.detail

  if (typeof detail === 'string') return detail

  if (Array.isArray(detail)) {
    return detail
      .map(item => {
        if (item && typeof item === 'object' && 'msg' in item) {
          return String(item.msg)
        }
        return String(item)
      })
      .join('; ')
  }

  if (detail != null) return String(detail)
  if (typeof e?.message === 'string') return e.message

  return fallback
}

function addUniqueMessage(target: string[], message: string) {
  if (!target.includes(message)) {
    target.push(message)
  }
}

function getFieldMessages(propUri: string): string[] {
  return [
    ...new Set([
      ...(validationErrors[propUri] ?? []),
      ...(serverFieldErrors[propUri] ?? []),
    ]),
  ]
}

function hasFieldError(propUri: string): boolean {
  return getFieldMessages(propUri).length > 0
}

function clearServerValidationState() {
  for (const propUri of Object.keys(serverFieldErrors)) {
    delete serverFieldErrors[propUri]
  }

  classValidationErrors.value = []
  serverSummaryErrors.value = []
}

function applyServerValidationMessage(
  message: string,
  stage: 'selection' | 'metadata' = 'metadata',
) {
  // Separate messages using the prefixes established by commit 1.
  // The lookahead avoids splitting semicolons within a message.
  const normalized = message
    .replace(/^SHACL validation failed:\s*/i, '')
    .trim()

  const issues = normalized
    .split(
      /;\s+(?=(?:The value of property <|Property <|Validation issue:))/i,
    )
    .map(issue => issue.trim())
    .filter(Boolean)

  for (const issue of issues) {
    const propertyMatch = issue.match(
      /(?:The value of property|Property)\s+<([^>]+)>/i,
    )

    if (propertyMatch?.[1]) {
      const propUri = propertyMatch[1]

      if (properties.value.some(prop => prop.uri === propUri)) {
        const errors = serverFieldErrors[propUri] ?? []
        addUniqueMessage(errors, issue)
        serverFieldErrors[propUri] = errors
      } else {
        // The property is not represented by a current form field.
        addUniqueMessage(serverSummaryErrors.value, issue)
      }

      continue
    }

    // Retain compatibility with validation errors that predate the
    // property-path message format, such as profile-membership errors.
    const matchingProperty = properties.value.find(
      prop => issue.includes(prop.uri),
    )

    if (matchingProperty) {
      const errors = serverFieldErrors[matchingProperty.uri] ?? []
      addUniqueMessage(errors, issue)
      serverFieldErrors[matchingProperty.uri] = errors
    } else if (
      stage === 'selection' ||
      /\bclasses?\b|\bdisjoint\b/i.test(issue)
    ) {
      addUniqueMessage(classValidationErrors.value, issue)
    } else {
      addUniqueMessage(serverSummaryErrors.value, issue)
    }
  }
}

watch(
  () => props.serverValidationError,
  message => {
    if (message) {
      applyServerValidationMessage(message, 'metadata')
    }
  },
)

function getFieldErrors(propUri: string): string[] {
  const propDef = properties.value.find(p => p.uri === propUri)
  if (!propDef) return []

  const values = getPropValues(propUri)
    .map(toLexicalString)
    .filter(value => value.trim() !== '')
  const constraints = propDef.constraints || {}
  const errors: string[] = []

  if (!propDef.allowMultiple && values.length > 1) {
    errors.push('Only one value allowed.')
  }

  if (
    constraints.minCount != null &&
    values.length < constraints.minCount
  ) {
    errors.push(`At least ${constraints.minCount} value(s) required.`)
  }

  if (
    constraints.maxCount != null &&
    values.length > constraints.maxCount
  ) {
    errors.push(`At most ${constraints.maxCount} value(s) allowed.`)
  }

  const datatype = String(
    constraints.datatype || propDef.datatype || '',
  ).toLowerCase()

  let pattern: RegExp | null = null

  if (constraints.pattern) {
    try {
      pattern = new RegExp(
        constraints.pattern,
        constraints.flags || '',
      )
    } catch {
      errors.push(
        'The active Application Profile has an invalid pattern.',
      )
    }
  }

  if (
    constraints.hasValue != null &&
    constraints.hasValue !== '' &&
    !values.includes(String(constraints.hasValue))
  ) {
    errors.push(
      `The required value is ${constraints.hasValue}.`,
    )
  }

  for (const val of values) {
    if (propDef.type === 'datatype' && datatype) {
      const datatypeName = datatypeLocalName(datatype)
      if (numericDatatypeNames.has(datatypeName)) {
        if (
          ['integer', 'int', 'long', 'short', 'byte',
            'nonpositiveinteger', 'negativeinteger',
            'nonnegativeinteger', 'positiveinteger',
            'unsignedlong', 'unsignedint',
            'unsignedshort', 'unsignedbyte'].includes(datatypeName) &&
          !/^[+-]?\d+$/.test(val)
        ) {
          errors.push('Must be an integer.')
        } else if (
          datatypeName === 'decimal' &&
          !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(val)
        ) {
          errors.push('Must be a valid decimal.')
        } else if (
          ['float', 'double'].includes(datatypeName) &&
          !Number.isFinite(Number(val))
        ) {
          errors.push('Must be a valid number.')
        }
      } else if (
        (
          datatype.includes('decimal') ||
          datatype.includes('float') ||
          datatype.includes('double')
        ) &&
        (val.trim() === '' || !Number.isFinite(Number(val)))
      ) {
        errors.push('Must be a number.')
      } else if (
        datatype.endsWith('#boolean') &&
        !['true', 'false', '1', '0'].includes(val.toLowerCase())
      ) {
        errors.push('Must be a boolean.')
      } else if (
        datatype.endsWith('#date') &&
        !/^\d{4}-\d{2}-\d{2}$/.test(val)
      ) {
        errors.push('Must be a valid date (YYYY-MM-DD).')
      }
    }

    if (pattern && !pattern.test(val)) {
      errors.push(`Value must match pattern: ${constraints.pattern}`)
    }

    if (
      constraints.minLength != null &&
      val.length < constraints.minLength
    ) {
      errors.push(`Minimum length is ${constraints.minLength}.`)
    }

    if (
      constraints.maxLength != null &&
      val.length > constraints.maxLength
    ) {
      errors.push(`Maximum length is ${constraints.maxLength}.`)
    }

    if (constraints.nodeKind) {
      const isBlankNode = val.startsWith('urn:bnid:')
      const isIRI =
        /^[a-z][a-z0-9+.-]*:/i.test(val) && !isBlankNode

      if (
        constraints.nodeKind.endsWith('#IRI') &&
        !isIRI
      ) {
        errors.push('Value must be an IRI.')
      } else if (
        constraints.nodeKind.endsWith('#Literal') &&
        isIRI
      ) {
        errors.push('Value must be a literal.')
      } else if (
        constraints.nodeKind.endsWith('#BlankNode') &&
        !isBlankNode
      ) {
        errors.push('Value must be a blank node.')
      }
    }

    // Validate sh:in locally only when the API supplies actual
    // allowed values as an array. The backend remains authoritative.
    if (Array.isArray(constraints.in)) {
      const allowed = constraints.in.map(String)
      if (!allowed.includes(val)) {
        errors.push(
          `Value must be one of: ${allowed.join(', ')}.`,
        )
      }
    }
  }

  return [...new Set(errors)]
}

function validateField(
  propUri: string,
  notify = true,
): string[] {
  const propDef = properties.value.find(p => p.uri === propUri)
  if (!propDef) return []

  const errors = getFieldErrors(propUri)

  if (errors.length) {
    validationErrors[propUri] = errors

    const signature = JSON.stringify(errors)

    if (
      notify &&
      localToastSignatures.get(propUri) !== signature
    ) {
      toast.error(
        `${getPropDisplayLabel(propDef)}: ${errors.join(' ')}`,
      )
    }

    localToastSignatures.set(propUri, signature)
  } else {
    delete validationErrors[propUri]
    localToastSignatures.delete(propUri)
  }

  return errors
}

function validateAllFields(): boolean {
  const issues: { label: string; errors: string[] }[] = []

  for (const prop of properties.value) {
    const errors = validateField(prop.uri, false)

    if (errors.length) {
      issues.push({
        label: getPropDisplayLabel(prop),
        errors,
      })
    }
  }

  if (issues.length) {
    const summary = issues
      .slice(0, 4)
      .map(issue => `${issue.label}: ${issue.errors.join(' ')}`)

    const remaining = issues.length - summary.length

    toast.error(
      `Please correct the metadata validation errors. ${summary.join(' | ')
      }${remaining > 0 ? ` | And ${remaining} more field(s).` : ''
      }`,
    )

    return false
  }

  return true
}

function collectCleanProperties(): Record<string, string[]> {
  const result: Record<string, string[]> = {}

  for (const prop of properties.value) {
    const values = getPropValues(prop.uri)
      .map(toLexicalString)
      .filter(value => value.trim() !== '')

    if (values.length) {
      result[prop.uri] = values
    }
  }

  return result
}

function cancelScheduledLiveValidation() {
  if (liveValidationTimer !== undefined) {
    clearTimeout(liveValidationTimer)
    liveValidationTimer = undefined
  }

  // Ignore responses from requests initiated before cancellation.
  liveValidationRevision++
}

function scheduleLiveValidation(stage: LiveValidationStage) {
  if (liveValidationTimer !== undefined) {
    clearTimeout(liveValidationTimer)
    liveValidationTimer = undefined
  }

  const revision = ++liveValidationRevision

  if (!selectedClasses.value.length) {
    liveValidationFailures.selection = null
    liveValidationFailures.metadata = null
    return
  }

  // Avoid server requests for incomplete or locally invalid drafts.
  // Those errors are already handled immediately by validateField().
  if (
    stage === 'metadata' &&
    properties.value.some(prop => getFieldErrors(prop.uri).length > 0)
  ) {
    return
  }

  liveValidationTimer = setTimeout(() => {
    liveValidationTimer = undefined
    void runLiveValidation(stage, revision)
  }, 650)
}

async function runLiveValidation(
  stage: LiveValidationStage,
  revision: number,
) {
  if (revision !== liveValidationRevision) return
  if (!selectedClasses.value.length) return

  if (
    stage === 'metadata' &&
    properties.value.some(prop => getFieldErrors(prop.uri).length > 0)
  ) {
    return
  }

  try {
    await $fetch<{ valid: boolean }>(
      `${apiBase}/api/metadata/validate`,
      {
        method: 'POST',
        body: {
          class_uris: [...selectedClasses.value],
          properties: stage === 'metadata'
            ? collectCleanProperties()
            : {},
          stage,
        },
      },
    )

    if (revision !== liveValidationRevision) return

    // Show success only when this stage previously had an error.
    if (liveValidationFailures[stage]) {
      toast.success(
        stage === 'selection'
          ? 'Selected classes now satisfy profile and ontology checks.'
          : 'Metadata now satisfies the active profile and ontology.',
      )
    }

    if (stage === 'metadata') {
      clearServerValidationState()
    } else {
      classValidationErrors.value = []
    }

    liveValidationFailures[stage] = null
  } catch (error: unknown) {
    if (revision !== liveValidationRevision) return

    const message = getErrorMessage(
      error,
      'Metadata validation failed.',
    )

    applyServerValidationMessage(message, stage)

    // Deduplicate repeated errors while the same problem persists.
    if (liveValidationFailures[stage] !== message) {
      toast.error(
        `${stage === 'selection'
          ? 'Class selection validation'
          : 'Metadata validation'
        }: ${message}`,
      )
    }

    liveValidationFailures[stage] = message
  }
}

function onPropertyInput(propUri: string) {
  delete serverFieldErrors[propUri]
  serverSummaryErrors.value = []
  validateField(propUri)
  scheduleLiveValidation('metadata')
}

onBeforeUnmount(() => {
  cancelScheduledLiveValidation()
})

onMounted(async () => {
  try {
    const res = await $fetch<ClassOption[]>(`${apiBase}/api/create-form/classes`)
    classes.value = res
  } catch (error: unknown) {
    console.error('Failed to load classes', error)
    toast.error(
      getErrorMessage(error, 'Failed to load metadata classes.'),
    )
  }
  if (props.mode === 'edit' && selectedClasses.value.length) {
    await fetchPropertiesForClasses()
    if (props.initialProperties) {
      for (const [pred, rawValues] of Object.entries(props.initialProperties)) {
        const values = Array.isArray(rawValues)
          ? rawValues
          : [rawValues]

        formData[pred] = values.map(toLexicalString)
      }
    }
    sortProperties()

    if (validateAllFields()) {
      scheduleLiveValidation('metadata')
    }
  }
})

async function onClassSelectionChange() {
  await fetchPropertiesForClasses()
}

async function fetchPropertiesForClasses() {
  const revision = ++propertyFetchRevision
  const requestedClasses = [...selectedClasses.value]

  if (requestedClasses.length === 0) {
    loadingProps.value = false
    propertiesLoaded.value = false
    properties.value = []

    for (const propUri of Object.keys(validationErrors)) {
      delete validationErrors[propUri]
    }

    localToastSignatures.clear()
    scheduleLiveValidation('selection')
    return
  }

  loadingProps.value = true
  propertiesLoaded.value = false

  try {
    const responses = await Promise.all(
      requestedClasses.map(classUri =>
        $fetch<{ class_uri: string; properties: PropDef[] }>(
          `${apiBase}/api/create-form/properties?class_uri=${encodeURIComponent(classUri)}`
        )
      )
    )

    if (revision !== propertyFetchRevision) return

    const allProps = responses.flatMap(response => response.properties)

    const unique = new Map<string, PropDef>()
    for (const p of allProps) {
      if (!unique.has(p.uri)) unique.set(p.uri, p)
    }
    properties.value = Array.from(unique.values())
    propertiesLoaded.value = true

    const activePropertyUris = new Set(
      properties.value.map(prop => prop.uri),
    )

    for (const propUri of Object.keys(validationErrors)) {
      if (!activePropertyUris.has(propUri)) {
        delete validationErrors[propUri]
      }
    }

    for (const propUri of localToastSignatures.keys()) {
      if (!activePropertyUris.has(propUri)) {
        localToastSignatures.delete(propUri)
      }
    }

    for (const prop of properties.value) {
      const arr = getPropValues(prop.uri)
      if (arr.length === 0) arr.push('')
      filteredSuggestions[prop.uri] = prop.suggestions || []
    }
    sortProperties()
    scheduleLiveValidation('selection')
  } catch (error: unknown) {
    if (revision !== propertyFetchRevision) return
    console.error('Failed to load properties', error)
    toast.error(
      getErrorMessage(error, 'Failed to load metadata properties.'),
    )
  } finally {
    if (revision === propertyFetchRevision) {
      loadingProps.value = false
    }
  }
}

function getPropDatatype(prop: PropDef): string | null {
  const datatype = prop.constraints?.datatype ?? prop.datatype

  return typeof datatype === 'string'
    ? datatype
    : datatype == null
      ? null
      : String(datatype)
}

function datatypeLocalName(datatype: string | null): string {
  return (datatype ?? '')
    .toLowerCase()
    .split(/[\/#:]/)
    .pop() ?? ''
}

function isBooleanDatatype(datatype: string | null): boolean {
  return datatypeLocalName(datatype) === 'boolean'
}

const numericDatatypeNames = new Set([
  'integer',
  'int',
  'long',
  'short',
  'byte',
  'nonpositiveinteger',
  'negativeinteger',
  'nonnegativeinteger',
  'positiveinteger',
  'unsignedlong',
  'unsignedint',
  'unsignedshort',
  'unsignedbyte',
  'decimal',
  'float',
  'double',
])

function inputType(datatype: string | null): string {
  const name = datatypeLocalName(datatype)

  if (numericDatatypeNames.has(name)) {
    return 'number'
  }

  // Preserve complete RDF lexical forms, including optional timezones.
  // The backend remains responsible for validating the declared XSD type.
  return 'text'
}

function addValue(propUri: string) {
  getPropValues(propUri).push('')
  validateField(propUri)
  scheduleLiveValidation('metadata')
}

function removeValue(propUri: string, index: number) {
  getPropValues(propUri).splice(index, 1)
  onPropertyInput(propUri)
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
  onPropertyInput(propUri)
}

function getAllowedClassUris(
  ranges: string[],
): string[] | undefined {
  const rangeUris = ranges.filter(Boolean)

  // No declared range means any active class is allowed.
  if (rangeUris.length === 0) {
    return undefined
  }

  return classes.value
    .filter(classOption =>
      rangeUris.some(rangeUri =>
        classOption.uri === rangeUri ||
        classOption.superClasses?.includes(rangeUri),
      ),
    )
    .map(classOption => classOption.uri)
}

async function openCreatePanel(
  propUri: string,
  index: number,
  ranges: string[],
) {
  openingPanelActionKey.value = getPanelActionKey(propUri, index)
  await waitForIndicatorPaint()

  const allowed = getAllowedClassUris(ranges)

  panelState.value = {
    propUri,
    index,
    mode: 'create',
    allowedClasses: allowed,
  }
}

async function openEditPanel(propUri: string, index: number) {
  const uri = getPropValues(propUri)[index]
  if (!uri) return

  openingPanelActionKey.value = getPanelActionKey(propUri, index)
  await waitForIndicatorPaint()

  try {
    const res = await $fetch<any>(
      `${apiBase}/api/instances/${encodeURIComponent(uri)}`,
    )

    const ranges =
      properties.value.find(prop => prop.uri === propUri)?.ranges ?? []

    const allowed = getAllowedClassUris(ranges)

    panelState.value = {
      propUri,
      index,
      mode: 'edit',
      instanceUri: uri,
      allowedClasses: allowed,
      classUris: res.types,
      existingProperties: res.properties as Record<string, string[]>,
    }
  } catch (error: unknown) {
    openingPanelActionKey.value = null

    console.error('Failed to fetch instance', error)
    toast.error(
      getErrorMessage(error, 'Failed to load the linked instance.'),
    )
  }
}

function closePanel() {
  panelState.value = null
  openingPanelActionKey.value = null
}

async function onPanelSubmit(
  payload: {
    classUris: string[]
    instanceUri: string
    properties: Record<string, string[]>
    editablePropertyUris: string[]
  }
) {
  if (!panelState.value || panelLoadingMsg.value) return
  const { propUri, index, mode } = panelState.value
  const allowedClassUris = panelState.value.allowedClasses

  if (
    allowedClassUris !== undefined &&
    payload.classUris.some(
      classUri => !allowedClassUris.includes(classUri),
    )
  ) {
    toast.error(
      'The linked instance has a class that is not permitted by this property’s Range Classes.',
    )
    return
  }

  panelLoadingMsg.value = 'Validating and saving the linked data...'
  panelServerValidationError.value = null
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
          editable_property_uris: payload.editablePropertyUris,
        }),
      })

      getPropValues(propUri)[index] = payload.instanceUri
    }

    onPropertyInput(propUri)
    closePanel()

    toast.success(
      mode === 'create'
        ? 'Linked instance created.'
        : 'Linked instance updated.',
    )

    void store.fetchState()
  } catch (error: unknown) {
    const message = getErrorMessage(
      error,
      'Failed to save the linked instance.',
    )

    panelServerValidationError.value = message
    toast.error(message)
  } finally {
    panelLoadingMsg.value = ''
  }
}

function sortProperties() {
  properties.value.sort((a, b) => {
    const aFilled = getPropValues(a.uri).some(
      value => toLexicalString(value).trim() !== '',
    )
    const bFilled = getPropValues(b.uri).some(
      value => toLexicalString(value).trim() !== '',
    )
    if (aFilled && !bFilled) return -1
    if (!aFilled && bFilled) return 1
    return 0
  })
}

watch(() => panelState.value, (val) => {
  emit('panel-state-changed', val !== null)
})

watch(selectedClasses, () => {
  clearServerValidationState()
  onClassSelectionChange()
}, { deep: true })

function handleSubmit() {
  if (props.submitting) return
  cancelScheduledLiveValidation()
  const cleanProps: Record<string, string[]> = {}
  const editablePropertyUris = properties.value.map(prop => prop.uri)

  for (const prop of properties.value) {
    const vals = getPropValues(prop.uri)
      .map(toLexicalString)
      .filter(value => value.trim() !== '')
    if (vals.length > 0) {
      cleanProps[prop.uri] = vals
    }
  }

  if (!validateAllFields()) return

  clearServerValidationState()

  emit('submit', {
    classUris: selectedClasses.value,
    instanceUri: instanceUri.value,
    properties: cleanProps,
    editablePropertyUris,
  })
}
</script>