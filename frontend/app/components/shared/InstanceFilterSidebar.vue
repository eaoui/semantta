<template>
    <aside
        class="order-first w-full shrink-0 md:order-last md:sticky md:top-4 md:max-h-[calc(100vh-2rem)] md:self-start md:w-56 md:overflow-y-auto">
        <div>
            <h3 class="text-lg font-semibold mb-4 text-gray-900 dark:text-gray-100">
                {{ mode === 'dataset' ? 'Filter Dataset' : 'Filter Instances' }}
            </h3>

            <div class="space-y-4">
                <!-- Search -->
                <div class="space-y-1">
                    <label class="block text-sm text-gray-700 dark:text-gray-300">
                        Search
                    </label>

                    <SearchBox :model-value="search" :placeholder="searchPlaceholder"
                        @update:model-value="emit('update:search', $event)" />
                </div>

                <!-- Type -->
                <div class="space-y-1">
                    <label class="block text-sm text-gray-700 dark:text-gray-300">
                        Type
                    </label>

                    <select :value="selectedType" class="block w-full min-w-0 border border-gray-300
                   dark:border-gray-600 rounded px-3 py-2 text-sm
                   bg-white dark:bg-gray-700
                   text-gray-900 dark:text-gray-100" @change="updateType">
                        <option value="">All types</option>

                        <option v-for="type in typeOptions" :key="type.uri" :value="type.uri">
                            {{ type.label }}
                        </option>
                    </select>
                </div>

                <!-- Admin Instances-only filters -->
                <template v-if="mode === 'instances'">
                    <div class="space-y-1">
                        <label class="block text-sm text-gray-700 dark:text-gray-300">
                            Source
                        </label>

                        <select :value="sourceFilter" class="block w-full min-w-0 border border-gray-300
                     dark:border-gray-600 rounded px-3 py-2 text-sm
                     bg-white dark:bg-gray-700
                     text-gray-900 dark:text-gray-100" @change="updateSource">
                            <option value="all">All sources</option>
                            <option value="imported">Imported</option>
                            <option value="created">Created</option>
                        </select>
                    </div>

                    <label class="flex items-start gap-2 cursor-pointer
                   text-sm text-gray-700 dark:text-gray-300">
                        <input type="checkbox" class="mt-0.5 h-4 w-4 shrink-0" :checked="showBlankNodes"
                            @change="updateBlankNodes" />
                        <span>Display blank nodes</span>
                    </label>

                    <label class="flex items-start gap-2 cursor-pointer
                   text-sm text-gray-700 dark:text-gray-300">
                        <input type="checkbox" class="mt-0.5 h-4 w-4 shrink-0" :checked="starredOnly"
                            @change="updateStarredOnly" />
                        <span>Display only starred</span>
                    </label>
                </template>
            </div>
        </div>

        <p v-if="showCount" class="mt-6 text-sm text-gray-600 dark:text-gray-400">
            <template v-if="hasNonCountableFilters">
                Showing {{ pageStart }}–{{ pageEnd }} instance(s)
            </template>
            <template v-else>
                Showing {{ pageStart }}–{{ pageEnd }} of {{ total }} instance(s)
            </template>
        </p>
    </aside>
</template>

<script setup lang="ts">
import SearchBox from '@/components/shared/SearchBox.vue'

type FilterMode = 'dataset' | 'instances'
type SourceFilter = 'all' | 'imported' | 'created'

interface TypeOption {
    uri: string
    label: string
}

withDefaults(
    defineProps<{
        mode: FilterMode
        search: string
        searchPlaceholder: string
        selectedType: string
        typeOptions: TypeOption[]
        sourceFilter?: SourceFilter
        showBlankNodes?: boolean
        starredOnly?: boolean
        pageStart: number
        pageEnd: number
        total: number
        hasNonCountableFilters: boolean
        showCount?: boolean
    }>(),
    {
        sourceFilter: 'all',
        showBlankNodes: false,
        starredOnly: false,
        showCount: false,
    },
)

const emit = defineEmits<{
    'update:search': [value: string]
    'update:selectedType': [value: string]
    'update:sourceFilter': [value: SourceFilter]
    'update:showBlankNodes': [value: boolean]
    'update:starredOnly': [value: boolean]
}>()

function updateType(event: Event) {
    emit(
        'update:selectedType',
        (event.target as HTMLSelectElement).value,
    )
}

function updateSource(event: Event) {
    const value = (event.target as HTMLSelectElement).value

    if (
        value === 'all' ||
        value === 'imported' ||
        value === 'created'
    ) {
        emit('update:sourceFilter', value)
    }
}

function updateBlankNodes(event: Event) {
    emit(
        'update:showBlankNodes',
        (event.target as HTMLInputElement).checked,
    )
}

function updateStarredOnly(event: Event) {
    emit(
        'update:starredOnly',
        (event.target as HTMLInputElement).checked,
    )
}
</script>