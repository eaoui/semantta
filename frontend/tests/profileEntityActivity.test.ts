import { describe, expect, it } from 'vitest'

import {
  isInactiveProfileEntity,
} from '../app/utils/profileEntityActivity'

const entities = [
  {
    uri: 'urn:example:ActiveClass',
    active: true,
  },
  {
    uri: 'urn:example:InactiveClass',
    active: false,
  },
  {
    uri: 'urn:example:ActiveProperty',
    active: true,
  },
  {
    uri: 'urn:example:InactiveProperty',
    active: false,
  },
]

describe('profile entity activity', () => {
  it('identifies inactive entities', () => {
    expect(
      isInactiveProfileEntity(
        'urn:example:InactiveClass',
        entities,
      ),
    ).toBe(true)

    expect(
      isInactiveProfileEntity(
        'urn:example:InactiveProperty',
        entities,
      ),
    ).toBe(true)
  })

  it('does not identify active entities as inactive', () => {
    expect(
      isInactiveProfileEntity(
        'urn:example:ActiveClass',
        entities,
      ),
    ).toBe(false)
  })

  it('does not treat unknown entities as inactive', () => {
    expect(
      isInactiveProfileEntity(
        'urn:example:UnknownEntity',
        entities,
      ),
    ).toBe(false)
  })

  it('matches entities by their exact URI', () => {
    expect(
      isInactiveProfileEntity(
        'urn:example:InactiveClass/',
        entities,
      ),
    ).toBe(false)
  })

  it('responds to changes in entity activity state', () => {
    const mutableEntities = [
      {
        uri: 'urn:example:Class',
        active: true,
      },
    ]

    expect(
      isInactiveProfileEntity(
        'urn:example:Class',
        mutableEntities,
      ),
    ).toBe(false)

    mutableEntities[0]!.active = false

    expect(
      isInactiveProfileEntity(
        'urn:example:Class',
        mutableEntities,
      ),
    ).toBe(true)
  })
})