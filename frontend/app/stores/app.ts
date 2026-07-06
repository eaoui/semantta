// stores/app.ts
import { defineStore } from 'pinia'
import type {
  OntologyInfo,
  Instance,
  MetadataFileInfo,
  ProfileEntityItem,
} from '@/types'

export const useAppStore = defineStore('app', () => {
  // ── Data ──────────────────────────────────────────────
  const ontologies = ref<OntologyInfo[]>([])
  const instances = ref<Instance[]>([])
  const prefixMap = ref<Record<string, string>>({})
  const metadataFiles = ref<MetadataFileInfo[]>([])
  const profileEntities = ref<ProfileEntityItem[]>([])
  const ontologyNamespaces = ref<string[]>([])
  const baseIri = ref('')
  const siteTitle = ref('Semantta')

  // ── UI state ──────────────────────────────────────────
  const displayFormat = ref('prefix')
  const metadataFilter = ref('')
  const loading = ref(true)
  const error = ref<string | null>(null)
  const isReady = ref(false)
  const publicShowBlankNodes = ref(false)

  // ── API helpers ───────────────────────────────────────
  const api = useApi()
  const apiBase = useRuntimeConfig().public.apiBase

  // ── State fetching ────────────────────────────────────
  async function fetchState() {
    loading.value = true
    try {
      const data = await api.fetchState()
      if (!data) throw new Error('Backend returned empty response')

      ontologies.value = data.ontologies
      instances.value = data.instances.filter(
        (inst) =>
          inst.uri &&
          inst.uri !== 'undefined' &&
          (inst.uri.startsWith('http') || inst.uri.startsWith('urn:'))
      )
      metadataFiles.value = data.metadata_files
      prefixMap.value = data.prefix_map
      displayFormat.value = data.display_format
      publicShowBlankNodes.value = data.public_display_blank_nodes
      profileEntities.value = data.profile_entities
      ontologyNamespaces.value = data.ontology_namespaces
      siteTitle.value = data.site_title || 'Semantta'
      baseIri.value = data.base_iri || ''

      error.value = null
      isReady.value = true
    } catch (e: any) {
      error.value = e?.message || 'Failed to load state'
      console.error('fetchState error:', e)
    } finally {
      loading.value = false
    }
  }

  // ── Ontology actions ──────────────────────────────────
  async function uploadOntology(file: File) {
    try {
      await api.uploadOntology(file)
      await fetchState()
    } catch (e: any) {
      // error already shown via toast
      throw e
    }
  }

  async function deleteOntology(filename: string) {
    loading.value = true
    try {
      await api.request(`/api/ontology/${encodeURIComponent(filename)}`, { method: 'DELETE' })
      await fetchState()
    } catch (e: any) {
      // error already shown via toast
    } finally {
      loading.value = false
    }
  }

  // ── Metadata actions ─────────────────────────────
  async function deleteMetadataFile(filename: string) {
    loading.value = true
    try {
      await api.request(`/api/metadata/${encodeURIComponent(filename)}`, { method: 'DELETE' })
      await fetchState()
    } catch (e: any) {
      // error already shown via toast
    } finally {
      loading.value = false
    }
  }

  async function toggleStar(uri: string) {
    const res = await $fetch<{ starred: boolean }>(`${apiBase}/api/instances/${encodeURIComponent(uri)}/star`, {
      method: 'POST',
    })
    // Update the local instance object
    const inst = instances.value.find(i => i.uri === uri)
    if (inst) {
      inst.starred = res.starred
    }
  }

  // ── Display preferences ───────────────────────────────
  async function setDisplayFormat(format: string) {
    displayFormat.value = format   // optimistic UI update
    await api.setDisplayFormat(format)
  }

  async function setPublicBlankNodesDisplay(show: boolean) {
    await $fetch(`${apiBase}/api/preferences/public/blank-nodes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ show }),
    })
    publicShowBlankNodes.value = show
  }

  // ── Instance CRUD ─────────────────────────────────────
  async function createInstance(payload: {
    classUris: string[]
    instanceUri: string
    properties: Record<string, string[]>
  }) {
    const res = await $fetch<{ uri: string }>(`${apiBase}/api/metadata/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        class_uris: payload.classUris,
        instance_uri: payload.instanceUri,
        properties: payload.properties,
      }),
    })
    addLocalInstance({
      uri: res.uri,
      types: payload.classUris,
      properties: payload.properties,
    })
  }

  async function updateInstance(uri: string, payload: any) {
    await $fetch(`${apiBase}/api/instances/${encodeURIComponent(uri)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
    removeLocalInstance(uri)
    addLocalInstance({
      uri,
      types: payload.class_uris,
      properties: payload.properties,
    })
  }

  async function deleteInstance(uri: string) {
    await api.request(`/api/instances/${encodeURIComponent(uri)}`, { method: 'DELETE' })
    removeLocalInstance(uri)
  }

  // ── Profile entity toggling (local updates) ───────────
  async function addClass(uri: string) {
    await $fetch(`${apiBase}/api/profile/toggle`, {
      method: 'POST',
      body: JSON.stringify({ uri, active: true }),
    })
    toggleLocalEntity(uri, true)
  }

  async function removeClass(uri: string) {
    await $fetch(`${apiBase}/api/profile/toggle`, {
      method: 'POST',
      body: JSON.stringify({ uri, active: false }),
    })
    toggleLocalEntity(uri, false)
  }

  async function addPropertyGlobal(uri: string) {
    await $fetch(`${apiBase}/api/profile/add-property-global`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prop_uri: uri }),
    })
    toggleLocalEntity(uri, true)
  }

  async function removePropertyGlobal(uri: string) {
    await $fetch(`${apiBase}/api/profile/remove-property-global`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prop_uri: uri }),
    })
    toggleLocalEntity(uri, false)
  }

  async function addIndividual(uri: string) {
    await $fetch(`${apiBase}/api/profile/add-individual`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uri }),
    })
    toggleLocalEntity(uri, true)
  }

  async function removeIndividual(uri: string) {
    await $fetch(`${apiBase}/api/profile/remove-individual`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uri }),
    })
    toggleLocalEntity(uri, false)
  }

  async function addDatatype(uri: string) {
    await $fetch(`${apiBase}/api/profile/add-datatype`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uri }),
    })
    toggleLocalEntity(uri, true)
  }

  async function removeDatatype(uri: string) {
    await $fetch(`${apiBase}/api/profile/remove-datatype`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uri }),
    })
    toggleLocalEntity(uri, false)
  }

  // ── Property–class linking ────────────────────────────
  async function addPropertyToClass(classUri: string, propUri: string) {
    await $fetch(`${apiBase}/api/profile/add-property`, {
      method: 'POST',
      body: JSON.stringify({ class_uri: classUri, prop_uri: propUri }),
    })
    await fetchState()
  }

  async function removePropertyFromClass(classUri: string, propUri: string) {
    await $fetch(`${apiBase}/api/profile/remove-property`, {
      method: 'POST',
      body: JSON.stringify({ class_uri: classUri, prop_uri: propUri }),
    })
    await fetchState()
  }

  async function getClassesForProperty(propUri: string): Promise<string[]> {
    const res = await $fetch<{ classes: string[] }>(
      `${apiBase}/api/profile/property-classes?uri=${encodeURIComponent(propUri)}`
    )
    return res.classes
  }

  // ── Profile generation ────────────────────────────────
  async function generateProfileFromMetadata() {
    try {
      await $fetch(`${apiBase}/api/profile/generate`, { method: 'POST' })
      await fetchState()
    } catch (e: any) {
      alert('Generation failed: ' + (e?.data?.detail || e.message))
    }
  }

  // ── Settings mutations ────────────────────────────────
  async function updateSiteTitle(newTitle: string) {
    await $fetch(`${apiBase}/api/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ site_title: newTitle }),
    })
    siteTitle.value = newTitle
  }

  async function updateBaseIri(iri: string) {
    await $fetch(`${apiBase}/api/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_iri: iri }),
    })
    baseIri.value = iri
  }

  // ── Local state helpers ───────────────────────────────
  function toggleLocalEntity(uri: string, active: boolean) {
    const entity = profileEntities.value.find((e) => e.uri === uri)
    if (entity) {
      entity.active = active
    }
  }

  function removeLocalInstance(uri: string) {
    instances.value = instances.value.filter((i) => i.uri !== uri)
  }

  function addLocalInstance(inst: {
    uri: string
    types: string[]
    properties: Record<string, string[]>
    label?: string
  }) {
    if (!instances.value.some((i) => i.uri === inst.uri)) {
      instances.value.push({
        uri: inst.uri,
        types: inst.types,
        properties: inst.properties,
        is_blank: inst.uri.startsWith('urn:bnid:') || inst.uri.startsWith('_:'),
        label: inst.label || null,
        source: 'created',
      })
    }
  }

  // ── Computed ──────────────────────────────────────────
  const filteredInstances = computed(() => {
    if (!metadataFilter.value) return instances.value
    return instances.value.filter((inst) =>
      inst.types.includes(metadataFilter.value)
    )
  })

  const typeOptions = computed(() => {
    const allTypes = instances.value.flatMap((inst) => inst.types)
    return [...new Set(allTypes)].sort()
  })

  // ── Deprecated / legacy ───────────────────────────────
  // keep setMetadataFilter for backwards compatibility
  function setMetadataFilter(type: string) {
    metadataFilter.value = type
  }

  // keep toggleProfileEntity (full refresh) for backwards compat
  async function toggleProfileEntity(uri: string, active: boolean) {
    await api.request('/api/profile/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uri, active }),
    })
    await fetchState()
  }

  // ── Return everything ─────────────────────────────────
  return {
    // state
    ontologies,
    instances,
    prefixMap,
    displayFormat,
    metadataFilter,
    loading,
    error,
    metadataFiles,
    profileEntities,
    ontologyNamespaces,
    siteTitle,
    baseIri,
    isReady,
    publicShowBlankNodes,

    // computed
    filteredInstances,
    typeOptions,

    // actions
    fetchState,
    uploadOntology,
    setDisplayFormat,
    setMetadataFilter,
    deleteOntology,
    deleteMetadataFile,
    toggleStar,
    toggleProfileEntity,
    deleteInstance,
    createInstance,
    updateInstance,
    addClass,
    removeClass,
    addPropertyToClass,
    removePropertyFromClass,
    getClassesForProperty,
    generateProfileFromMetadata,
    setPublicBlankNodesDisplay,
    updateSiteTitle,
    updateBaseIri,
    addPropertyGlobal,
    removePropertyGlobal,
    addIndividual,
    removeIndividual,
    addDatatype,
    removeDatatype,
  }
})