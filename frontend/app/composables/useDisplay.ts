/**
 * URI display formatting utilities.
 * Respects the user‑selected display format (IRI, label, prefix)
 * and the global prefix map from the Pinia store.
 */
export const useDisplay = () => {
  const store = useAppStore()

  const formatUri = (uri: string, format?: string): string => {
    const fmt = format || store.displayFormat
    if (!fmt || fmt === 'iri') return uri

    if (fmt === 'label') {
      const parts = uri.split(/[/#]/)
      return parts[parts.length - 1] || uri
    }

    if (fmt === 'prefix') {
      const entries = Object.entries(store.prefixMap)
        .sort(([namespaceA], [namespaceB]) =>
          namespaceB.length - namespaceA.length,
        )

      for (const [namespace, prefix] of entries) {
        if (!namespace || !uri.startsWith(namespace)) continue

        const local = uri.slice(namespace.length)

        if (local) return `${prefix}:${local}`
        return prefix
      }
    }

    return uri
  }

  return { formatUri }
}