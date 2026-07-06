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
      const pm = store.prefixMap
      for (const ns in pm) {
        if (uri.startsWith(ns)) {
          const local = uri.slice(ns.length)
          const prefix = pm[ns]!            // safe – we're iterating over defined keys
          return local ? `${prefix}:${local}` : prefix
        }
      }
    }

    return uri
  }

  return { formatUri }
}