<template>
    <div>
        <!-- Controls -->
        <div class="flex flex-wrap items-center gap-3 mb-3">
            <input v-model="graphSearchQuery" type="text" placeholder="Search node…"
                class="border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                @input="handleGraphSearch" />

            <select v-model="graphLayout" @change="changeLayout"
                class="border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100">
                <option value="force">Force‑directed</option>
                <option value="hierarchical">Hierarchical</option>
            </select>

            <button @click="togglePhysics"
                class="text-sm px-3 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600">
                {{ physicsEnabled ? 'Freeze layout' : 'Resume layout' }}
            </button>

            <label class="flex items-center gap-1 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
                <input type="checkbox" v-model="showBlankNodes" @change="rebuildGraph" class="h-4 w-4" />
                Show blank nodes
            </label>

            <button @click="fitGraph"
                class="text-sm px-3 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600">
                Reset view
            </button>

            <button @click="shuffleLayout"
                class="text-sm px-3 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600">
                Shuffle layout
            </button>
        </div>

        <div class="w-full h-150 border rounded" ref="graphContainer"></div>
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
const graphContainer = ref<HTMLElement | null>(null)
let network: Network | null = null
const initialized = ref(false)

// ---------- helpers ----------
function isPassThroughBlankNode(bnodeUri: string, propertyUri: string): boolean {
    const bnode = props.bnodeData?.[bnodeUri]
    if (!bnode) return false
    if (bnode.types && bnode.types.length > 0) return false
    const props_ = bnode.properties || {}
    const propKeys = Object.keys(props_)
    return propKeys.length === 1 && propKeys[0] === propertyUri
}

function getBlankNodeLabel(uri: string): string {
    const bnode = props.bnodeData?.[uri]
    if (bnode?.types?.length) {
        return bnode.types.map((t: string) => props.formatUri(t)).join(', ')
    }
    return 'Blank Node'
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
        const edgeSet = new Set<string>()   // "from|||label|||to"

        if (!props.isBlankNode(props.instanceUri)) {
            allUris.add(props.instanceUri)
        }

        // ---- direct properties ----
        for (const [pred, vals] of Object.entries(props.instanceProperties)) {
            const predLabel = props.formatUri(pred)
            for (const val of vals as string[]) {
                if (!val.startsWith('http://') && !val.startsWith('urn:')) continue
                if (!showBlankNodes.value && props.isBlankNode(val)) continue

                // pass‑through blank node?
                if (props.isBlankNode(val) && isPassThroughBlankNode(val, pred)) {
                    const bnode = props.bnodeData?.[val]
                    if (bnode?.properties?.[pred]) {
                        for (const subVal of bnode.properties[pred]) {
                            if (subVal.startsWith('http://') || subVal.startsWith('urn:')) {
                                allUris.add(subVal)
                                const edgeKey = `${props.instanceUri}|||${predLabel}|||${subVal}`
                                if (!edgeSet.has(edgeKey)) edgeSet.add(edgeKey)
                            }
                        }
                    }
                    continue
                }

                allUris.add(val)
                edgeSet.add(`${props.instanceUri}|||${predLabel}|||${val}`)
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
                const bpredLabel = props.formatUri(bpred)
                for (const bval of bvals as string[]) {
                    if (bval.startsWith('http://') || bval.startsWith('urn:')) {
                        if (!showBlankNodes.value && props.isBlankNode(bval)) continue
                        allUris.add(bval)
                        const edgeKey = `${uri}|||${bpredLabel}|||${bval}`
                        if (!edgeSet.has(edgeKey)) edgeSet.add(edgeKey)
                    }
                }
            }
        }

        // ---- nodes ----
        const nodes: any[] = []
        for (const uri of allUris) {
            const isBlank = props.isBlankNode(uri)
            const isMain = uri === props.instanceUri
            nodes.push({
                id: uri,
                label: isBlank ? getBlankNodeLabel(uri) : props.getDisplayLabel(uri),
                font: { size: 12 },
                color: isMain
                    ? { background: '#3B82F6', border: '#1E40AF' }
                    : isBlank
                        ? { background: '#FEF3C7', border: '#D97706' }
                        : { background: '#E5E7EB', border: '#9CA3AF' },
                shape: isMain ? 'box' : 'ellipse',
                size: isMain ? 30 : isBlank ? 18 : 20,
            })
        }

        // ---- edges ----
        const edges: any[] = []
        const isDark = document.documentElement.classList.contains('dark')
        for (const key of edgeSet) {
            const [from, label, to] = key.split('|||')
            edges.push({
                from,
                to,
                label,
                font: {
                    size: 10,
                    color: isDark ? '#D1D5DB' : '#6B7280',
                    background: isDark ? '#111827' : '#FFFFFF',
                    strokeWidth: 0,
                },
                arrows: 'to',
            })
        }

        const data = { nodes, edges }
        const options = {
            layout: {
                improvedLayout: true,
                hierarchical: graphLayout.value === 'hierarchical',
            },
            edges: { smooth: { enabled: true, type: 'curvedCW', roundness: 0.2 } },
            physics: { enabled: physicsEnabled.value, solver: 'forceAtlas2Based' },
            interaction: { hover: true, zoomView: true },
        }
        network = new Network(container, data, options)
    } catch (e: any) {
        emit('error', e.message || 'Graph creation failed')
    } finally {
        emit('loading', false)
    }
}

function rebuildGraph() {
    // simply re‑run build (used by checkbox)
    buildGraph()
}

// ---------- control functions ----------
function handleGraphSearch() {
    if (!network) return
    const q = graphSearchQuery.value.toLowerCase().trim()
    if (!q) {
        network.selectNodes([])
        network.fit({ animation: true })
        return
    }
    const allNodes = (network as any).body.data.nodes.get()
    const found = allNodes.find((n: any) => {
        const label = n.label || ''
        return label.toLowerCase().includes(q)
    })
    if (found) {
        network.selectNodes([found.id])
        network.focus(found.id, { scale: 1.2, animation: true })
    } else {
        network.selectNodes([])
    }
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
    if (network) {
        network.destroy()
        network = null
    }
})
</script>