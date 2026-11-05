import { describe, expect, it } from 'vitest'

import {
  groupMetadataProperties,
} from '../app/utils/metadataPropertyGroups'

describe('metadata property grouping', () => {
  const annotationProperty = {
    uri: 'urn:property:annotation',
    groupUri: 'urn:group:annotation',
    groupLabel: 'Annotation Properties',
    groupOrder: 1,
    order: 1,
  }

  const objectPropertyFirst = {
    uri: 'urn:property:object-first',
    groupUri: 'urn:group:object',
    groupLabel: 'Object Properties',
    groupOrder: 2,
    order: 1,
  }

  const objectPropertySecond = {
    uri: 'urn:property:object-second',
    groupUri: 'urn:group:object',
    groupLabel: 'Object Properties',
    groupOrder: 2,
    order: 2,
  }

  const datatypeProperty = {
    uri: 'urn:property:datatype',
    groupUri: 'urn:group:datatype',
    groupLabel: 'Datatype Properties',
    groupOrder: 3,
    order: 1,
  }

  it('groups properties by their group URI', () => {
    const result = groupMetadataProperties([
      annotationProperty,
      objectPropertyFirst,
      objectPropertySecond,
      datatypeProperty,
    ])

    expect(result).toHaveLength(3)

    expect(result.map(group => group.uri)).toEqual([
      'urn:group:annotation',
      'urn:group:object',
      'urn:group:datatype',
    ])
  })

  it('sorts groups by group order', () => {
    const result = groupMetadataProperties([
      datatypeProperty,
      objectPropertyFirst,
      annotationProperty,
    ])

    expect(result.map(group => group.order)).toEqual([
      1,
      2,
      3,
    ])
  })

  it('sorts properties by their order within each group', () => {
    const result = groupMetadataProperties([
      objectPropertySecond,
      objectPropertyFirst,
    ])

    expect(
      result[0]?.properties.map(property => property.uri),
    ).toEqual([
      'urn:property:object-first',
      'urn:property:object-second',
    ])
  })

  it('places unordered properties at the end of their group', () => {
    const unorderedProperty = {
      ...objectPropertyFirst,
      uri: 'urn:property:unordered',
      order: null,
    }

    const result = groupMetadataProperties([
      unorderedProperty,
      objectPropertySecond,
      objectPropertyFirst,
    ])

    expect(
      result[0]?.properties.map(property => property.uri),
    ).toEqual([
      'urn:property:object-first',
      'urn:property:object-second',
      'urn:property:unordered',
    ])
  })

  it('uses property URI as a deterministic tie-breaker', () => {
    const first = {
      ...objectPropertyFirst,
      uri: 'urn:property:a',
      order: 1,
    }

    const second = {
      ...objectPropertyFirst,
      uri: 'urn:property:b',
      order: 1,
    }

    const result = groupMetadataProperties([
      second,
      first,
    ])

    expect(
      result[0]?.properties.map(property => property.uri),
    ).toEqual([
      'urn:property:a',
      'urn:property:b',
    ])
  })

  it('preserves original property objects and their values', () => {
    const property = {
      ...objectPropertyFirst,
      values: ['existing metadata value'],
    }

    const result = groupMetadataProperties([property])

    const groupedProperty = result[0]?.properties[0]

    expect(groupedProperty).toBe(property)
    expect(groupedProperty?.uri).toBe(property.uri)
    expect(groupedProperty?.values).toEqual([
      'existing metadata value',
    ])
  })

  it('does not modify the original property array', () => {
    const properties = [
      datatypeProperty,
      objectPropertySecond,
      annotationProperty,
    ]

    const originalOrder = properties.map(
      property => property.uri,
    )

    groupMetadataProperties(properties)

    expect(
      properties.map(property => property.uri),
    ).toEqual(originalOrder)
  })

  it('returns no groups for an empty property list', () => {
    expect(groupMetadataProperties([])).toEqual([])
  })
})