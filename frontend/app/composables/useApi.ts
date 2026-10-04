import type {
  StateResponse,
  InstanceListOptions,
  InstanceListResponse,
} from '@/types'

/**
 * Thin wrapper around the backend REST API.
 * Provides typed request helpers and common operations.
 */
export const useApi = () => {
  const config = useRuntimeConfig()
  const baseURL = config.public.apiBase as string

  async function request<T>(path: string, options?: RequestInit): Promise<T> {
    const url = `${baseURL}${path}`
    console.log(`[API] ${options?.method || 'GET'} ${url}`)
    const res = await fetch(url, options)
    if (!res.ok) {
      const body = await res.text()
      let detail = body
      try {
        const parsed = JSON.parse(body)
        if (parsed.detail) detail = parsed.detail
      } catch {
        // body is not JSON – keep as plain text
      }
      const error = new Error(detail) as any
      error.data = { detail }
      error.status = res.status
      throw error
    }
    return res.json()
  }

  const fetchState = (): Promise<StateResponse> =>
    request('/api/state')

  const fetchInstances = (
    options: InstanceListOptions = {},
  ) => {
    const params = new URLSearchParams()

    if (options.limit != null) {
      params.set(
        'limit',
        String(options.limit),
      )
    }

    if (options.cursor) {
      params.set('cursor', options.cursor)
    }

    if (options.search?.trim()) {
      params.set(
        'search',
        options.search.trim(),
      )
    }

    if (options.typeUri) {
      params.set(
        'type_uri',
        options.typeUri,
      )
    }

    if (
      options.source &&
      options.source !== 'all'
    ) {
      params.set(
        'source',
        options.source,
      )
    }

    if (options.starred) {
      params.set(
        'starred',
        'true',
      )
    }

    if (options.includeBlankNodes) {
      params.set(
        'include_blank_nodes',
        'true',
      )
    }

    const query = params.toString()

    return request<InstanceListResponse>(
      `/api/instances${query ? `?${query}` : ''
      }`,
    )
  }

  const fetchInstanceTypes = () =>
    request<{ types: string[] }>(
      '/api/instances/types',
    )

  const uploadOntology = (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ status: string; filename: string }>('/api/ontology/upload', {
      method: 'POST',
      body: form,
    })
  }

  const setDisplayFormat = (format: string) => {
    const form = new FormData()
    form.append('format', format)
    return request<{ status: string }>('/api/display-format', {
      method: 'POST',
      body: form,
    })
  }

  return {
    fetchState,
    fetchInstances,
    fetchInstanceTypes,
    uploadOntology,
    setDisplayFormat,
    request,
  }
}