import { describe, expect, it } from 'vitest'

import {
  shouldShowEmptyShInNotice,
} from '../app/utils/profileConstraintNotices'

const SH_IN_URI = 'http://www.w3.org/ns/shacl#in'

describe('empty sh:in warning', () => {
  it('shows the warning for an empty explicit override', () => {
    expect(
      shouldShowEmptyShInNotice(
        SH_IN_URI,
        [],
        'override',
      ),
    ).toBe(true)
  })

  it('does not show the warning in default mode', () => {
    expect(
      shouldShowEmptyShInNotice(
        SH_IN_URI,
        [],
        'default',
      ),
    ).toBe(false)
  })

  it('does not show the warning when the override has values', () => {
    expect(
      shouldShowEmptyShInNotice(
        SH_IN_URI,
        ['urn:example:Draft'],
        'override',
      ),
    ).toBe(false)
  })

  it('does not show the warning for other fields', () => {
    expect(
      shouldShowEmptyShInNotice(
        'http://www.w3.org/ns/shacl#class',
        [],
        'override',
      ),
    ).toBe(false)
  })

  it('does not show the warning for undefined or non-array values', () => {
    expect(
      shouldShowEmptyShInNotice(
        SH_IN_URI,
        undefined,
        'override',
      ),
    ).toBe(false)

    expect(
      shouldShowEmptyShInNotice(
        SH_IN_URI,
        null,
        'override',
      ),
    ).toBe(false)
  })
})