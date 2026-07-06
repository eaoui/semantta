import type { StateResponse } from '@/types'

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

  return { fetchState, uploadOntology, setDisplayFormat, request }
}