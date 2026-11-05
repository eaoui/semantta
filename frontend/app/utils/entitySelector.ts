export interface ProfileEntityOptionSource {
  uri: string
  label?: string | null
  type: string
  active: boolean
}

export interface EntityOption {
  uri: string
  label?: string | null
}

export function getActiveIndividualOptions(
  entities: readonly ProfileEntityOptionSource[],
): EntityOption[] {
  return entities
    .filter(entity =>
      entity.active && entity.type === 'individual',
    )
    .map(entity => ({
      uri: entity.uri,
      label: entity.label,
    }))
}

export function getNextEntitySelection(
  current: readonly string[],
  uri: string,
  multiple: boolean,
): string[] {
  if (current.includes(uri)) {
    return [...current]
  }

  return multiple
    ? [...current, uri]
    : [uri]
}