import { computed } from 'vue'
import { useAppStore } from '@/stores/app'

/**
 * Normalize only trailing namespace delimiters.
 * HTTP and HTTPS remain distinct.
 */
export function normalizeOntologyNamespace(uri: string): string {
  return uri.replace(/[\/#]+$/, '')
}

export function useOntologyNamespaceMatching() {
  const store = useAppStore()

  const ontologyNamespaces = computed(() => {
    const namespaces = new Set<string>()

    for (const ontology of store.ontologies) {
      const iri = ontology.iri
      if (!iri) continue

      // Match the ontology IRI itself.
      namespaces.add(normalizeOntologyNamespace(iri))

      // Preserve the existing base-namespace matching behavior.
      const idx = Math.max(
        iri.lastIndexOf('/'),
        iri.lastIndexOf('#'),
      )

      const baseNamespace =
        idx >= 0 ? iri.substring(0, idx + 1) : iri

      namespaces.add(
        normalizeOntologyNamespace(baseNamespace),
      )
    }

    return namespaces
  })

  function isOntologyNamespaceMatch(namespace: string): boolean {
    return ontologyNamespaces.value.has(
      normalizeOntologyNamespace(namespace),
    )
  }

  return { isOntologyNamespaceMatch }
}