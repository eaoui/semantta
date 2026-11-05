import { describe, expect, it } from 'vitest'

import {
  PROFILE_ENTITY_TAB_TYPES,
} from '../app/utils/profileEntityTabs'

describe('Application Profile entity tabs', () => {
  it('always includes the Individuals tab', () => {
    expect(PROFILE_ENTITY_TAB_TYPES).toContain('individual')
  })

  it('preserves the intended tab ordering', () => {
    expect(PROFILE_ENTITY_TAB_TYPES).toEqual([
      'class',
      'object_property',
      'datatype_property',
      'annotation_property',
      'datatype',
      'individual',
    ])
  })
})