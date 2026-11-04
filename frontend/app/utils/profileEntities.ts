import type { ProfileEntityItem } from '@/types'

const PROPERTY_TYPES = new Set([
  'object_property',
  'datatype_property',
  'annotation_property',
])

export interface ProfilePropertyOption {
  uri: string
  label: string
}

export function getClassPropertyOptions(
  profileEntities: readonly ProfileEntityItem[],
  inheritedPropertyUris: readonly string[],
  universalPropertyUris: readonly string[],
): ProfilePropertyOption[] {
  const excludedProperties = new Set([
    ...inheritedPropertyUris,
    ...universalPropertyUris,
  ])

  return profileEntities
    .filter(entity =>
      entity.active &&
      PROPERTY_TYPES.has(entity.type) &&
      !excludedProperties.has(entity.uri)
    )
    .map(entity => ({
      uri: entity.uri,
      label: entity.label || entity.uri,
    }))
}

export function getProfileEntityDisplayLabel(
  uri: string,
  displayFormat: string,
  formatUri: (uri: string, format?: string) => string,
  explicitLabel?: string | null,
): string {
  if (displayFormat === 'label') {
    return explicitLabel || formatUri(uri, 'label') || uri
  }

  return formatUri(uri, displayFormat) || uri
}