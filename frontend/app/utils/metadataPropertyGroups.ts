export interface MetadataPropertyOrdering {
  uri: string
  groupUri: string
  groupLabel: string
  groupOrder: number
  order: number | null
}

export interface MetadataPropertyGroup<
  T extends MetadataPropertyOrdering,
> {
  uri: string
  label: string
  order: number
  properties: T[]
}

function compareNullableOrder(
  first: number | null,
  second: number | null,
): number {
  if (first === null) {
    return second === null ? 0 : 1
  }

  if (second === null) {
    return -1
  }

  return first - second
}

export function groupMetadataProperties<
  T extends MetadataPropertyOrdering,
>(
  properties: readonly T[],
): MetadataPropertyGroup<T>[] {
  const groups = new Map<string, MetadataPropertyGroup<T>>()

  for (const property of properties) {
    let group = groups.get(property.groupUri)

    if (!group) {
      group = {
        uri: property.groupUri,
        label: property.groupLabel,
        order: property.groupOrder,
        properties: [],
      }

      groups.set(property.groupUri, group)
    }

    group.properties.push(property)
  }

  return Array.from(groups.values())
    .map(group => ({
      ...group,
      properties: [...group.properties].sort((a, b) =>
        compareNullableOrder(a.order, b.order) ||
        a.uri.localeCompare(b.uri),
      ),
    }))
    .sort((a, b) =>
      a.order - b.order ||
      a.uri.localeCompare(b.uri),
    )
}