// types/index.ts
// Shared TypeScript interfaces matching the backend's JSON responses.

export interface NamespaceInfo {
  prefix: string
  namespace: string
}

export interface OntologyInfo {
  filename: string
  title: string
  version: string
  iri: string
  namespaces: string[]
}

export interface MetadataFileInfo {
  filename: string
  primary_iri: string | null
  namespaces: string[]
  instances_count: number
  triples_count: number
  vocab_integrated: boolean
  instances_merged: boolean
}

export interface Instance {
  uri: string
  types: string[]
  properties: Record<string, string[]>
  is_blank: boolean
  label?: string | null
  source?: string
  starred?: boolean
}

export interface ProfileEntityItem {
  uri: string
  type: string
  in_onto: boolean
  active: boolean
  types?: string[]
  domain?: string[]
  ontology?: string
  sources?: string[]
  order?: number
}

export interface StateResponse {
  ontologies: OntologyInfo[]
  instances: Instance[]
  instance_count: number
  display_format: string
  public_display_blank_nodes: boolean
  prefix_map: Record<string, string>
  metadata_files: MetadataFileInfo[]
  profile_entities: ProfileEntityItem[]
  ontology_namespaces: string[]
  site_title?: string
  base_iri?: string
}

export interface InstanceListResponse {
  instances: Instance[]
  has_more: boolean
  next_cursor: string | null
  limit: number
  cursor: string | null
}

export interface InstanceListOptions {
  limit?: number
  cursor?: string
  search?: string
  typeUri?: string
  source?: 'all' | 'imported' | 'created'
  starred?: boolean
  includeBlankNodes?: boolean
}