<template>
  <tr>
    <!-- Drag handle -->
    <td v-if="draggable" class="border border-gray-300 dark:border-gray-600 p-2 text-center drag-handle cursor-grab" :class="mutedTextClass">⠿</td>

    <!-- URI -->
    <td class="border border-gray-300 dark:border-gray-600 p-2" :class="mutedTextClass">
      {{ formatUri(props.entity.uri) }}
    </td>

    <!-- Types (only for individuals) -->
    <td v-if="showTypes" class="border border-gray-300 dark:border-gray-600 p-2" :class="mutedTextClass">
      <span v-if="props.entity.types?.length">{{ props.entity.types.map(t => formatUri(t)).join(', ') }}</span>
      <span v-else class="text-gray-400 dark:text-gray-500">—</span>
    </td>

    <!-- Domain (only for properties) -->
    <td v-if="showDomain" class="border border-gray-300 dark:border-gray-600 p-2" :class="mutedTextClass">
      <span v-if="props.entity.domain?.length">{{ props.entity.domain.map(d => formatUri(d)).join(', ') }}</span>
      <span v-else class="text-gray-400 dark:text-gray-500">—</span>
    </td>

    <!-- Source -->
    <td class="border border-gray-300 dark:border-gray-600 p-2 text-sm" :class="mutedTextClass">
      {{ sourceLabel(props.entity.sources) }}
    </td>

    <!-- Actions -->
    <td class="border border-gray-300 dark:border-gray-600 p-2 text-center">
      <div class="flex gap-1 justify-center">
        <NuxtLink v-if="props.entity.type !== 'datatype' && props.entity.type !== 'individual' && !isMetadataOnly"
          :to="`/admin/profile/edit?uri=${encodeURIComponent(props.entity.uri)}`"
          class="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300">
          <PhosphorIcon name="pencil-simple" size="16" />
        </NuxtLink>
        <PhosphorIcon v-if="!isCoreEntity" name="x" size="16" class="text-red-600 hover:text-red-800 cursor-pointer"
          @click="$emit('remove', props.entity.uri)" />
      </div>
    </td>
  </tr>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ProfileEntityItem } from '@/types'
import { useDisplay } from '@/composables/useDisplay'
import { useAppStore } from '@/stores/app'
import { CORE_ENTITY_URIS } from '@/utils/coreEntities'

const props = defineProps<{
  entity: ProfileEntityItem
  draggable?: boolean
  showTypes?: boolean
  showDomain?: boolean
}>()

defineEmits<{
  remove: [uri: string]
}>()

const { formatUri } = useDisplay()
const store = useAppStore()

const isCoreEntity = computed(() => CORE_ENTITY_URIS.has(props.entity.uri))
const isMetadataOnly = computed(() => {
  return props.entity.sources?.length === 1 && props.entity.sources[0] === 'Metadata'
})

const mutedTextClass = computed(() => ({
  'text-gray-500 dark:text-gray-400': !props.entity.in_onto && props.entity.ontology !== 'System',
  'text-gray-900 dark:text-gray-100': props.entity.in_onto || props.entity.ontology === 'System',
}))

function sourceLabel(sources?: string[]): string {
  if (!sources || sources.length === 0) return '—'
  return sources.map(src => {
    if (src === 'Metadata') return 'Metadata-only'
    if (src === 'System') return 'System'
    const onto = store.ontologies.find(o => o.filename === src)
    return onto?.title || src
  }).join(', ')
}
</script>