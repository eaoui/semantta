<template>
  <div>
    <!-- Selected tags -->
    <div class="flex flex-wrap gap-1 mb-2">
      <span v-for="uri in selected" :key="uri"
        class="inline-flex items-center gap-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 text-sm px-2 py-1 rounded">
        {{ getLabel(uri) }}
        <button type="button" @click="remove(uri)"
          class="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-200">&times;</button>
      </span>
      <span v-if="selected.length === 0" class="text-gray-400 dark:text-gray-500 text-sm">None selected</span>
    </div>

    <!-- Search input + dropdown -->
    <div class="relative">
      <input v-model="search" type="text" :placeholder="placeholder"
        class="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded p-2 w-full"
        autocomplete="off" @focus="open = true" @input="open = true" @blur="hideDropdown" @click="open = true"
        @keydown="onKeyDown" />
      <ul v-if="open && filteredOptions.length > 0" ref="dropdownList"
        class="absolute z-10 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded shadow max-h-48 overflow-auto w-full mt-1">
        <li v-for="(opt, index) in filteredOptions" :key="opt.uri" @mousedown.prevent="add(opt.uri)"
          :class="{ 'bg-gray-100 dark:bg-gray-600': index === highlightIndex }"
          class="px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-600 cursor-pointer text-sm text-gray-900 dark:text-gray-100">
          {{ opt.label }}
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import { useDisplay } from '@/composables/useDisplay'

const { formatUri } = useDisplay()
// Raw entity URIs, independent of display format
const rawEntities = ref<string[]>([])

const props = withDefaults(defineProps<{
  modelValue: string[]
  placeholder?: string
  availableEntities?: { uri: string; label: string }[]
  entityType?: 'class' | 'property' | 'datatype'
}>(), {
  placeholder: 'Search…',
  availableEntities: () => [],
  entityType: 'class'
})

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
}>()

const store = useAppStore()
// Build the full list whenever rawEntities or display format changes
const allEntities = computed(() =>
  rawEntities.value.map(uri => ({
    uri,
    label: formatUri(uri, store.displayFormat) || uri,
  }))
)
const search = ref('')
const open = ref(false)

const highlightIndex = ref(-1)
const dropdownList = ref<HTMLElement | null>(null)

watch(search, () => {
  highlightIndex.value = -1
})

onMounted(async () => {
  if (props.availableEntities.length > 0) {
    rawEntities.value = props.availableEntities.map(e => e.uri)
  } else {
    if (props.entityType === 'class') {
      try {
        const res = await $fetch<{ uri: string; label: string }[]>(
          `${useRuntimeConfig().public.apiBase}/api/create-form/classes`
        )
        // Classes already come with labels from the backend – we still store their URIs
        // and let the computed re‑format them according to the current display mode.
        rawEntities.value = res.map((c: any) => c.uri)
      } catch (e) {
        console.error('Failed to load classes', e)
      }
    } else if (props.entityType === 'property') {
      const activeProps = store.profileEntities.filter(
        e => e.active && ['object_property', 'datatype_property', 'annotation_property'].includes(e.type)
      )
      rawEntities.value = activeProps.map(e => e.uri)
    } else if (props.entityType === 'datatype') {
      const activeDatatypes = store.profileEntities.filter(
        e => e.active && e.type === 'datatype'
      )
      rawEntities.value = activeDatatypes.map(e => e.uri)
    }
  }
})

const selected = computed(() => props.modelValue || [])

const filteredOptions = computed(() => {
  const q = search.value.toLowerCase().trim()
  const available = allEntities.value.filter(e => !selected.value.includes(e.uri))
  if (!q) return available
  return available.filter(e => e.label.toLowerCase().includes(q) || e.uri.toLowerCase().includes(q))
})

function add(uri: string) {
  if (!selected.value.includes(uri)) {
    emit('update:modelValue', [...selected.value, uri])
  }
  search.value = ''
  open.value = false
  highlightIndex.value = -1
}

function remove(uri: string) {
  emit('update:modelValue', selected.value.filter(u => u !== uri))
}

function getLabel(uri: string): string {
  const found = allEntities.value.find(e => e.uri === uri)
  if (found?.label) return found.label
  const profileEntity = store.profileEntities.find(e => e.uri === uri)
  if (profileEntity) {
    return formatUri(profileEntity.uri, store.displayFormat) || profileEntity.uri
  }
  return formatUri(uri, store.displayFormat) || uri
}

function hideDropdown() {
  setTimeout(() => {
    open.value = false
    highlightIndex.value = -1
  }, 200)
}

function onKeyDown(e: KeyboardEvent) {
  if (!open.value) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      open.value = true
      highlightIndex.value = e.key === 'ArrowDown' ? 0 : (filteredOptions.value.length - 1)
      scrollToHighlighted()
    }
    return
  }

  const options = filteredOptions.value
  if (options.length === 0) return

  if (e.key === 'ArrowDown') {
    e.preventDefault()
    highlightIndex.value = (highlightIndex.value + 1) % options.length
    scrollToHighlighted()
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    highlightIndex.value = (highlightIndex.value - 1 + options.length) % options.length
    scrollToHighlighted()
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const idx = highlightIndex.value
    if (idx >= 0 && idx < options.length) {
      const option = options[idx]
      if (option) {
        add(option.uri)
      }
    }
  } else if (e.key === 'Escape') {
    open.value = false
    highlightIndex.value = -1
  }
}

function scrollToHighlighted() {
  const list = dropdownList.value
  if (!list) return
  const items = list.querySelectorAll('li')
  const idx = highlightIndex.value
  if (idx >= 0 && idx < items.length) {
    const item = items[idx]
    if (item) {
      item.scrollIntoView({ block: 'nearest' })
    }
  }
}
</script>