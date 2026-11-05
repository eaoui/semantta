import { describe, expect, it } from 'vitest'

import {
  getActiveIndividualOptions,
  getNextEntitySelection,
} from '../app/utils/entitySelector'

import {
  constraintConfig,
} from '../app/utils/constraintConfig'

const SH_IN = 'http://www.w3.org/ns/shacl#in'
const SH_HAS_VALUE = 'http://www.w3.org/ns/shacl#hasValue'

describe('EntitySelector individual options', () => {
  it('returns only active Application Profile individuals', () => {
    const entities = [
      {
        uri: 'urn:example:Person1',
        label: 'Person One',
        type: 'individual',
        active: true,
      },
      {
        uri: 'urn:example:Person2',
        label: 'Person Two',
        type: 'individual',
        active: false,
      },
      {
        uri: 'urn:example:Person3',
        label: null,
        type: 'individual',
        active: true,
      },
      {
        uri: 'urn:example:Person',
        label: 'Person',
        type: 'class',
        active: true,
      },
      {
        uri: 'urn:example:Property',
        label: 'Property',
        type: 'object_property',
        active: true,
      },
      {
        uri: 'urn:example:MetadataRecord',
        label: 'Metadata Record',
        type: 'instance',
        active: true,
      },
    ]

    expect(getActiveIndividualOptions(entities)).toEqual([
      {
        uri: 'urn:example:Person1',
        label: 'Person One',
      },
      {
        uri: 'urn:example:Person3',
        label: null,
      },
    ])
  })

  it('returns an empty list when no active individuals exist', () => {
    expect(
      getActiveIndividualOptions([
        {
          uri: 'urn:example:Person',
          type: 'individual',
          active: false,
        },
      ]),
    ).toEqual([])
  })
})

describe('EntitySelector selection cardinality', () => {
  it('adds an individual in multiple-selection mode', () => {
    expect(
      getNextEntitySelection(
        ['urn:example:Person1'],
        'urn:example:Person2',
        true,
      ),
    ).toEqual([
      'urn:example:Person1',
      'urn:example:Person2',
    ])
  })

  it('replaces the existing selection in single-selection mode', () => {
    expect(
      getNextEntitySelection(
        ['urn:example:Person1'],
        'urn:example:Person2',
        false,
      ),
    ).toEqual([
      'urn:example:Person2',
    ])
  })

  it('does not introduce duplicate selections', () => {
    expect(
      getNextEntitySelection(
        ['urn:example:Person1'],
        'urn:example:Person1',
        true,
      ),
    ).toEqual([
      'urn:example:Person1',
    ])
  })

  it('preserves an existing selection when a different option is not added', () => {
    const existing = ['urn:example:Person1']

    expect(
      getNextEntitySelection(
        existing,
        'urn:example:Person1',
        false,
      ),
    ).toEqual(existing)
  })
})

describe('object-property constraint selector configuration', () => {
  it('configures sh:in as a multiple individual selector', () => {
    expect(constraintConfig[SH_IN]).toMatchObject({
      label: 'Allowed Values',
      type: 'individual',
      multiple: true,
      appliesTo: ['object_property'],
    })
  })

  it('configures sh:hasValue as a single individual selector', () => {
    expect(constraintConfig[SH_HAS_VALUE]).toMatchObject({
      label: 'Required Value',
      type: 'individual',
      appliesTo: ['object_property'],
    })

    expect(constraintConfig[SH_HAS_VALUE]?.multiple).toBeUndefined()
  })
})