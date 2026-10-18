<template>
    <div ref="graphPanel"
        class="graph-panel relative w-full h-150 border border-gray-300 dark:border-gray-700 rounded-lg overflow-hidden bg-white dark:bg-gray-900 [&:fullscreen]:w-screen [&:fullscreen]:h-screen [&:fullscreen]:max-w-none [&:fullscreen]:max-h-none [&:fullscreen]:rounded-none">
        <div class="grid h-full min-h-0 w-full" :class="filtersVisible
            ? 'grid-cols-[minmax(0,5fr)_minmax(0,1fr)]'
            : 'grid-cols-[minmax(0,1fr)]'">
            <!-- Main graph area -->
            <section class="relative w-full h-full min-w-0 min-h-0">
                <div ref="graphContainer" class="w-full h-full"></div>

                <!-- Graph toolbar -->
                <div class="absolute top-3 right-3 z-20 flex items-center gap-2">
                    <!-- Fit -->
                    <button type="button" @click="fitGraph" title="Fit to container" aria-label="Reset view"
                        class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded border border-gray-300 dark:border-gray-600 bg-white/95 dark:bg-gray-800/95 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 shadow-sm">
                        <PhosphorIcon name="frame-corners" class="h-5 w-5" aria-hidden="true" />
                    </button>

                    <!-- Fullscreen -->
                    <button type="button" @click="toggleFullscreen"
                        :aria-label="isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'"
                        :title="isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'"
                        class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded border border-gray-300 dark:border-gray-600 bg-white/95 dark:bg-gray-800/95 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 shadow-sm">
                        <PhosphorIcon :name="isFullscreen ? 'corners-in' : 'corners-out'" class="h-5 w-5"
                            aria-hidden="true" />
                    </button>

                    <!-- Reopen sidebar; hidden when the sidebar is already visible -->
                    <button v-if="!filtersVisible" type="button" @click="toggleFilters" title="Display Sidebar"
                        aria-label="Display Sidebar"
                        class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded border border-gray-300 dark:border-gray-600 bg-white/95 dark:bg-gray-800/95 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 shadow-sm">
                        <PhosphorIcon name="sidebar-simple" class="h-5 w-5 transform-[scaleX(-1)]" aria-hidden="true" />
                    </button>
                </div>

            </section>

            <!-- Right-hand filter sidebar -->
            <aside v-if="filtersVisible"
                class="w-full h-full min-w-0 min-h-0 overflow-y-auto overflow-x-hidden overscroll-contain scrollbar-gutter-stable border-l border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
                <header class="sticky top-0 z-10 flex items-center justify-between gap-2
                           px-3 py-3 border-b border-gray-200 dark:border-gray-700
                           bg-gray-50 dark:bg-gray-800">
                    <h2 class="text-sm font-semibold text-gray-800 dark:text-gray-100">
                        Graph filters
                    </h2>

                    <button type="button" @click="toggleFilters" title="Hide filters" aria-label="Hide filters" class="shrink-0 px-2 py-1 rounded border
                               border-gray-300 dark:border-gray-600
                               text-xs text-gray-700 dark:text-gray-200
                               hover:bg-gray-100 dark:hover:bg-gray-700">
                        Hide
                    </button>
                </header>

                <div class="p-3 space-y-4">
                    <!-- Search -->
                    <div class="space-y-1">
                        <label for="graph-search" class="block text-xs font-medium text-gray-700 dark:text-gray-300">
                            Search node
                        </label>

                        <input id="graph-search" v-model="graphSearchQuery" type="search" placeholder="Search..." class="block w-full min-w-0 box-border border
                                   border-gray-300 dark:border-gray-600
                                   rounded px-2 py-2 text-sm
                                   bg-white dark:bg-gray-700
                                   text-gray-900 dark:text-gray-100" @input="handleGraphSearch" />
                    </div>

                    <!-- Layout -->
                    <div class="space-y-1">
                        <label for="graph-layout" class="block text-xs font-medium text-gray-700 dark:text-gray-300">
                            Layout
                        </label>

                        <select id="graph-layout" v-model="graphLayout" @change="changeLayout" class="block w-full min-w-0 border
                                   border-gray-300 dark:border-gray-600
                                   rounded px-2 py-2 text-sm
                                   bg-white dark:bg-gray-700
                                   text-gray-900 dark:text-gray-100">
                            <option value="force">Force-directed</option>
                            <option value="hierarchical">Hierarchical</option>
                        </select>
                    </div>


                    <!-- Layout controls -->
                    <div class="grid grid-cols-2 gap-2">
                        <button type="button" @click="togglePhysics"
                            class="inline-flex min-w-0 w-full items-center justify-center rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-2 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600">
                            {{ physicsEnabled ? 'Freeze' : 'Resume' }}
                        </button>

                        <button type="button" @click="shuffleLayout"
                            class="inline-flex min-w-0 w-full items-center justify-center rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-2 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600">
                            Shuffle
                        </button>
                    </div>


                    <!-- Blank nodes -->
                    <label class="flex items-start gap-2 min-w-0
                               text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
                        <input type="checkbox" v-model="showBlankNodes" @change="rebuildGraph"
                            class="mt-0.5 shrink-0" />
                        <span>Show blank nodes</span>
                    </label>

                    <!-- Class filters -->
                    <section class="border-t border-gray-200 dark:border-gray-700 pt-3">
                        <div class="flex items-start justify-between gap-1 mb-2">
                            <h3 class="text-xs font-semibold text-gray-800 dark:text-gray-100">
                                Classes
                            </h3>

                            <div class="flex shrink-0 gap-1">
                                <button type="button" @click="setAllClasses(true)"
                                    class="text-xs text-blue-600 dark:text-blue-400 hover:underline">
                                    All
                                </button>

                                <button type="button" @click="setAllClasses(false)"
                                    class="text-xs text-blue-600 dark:text-blue-400 hover:underline">
                                    None
                                </button>
                            </div>
                        </div>

                        <p v-if="classFilters.length === 0" class="text-xs text-gray-500 dark:text-gray-400">
                            No classes available.
                        </p>

                        <div v-else class="space-y-2">
                            <label v-for="classItem in classFilters" :key="classItem.uri" :title="classItem.uri"
                                class="flex items-start gap-2 min-w-0 cursor-pointer">
                                <input type="checkbox" class="mt-0.5 shrink-0"
                                    :checked="selectedClassUris.has(classItem.uri)"
                                    @change="onClassFilterChange(classItem.uri, $event)" />

                                <span class="min-w-0 break-words text-xs text-gray-700 dark:text-gray-200">
                                    {{ classItem.label }}
                                </span>
                            </label>
                        </div>
                    </section>

                    <!-- Edge/property filters -->
                    <section class="border-t border-gray-200 dark:border-gray-700 pt-3">
                        <div class="flex items-start justify-between gap-1 mb-2">
                            <h3 class="text-xs font-semibold text-gray-800 dark:text-gray-100">
                                Properties (edges)
                            </h3>

                            <div class="flex shrink-0 gap-1">
                                <button type="button" @click="setAllEdgeProperties(true)"
                                    class="text-xs text-blue-600 dark:text-blue-400 hover:underline">
                                    All
                                </button>
                                <button type="button" @click="setAllEdgeProperties(false)"
                                    class="text-xs text-blue-600 dark:text-blue-400 hover:underline">
                                    None
                                </button>
                            </div>
                        </div>

                        <p v-if="edgeProperties.length === 0" class="text-xs text-gray-500 dark:text-gray-400">
                            No edges available.
                        </p>

                        <div v-else class="space-y-2">
                            <label v-for="property in edgeProperties" :key="property.uri" :title="property.uri"
                                class="flex items-start gap-2 min-w-0 cursor-pointer">
                                <input type="checkbox" class="mt-0.5 shrink-0"
                                    :checked="selectedEdgePropertyUris.has(property.uri)"
                                    @change="onEdgePropertyChange(property.uri, $event)" />

                                <span class="min-w-0 wrap-break-word text-xs
                                             text-gray-700 dark:text-gray-200">
                                    <span class="block wrap-break-word text-xs text-gray-700 dark:text-gray-200">
                                        {{ property.label }}
                                    </span>
                                </span>
                            </label>
                        </div>
                    </section>
                </div>
            </aside>
        </div>
    </div>
</template>


<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { Network } from 'vis-network'
import 'vis-network/styles/vis-network.min.css'

const props = defineProps<{
    instanceUri: string
    instanceProperties: Record<string, string[]>
    bnodeData: Record<string, any>
    formatUri: (uri: string) => string
    isBlankNode: (uri: string) => boolean
    getDisplayLabel: (uri: string) => string
    visible: boolean
    instanceTypes: string[]
}>()

const emit = defineEmits<{
    (e: 'loading', value: boolean): void
    (e: 'error', message: string): void
}>()

// ---------- state ----------
const graphSearchQuery = ref('')
const physicsEnabled = ref(true)
const graphLayout = ref<'force' | 'hierarchical'>('force')
const showBlankNodes = ref(true)
const graphPanel = ref<HTMLElement | null>(null)
const graphContainer = ref<HTMLElement | null>(null)

const isFullscreen = ref(false)
const filtersVisible = ref(true)

const edgeProperties = ref<Array<{ uri: string; label: string }>>([])
const selectedEdgePropertyUris = ref<Set<string>>(new Set())

const graphRuntimeConfig = useRuntimeConfig()

const classFilters = ref<Array<{ uri: string; label: string }>>([])
const selectedClassUris = ref<Set<string>>(new Set())

const knownEdgePropertyUris = ref<Set<string>>(new Set())
const knownClassUris = ref<Set<string>>(new Set())
const filterOptionsInitialized = ref(false)

let filterTargetUri: string | null = null

let network: Network | null = null
let allGraphNodes: any[] = []
let allGraphEdges: any[] = []

const nodeSearchLabels = new Map<string, string>()
const nodePositions = new Map<string, { x: number; y: number }>()

const initialized = ref(false)

// ---------- helpers ----------
function reconcileFilterSelection(
    selected: Set<string>,
    previouslyAvailable: Set<string>,
    currentlyAvailable: Set<string>,
): Set<string> {
    const next = new Set(
        [...selected].filter(uri => currentlyAvailable.has(uri)),
    )

    // New options start enabled; previous choices are preserved.
    for (const uri of currentlyAvailable) {
        if (!previouslyAvailable.has(uri)) {
            next.add(uri)
        }
    }

    return next
}

function truncateLabel(label: string, maxLength = 32): string {
    if (label.length <= maxLength) return label
    return `${label.slice(0, maxLength - 3)}...`
}

function isGraphResourceUri(uri: string): boolean {
    return /^https?:\/\//i.test(uri) || uri.startsWith('urn:')
}

function toggleFilters() {
    filtersVisible.value = !filtersVisible.value

    void nextTick(() => {
        network?.redraw()
    })
}

async function toggleFullscreen() {
    const panel = graphPanel.value
    if (!panel) return

    try {
        if (document.fullscreenElement === panel) {
            await document.exitFullscreen()
        } else {
            await panel.requestFullscreen()
        }
    } catch (error) {
        emit(
            'error',
            error instanceof Error
                ? error.message
                : 'Unable to toggle fullscreen.',
        )
    }
}

function handleFullscreenChange() {
    isFullscreen.value = document.fullscreenElement === graphPanel.value

    void nextTick(() => {
        network?.redraw()
    })
}

function isPassThroughBlankNode(bnodeUri: string, propertyUri: string): boolean {
    const bnode = props.bnodeData?.[bnodeUri]
    if (!bnode) return false
    if (bnode.types && bnode.types.length > 0) return false
    const props_ = bnode.properties || {}
    const propKeys = Object.keys(props_)
    return propKeys.length === 1 && propKeys[0] === propertyUri
}

function getBlankNodeLabel(uri: string): string {
    const preferredLabel = props.getDisplayLabel(uri)
    if (preferredLabel && preferredLabel !== 'Blank node') {
        return preferredLabel
    }

    const bnode = props.bnodeData?.[uri]
    if (bnode?.types?.length) {
        return bnode.types.map((t: string) => props.formatUri(t)).join(', ')
    }

    return 'Blank node'
}

// ---------- graph building ----------
async function buildGraph() {
    if (!props.instanceUri) return
    emit('loading', true)
    emit('error', '')

    const container = graphContainer.value
    if (!container || container.clientWidth === 0) {
        emit('error', 'Graph container not ready.')
        emit('loading', false)
        return
    }
    if (network) {
        network.destroy()
        network = null
    }

    try {
        const allUris = new Set<string>()

        const edgeMap = new Map<
            string,
            {
                id: string
                from: string
                to: string
                propertyUri: string
                label: string
            }
        >()

        function addGraphEdge(
            from: string,
            propertyUri: string,
            to: string,
        ) {
            const id = JSON.stringify([from, propertyUri, to])

            if (!edgeMap.has(id)) {
                edgeMap.set(id, {
                    id,
                    from,
                    to,
                    propertyUri,
                    label: props.formatUri(propertyUri),
                })
            }
        }

        if (!props.isBlankNode(props.instanceUri)) {
            allUris.add(props.instanceUri)
        }

        // ---- direct properties ----
        for (const [pred, vals] of Object.entries(props.instanceProperties)) {
            for (const val of vals as string[]) {
                if (!isGraphResourceUri(val)) continue
                if (!showBlankNodes.value && props.isBlankNode(val)) continue

                // pass‑through blank node?
                if (props.isBlankNode(val) && isPassThroughBlankNode(val, pred)) {
                    const bnode = props.bnodeData?.[val]
                    if (bnode?.properties?.[pred]) {
                        for (const subVal of bnode.properties[pred]) {
                            if (isGraphResourceUri(subVal)) {
                                allUris.add(subVal)
                                addGraphEdge(props.instanceUri, pred, subVal)
                            }
                        }
                    }
                    continue
                }

                allUris.add(val)
                addGraphEdge(props.instanceUri, pred, val)
            }
        }

        // ---- expand blank nodes one level ----
        const processedBlankNodes = new Set<string>()
        for (const uri of allUris) {
            if (!props.isBlankNode(uri) || processedBlankNodes.has(uri)) continue
            if (!showBlankNodes.value) continue
            processedBlankNodes.add(uri)

            const bnode = props.bnodeData?.[uri]
            if (!bnode?.properties) continue

            for (const [bpred, bvals] of Object.entries(bnode.properties)) {
                for (const bval of bvals as string[]) {
                    if (isGraphResourceUri(bval)) {
                        if (!showBlankNodes.value && props.isBlankNode(bval)) continue

                        allUris.add(bval)
                        addGraphEdge(uri, bpred, bval)
                    }
                }
            }
        }

        // Start with fresh filter defaults only when the graph's root changes.
        // Rebuilding the same graph preserves the user's filter selections.
        if (filterTargetUri !== props.instanceUri) {
            filterTargetUri = props.instanceUri
            filterOptionsInitialized.value = false

            selectedEdgePropertyUris.value = new Set()
            selectedClassUris.value = new Set()
            knownEdgePropertyUris.value = new Set()
            knownClassUris.value = new Set()

            graphSearchQuery.value = ''
        }

        // Retrieve RDF types for graph nodes in batches.
        const typesByUri: Record<string, string[]> = {}

        const graphUris = Array.from(allUris)

        const apiBase = String(
            graphRuntimeConfig.public.apiBase,
        ).replace(/\/$/, '')

        try {
            for (let offset = 0; offset < graphUris.length; offset += 250) {
                const response = await $fetch<{
                    types_by_uri: Record<string, string[]>
                }>(`${apiBase}/api/instances/types-by-uri`, {
                    method: 'POST',
                    body: {
                        uris: graphUris.slice(offset, offset + 250),
                    },
                })

                Object.assign(typesByUri, response.types_by_uri)
            }
        } catch (error) {
            // The graph should remain usable even if type lookup fails.
            console.warn('Could not retrieve graph-node types:', error)
        }

        // ---- nodes ----
        const nodes: any[] = []
        nodeSearchLabels.clear()

        for (const uri of allUris) {
            const isBlank = props.isBlankNode(uri)
            const isMain = uri === props.instanceUri

            const fullLabel = (
                isBlank
                    ? getBlankNodeLabel(uri)
                    : props.getDisplayLabel(uri)
            ) || props.formatUri(uri) || uri

            nodeSearchLabels.set(uri, fullLabel)

            nodes.push({
                id: uri,
                label: truncateLabel(fullLabel),
                title: fullLabel,
                font: { size: 12 },
                color: isMain
                    ? { background: '#3B82F6', border: '#1E40AF' }
                    : isBlank
                        ? { background: '#FEF3C7', border: '#D97706' }
                        : { background: '#E5E7EB', border: '#9CA3AF' },
                shape: isMain ? 'box' : 'ellipse',
                size: isMain ? 30 : isBlank ? 18 : 20,
                classes: Array.from(new Set<string>([
                    ...(typesByUri[uri] || []),
                    ...(uri === props.instanceUri ? props.instanceTypes || [] : []),
                    ...(props.bnodeData?.[uri]?.types || []),
                ])),
            })
        }

        // ---- edges ----
        const isDark = document.documentElement.classList.contains('dark')

        const edgeDefinitions = Array.from(edgeMap.values())

        const propertyLabels = new Map<string, string>()

        for (const edge of edgeDefinitions) {
            propertyLabels.set(edge.propertyUri, edge.label)
        }

        edgeProperties.value = Array.from(
            propertyLabels,
            ([uri, label]) => ({ uri, label }),
        ).sort((a, b) =>
            a.label.localeCompare(b.label) || a.uri.localeCompare(b.uri),
        )

        const classLabels = new Map<string, string>()

        for (const node of nodes) {
            for (const classUri of node.classes as string[]) {
                classLabels.set(
                    classUri,
                    props.formatUri(classUri) || classUri,
                )
            }
        }

        classFilters.value = Array.from(
            classLabels,
            ([uri, label]) => ({ uri, label }),
        ).sort((a, b) =>
            a.label.localeCompare(b.label) ||
            a.uri.localeCompare(b.uri),
        )

        const nextEdgeUris = new Set(
            edgeProperties.value.map(property => property.uri),
        )

        const nextClassUris = new Set(
            classFilters.value.map(item => item.uri),
        )

        if (!filterOptionsInitialized.value) {
            selectedEdgePropertyUris.value = new Set(nextEdgeUris)
            selectedClassUris.value = new Set(nextClassUris)
        } else {
            selectedEdgePropertyUris.value = reconcileFilterSelection(
                selectedEdgePropertyUris.value,
                knownEdgePropertyUris.value,
                nextEdgeUris,
            )

            selectedClassUris.value = reconcileFilterSelection(
                selectedClassUris.value,
                knownClassUris.value,
                nextClassUris,
            )
        }

        knownEdgePropertyUris.value = nextEdgeUris
        knownClassUris.value = nextClassUris
        filterOptionsInitialized.value = true

        const edges: any[] = edgeDefinitions.map(edge => ({
            ...edge,
            font: {
                size: 10,
                color: isDark ? '#D1D5DB' : '#6B7280',
                background: isDark ? '#111827' : '#FFFFFF',
                strokeWidth: 0,
            },
            arrows: 'to',
        }))

        allGraphNodes = nodes
        allGraphEdges = edges

        const data = { nodes, edges }

        const options = {
            autoResize: true,
            width: '100%',
            height: '100%',
            layout: {
                improvedLayout: true,
                hierarchical: graphLayout.value === 'hierarchical',
            },
            edges: {
                smooth: {
                    enabled: true,
                    type: 'curvedCW',
                    roundness: 0.2,
                },
            },
            physics: {
                enabled: physicsEnabled.value,
                solver: 'forceAtlas2Based',
            },
            interaction: {
                hover: true,
                zoomView: true,
            },
        }

        network = new Network(container, data, options)
        applyGraphFilters()
    } catch (e: any) {
        emit('error', e.message || 'Graph creation failed')
    } finally {
        emit('loading', false)
    }
}

function applyGraphFilters() {
    if (!network) return

    // Preserve positions for currently visible nodes.
    const currentPositions = network.getPositions()

    for (const [uri, position] of Object.entries(currentPositions)) {
        nodePositions.set(uri, {
            x: position.x,
            y: position.y,
        })
    }

    // Class filtering is applied independently of edge filtering.
    const classEligibleUris = new Set(
        allGraphNodes
            .filter(node => {
                if (node.id === props.instanceUri) return true

                const classes = node.classes as string[] || []

                // Untyped nodes (including blank nodes) remain visible.
                if (classes.length === 0) return true

                return classes.some(
                    classUri => selectedClassUris.value.has(classUri),
                )
            })
            .map(node => node.id),
    )

    const visibleEdges = allGraphEdges.filter(edge =>
        selectedEdgePropertyUris.value.has(edge.propertyUri) &&
        classEligibleUris.has(edge.from) &&
        classEligibleUris.has(edge.to),
    )

    // Keep the root and nodes connected by the remaining edges.
    const visibleNodeUris = new Set<string>([props.instanceUri])

    for (const edge of visibleEdges) {
        visibleNodeUris.add(edge.from)
        visibleNodeUris.add(edge.to)
    }

    const visibleNodes = allGraphNodes
        .filter(node =>
            node.id === props.instanceUri ||
            (
                classEligibleUris.has(node.id) &&
                visibleNodeUris.has(node.id)
            ),
        )
        .map(node => {
            const position = nodePositions.get(node.id)

            return position
                ? { ...node, x: position.x, y: position.y }
                : node
        })

    network.setData({
        nodes: visibleNodes,
        edges: visibleEdges,
    })

    // Reapply search highlighting to the filtered nodes, without changing
    // either filter selection or the current viewport.
    if (graphSearchQuery.value.trim()) {
        applySearchHighlights(false)
    }

    network.redraw()
}

function onEdgePropertyChange(
    propertyUri: string,
    event: Event,
) {
    const input = event.target

    if (!(input instanceof HTMLInputElement)) return

    const nextSelection = new Set(selectedEdgePropertyUris.value)

    if (input.checked) {
        nextSelection.add(propertyUri)
    } else {
        nextSelection.delete(propertyUri)
    }

    selectedEdgePropertyUris.value = nextSelection
    applyGraphFilters()
}

function setAllEdgeProperties(checked: boolean) {
    selectedEdgePropertyUris.value = checked
        ? new Set(edgeProperties.value.map(property => property.uri))
        : new Set()

    applyGraphFilters()
}

function onClassFilterChange(
    classUri: string,
    event: Event,
) {
    const input = event.target

    if (!(input instanceof HTMLInputElement)) return

    const next = new Set(selectedClassUris.value)

    if (input.checked) {
        next.add(classUri)
    } else {
        next.delete(classUri)
    }

    selectedClassUris.value = next
    applyGraphFilters()
}

function setAllClasses(checked: boolean) {
    selectedClassUris.value = checked
        ? new Set(classFilters.value.map(item => item.uri))
        : new Set()

    applyGraphFilters()
}

function rebuildGraph() {
    // simply re‑run build (used by checkbox)
    buildGraph()
}

// ---------- control functions ----------
function applySearchHighlights(fitMatches: boolean) {
    if (!network) return

    const query = graphSearchQuery.value.toLowerCase().trim()

    if (!query) {
        network.selectNodes([])

        if (fitMatches) {
            network.fit({ animation: true })
        }

        return
    }

    // Search full labels, not the labels shortened for display.
    const visibleNodes = (
        network as any
    ).body.data.nodes.get() as Array<{ id: string; label?: string }>

    const matchingIds = visibleNodes
        .filter(node => {
            const fullLabel = nodeSearchLabels.get(node.id) || node.label || ''
            return fullLabel.toLowerCase().includes(query)
        })
        .map(node => node.id)

    // Select all matches, not just the first result.
    network.selectNodes(matchingIds)

    if (fitMatches && matchingIds.length > 0) {
        network.fit({
            nodes: matchingIds,
            animation: true,
        })
    }
}

function handleGraphSearch() {
    applySearchHighlights(true)
}

function togglePhysics() {
    physicsEnabled.value = !physicsEnabled.value
    if (network) {
        network.setOptions({ physics: { enabled: physicsEnabled.value } })
    }
}

function changeLayout() {
    if (network) {
        network.setOptions({ layout: { hierarchical: graphLayout.value === 'hierarchical' } })
    }
}

function fitGraph() {
    network?.fit({ animation: true })
}

function shuffleLayout() {
    if (!network || !graphContainer.value) return
    const width = graphContainer.value.clientWidth
    const height = graphContainer.value.clientHeight
    const positions = (network as any).getPositions()
    for (const nodeId of Object.keys(positions)) {
        network.moveNode(nodeId, Math.random() * width, Math.random() * height)
    }
    network.stabilize(100)
}

// ---------- lifecycle ----------
onMounted(() => {
    document.addEventListener(
        'fullscreenchange',
        handleFullscreenChange,
    )
})

watch(
    () => props.visible,
    async (isVisible) => {
        if (isVisible && !initialized.value) {
            await nextTick()
            if (graphContainer.value && graphContainer.value.clientWidth > 0) {
                await buildGraph()
                initialized.value = true
            } else {
                // Retry after a short delay if container still not ready
                setTimeout(async () => {
                    if (graphContainer.value && graphContainer.value.clientWidth > 0) {
                        await buildGraph()
                        initialized.value = true
                    } else {
                        emit('error', 'Could not display graph.')
                        emit('loading', false)
                    }
                }, 200)
            }
        }
    },
    { immediate: true }   // important: check immediately in case it’s already visible
)

onUnmounted(() => {
    document.removeEventListener(
        'fullscreenchange',
        handleFullscreenChange,
    )

    if (network) {
        network.destroy()
        network = null
    }
})
</script>

<style scoped>
@media (max-height: 520px) {
    .graph-panel:not(:fullscreen) {
        height: 75vh;
        min-height: 320px;
    }
}
</style>