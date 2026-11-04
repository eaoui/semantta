<template>
  <div ref="rootElement" class="relative" @focusout="handleFocusOut">
    <!-- Selected language tags -->
    <div class="flex min-h-11 flex-wrap items-center gap-2 rounded border
        border-gray-300 bg-white p-2 dark:border-gray-600 dark:bg-gray-700">
      <span v-for="(tag, index) in selectedTags" :key="`${tag}-${index}`" class="inline-flex items-center gap-2 rounded bg-blue-100
          px-2 py-1 text-sm text-blue-800 dark:bg-blue-900
          dark:text-blue-100">
        <span>{{ getBcp47LanguageTagLabel(tag) }}</span>

        <span class="text-xs opacity-70">{{ tag }}</span>

        <span v-if="!isBcp47LanguageTagAvailable(tag)" class="text-xs opacity-60"
          title="This existing value is not in the current CLDR catalogue">
          Existing
        </span>

        <button type="button" :aria-label="`Remove ${tag}`" title="Remove language tag"
          class="font-semibold hover:text-red-600 dark:hover:text-red-300" @click.stop="removeTag(index)">
          ×
        </button>
      </span>

      <input v-model="searchQuery" type="search" autocomplete="off" aria-label="Search BCP 47 language tags"
        placeholder="Search language tags…" class="min-w-40 flex-1 border-0 bg-transparent p-1 text-sm
          text-gray-900 outline-none dark:text-gray-100" @focus="isOpen = true"
        @keydown.esc.prevent="isOpen = false" />
    </div>

    <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
      Search by language name or BCP 47 tag.
    </p>

    <!-- Search results -->
    <div v-if="isOpen" class="absolute z-30 mt-1 max-h-64 w-full overflow-y-auto
        rounded border border-gray-300 bg-white shadow-lg
        dark:border-gray-600 dark:bg-gray-800" role="listbox" aria-label="Available language tags"
      aria-multiselectable="true">
      <button v-for="option in filteredOptions" :key="option.value" type="button" role="option"
        :aria-selected="isSelected(option.value)" class="flex w-full items-center gap-3 px-3 py-2 text-left
          hover:bg-gray-100 dark:hover:bg-gray-700" :class="isSelected(option.value)
            ? 'bg-blue-50 dark:bg-blue-950'
            : ''" @mousedown.prevent @click="toggleOption(option.value)">
        <span class="flex h-4 w-4 shrink-0 items-center justify-center
            rounded border text-xs" :class="isSelected(option.value)
              ? 'border-blue-600 bg-blue-600 text-white'
              : 'border-gray-400 dark:border-gray-500'">
          {{ isSelected(option.value) ? '✓' : '' }}
        </span>

        <span class="min-w-0 flex-1 truncate text-sm text-gray-900 dark:text-gray-100">
          {{ option.label }}
        </span>

        <span class="shrink-0 text-xs text-gray-500 dark:text-gray-400">
          {{ option.value }}
        </span>
      </button>

      <p v-if="filteredOptions.length === 0" class="px-3 py-4 text-center text-sm text-gray-500 dark:text-gray-400">
        No matching language tags.
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

import {
  getBcp47LanguageTagLabel,
  isBcp47LanguageTagAvailable,
  isLanguageTagSelected,
  normalizeLanguageTagSelection,
  searchBcp47LanguageTags,
  toggleLanguageTagSelection,
} from '~/utils/bcp47LanguageTags'

const props = defineProps<{
  modelValue: string[]
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: string[]): void
}>()

const rootElement = ref<HTMLElement | null>(null)
const searchQuery = ref('')
const isOpen = ref(false)

const selectedTags = computed(() =>
  normalizeLanguageTagSelection(props.modelValue),
)

const filteredOptions = computed(() =>
  searchBcp47LanguageTags(searchQuery.value),
)

function isSelected(tag: string): boolean {
  return isLanguageTagSelected(selectedTags.value, tag)
}

function toggleOption(tag: string) {
  emit(
    'update:modelValue',
    toggleLanguageTagSelection(selectedTags.value, tag),
  )
}

function removeTag(index: number) {
  emit(
    'update:modelValue',
    selectedTags.value.filter((_, currentIndex) => currentIndex !== index),
  )
}

function handleFocusOut(event: FocusEvent) {
  const nextTarget = event.relatedTarget as Node | null

  if (nextTarget && rootElement.value?.contains(nextTarget)) {
    return
  }

  isOpen.value = false
}
</script>