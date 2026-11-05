import { describe, expect, it } from 'vitest'

import {
  getIndividualConstraintPayloadValue,
} from '../app/utils/profileConstraintValues'

describe('individual constraint serialization', () => {
  it('serializes multiple selections as URI arrays', () => {
    expect(
      getIndividualConstraintPayloadValue(
        ['urn:example:A', 'urn:example:B'],
        true,
      ),
    ).toEqual([
      'urn:example:A',
      'urn:example:B',
    ])
  })

  it('preserves an explicitly empty multiple selection', () => {
    expect(
      getIndividualConstraintPayloadValue([], true),
    ).toEqual([])
  })

  it('serializes a single selection as a scalar URI', () => {
    expect(
      getIndividualConstraintPayloadValue(
        ['urn:example:A'],
        false,
      ),
    ).toBe('urn:example:A')
  })

  it('does not serialize an empty single selection', () => {
    expect(
      getIndividualConstraintPayloadValue([], false),
    ).toBeUndefined()
  })

  it('filters empty URI values', () => {
    expect(
      getIndividualConstraintPayloadValue(
        ['urn:example:A', '', '  '],
        true,
      ),
    ).toEqual(['urn:example:A'])
  })

  it('normalizes a scalar selection', () => {
    expect(
      getIndividualConstraintPayloadValue(
        'urn:example:A',
        false,
      ),
    ).toBe('urn:example:A')
  })
})