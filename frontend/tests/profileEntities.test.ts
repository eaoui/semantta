import { describe, expect, it } from 'vitest'

import type { ProfileEntityItem } from '../app/types'

import {
  getClassPropertyOptions,
  getProfileEntityDisplayLabel,
} from '../app/utils/profileEntities'

const entities: ProfileEntityItem[] = [
  {
    uri: 'urn:property:direct',
    label: 'Direct Property',
    type: 'object_property',
    active: true,
    in_onto: true,
  },
  {
    uri: 'urn:property:inherited',
    label: 'Inherited Property',
    type: 'datatype_property',
    active: true,
    in_onto: true,
  },
  {
    uri: 'urn:property:universal',
    label: 'Universal Property',
    type: 'annotation_property',
    active: true,
    in_onto: true,
  },
  {
    uri: 'urn:property:inactive',
    label: 'Inactive Property',
    type: 'object_property',
    active: false,
    in_onto: true,
  },
  {
    uri: 'urn:class:example',
    label: 'Example Class',
    type: 'class',
    active: true,
    in_onto: true,
  },
]

describe('class property options', () => {
  it('excludes inherited and universal properties', () => {
    const result = getClassPropertyOptions(
      entities,
      ['urn:property:inherited'],
      ['urn:property:universal'],
    )

    expect(result).toEqual([
      {
        uri: 'urn:property:direct',
        label: 'Direct Property',
      },
    ])
  })

  it('excludes inactive entities and non-property entities', () => {
    const result = getClassPropertyOptions(
      entities,
      [],
      [],
    )

    expect(result.map(item => item.uri)).toEqual([
      'urn:property:direct',
      'urn:property:inherited',
      'urn:property:universal',
    ])
  })

  it('uses the URI when an entity has no label', () => {
    const result = getClassPropertyOptions(
      [{
        ...entities[0]!,
        label: null,
      }],
      [],
      [],
    )

    expect(result[0]?.label).toBe('urn:property:direct')
  })

  it('preserves the original ordering of eligible properties', () => {
    const result = getClassPropertyOptions(
      entities,
      [],
      [],
    )

    expect(result.map(item => item.uri)).toEqual([
      'urn:property:direct',
      'urn:property:inherited',
      'urn:property:universal',
    ])
  })
})

describe('profile entity display labels', () => {
  const formatUri = (uri: string, format?: string) => {
    if (format === 'label') return 'Local Name'
    if (format === 'prefix') return `ex:${uri.split(':').pop()}`
    return uri
  }

  it('uses the ontology label in label mode', () => {
    expect(
      getProfileEntityDisplayLabel(
        'urn:example:Book',
        'label',
        formatUri,
        'Book',
      ),
    ).toBe('Book')
  })

  it('falls back to the formatted local name in label mode', () => {
    expect(
      getProfileEntityDisplayLabel(
        'urn:example:Book',
        'label',
        formatUri,
      ),
    ).toBe('Local Name')
  })

  it('uses the configured URI format outside label mode', () => {
    expect(
      getProfileEntityDisplayLabel(
        'urn:example:Book',
        'prefix',
        formatUri,
      ),
    ).toBe('ex:Book')
  })

  it('preserves the full URI in IRI mode', () => {
    expect(
      getProfileEntityDisplayLabel(
        'urn:example:Book',
        'iri',
        formatUri,
      ),
    ).toBe('urn:example:Book')
  })
})