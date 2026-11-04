import { describe, expect, it } from 'vitest'

import {
  BCP47_LANGUAGE_TAG_OPTIONS,
  getBcp47LanguageTagLabel,
  isBcp47LanguageTagAvailable,
  isLanguageTagSelected,
  normalizeLanguageTagSelection,
  searchBcp47LanguageTags,
  toggleLanguageTagSelection,
} from '../app/utils/bcp47LanguageTags'

describe('BCP 47 language-tag catalogue', () => {
  it('provides a broad catalogue of complete locale identifiers', () => {
    expect(BCP47_LANGUAGE_TAG_OPTIONS.length).toBeGreaterThan(500)

    const values = BCP47_LANGUAGE_TAG_OPTIONS.map(
      option => option.value,
    )

    expect(values).toContain('en')
    expect(values).toContain('en-GB')
    expect(values).toContain('fa')
    expect(values).toContain('fa-AF')
    expect(values).toContain('sr-Latn')
    expect(values).toContain('zh-Hant')

    expect(new Set(values).size).toBe(values.length)
  })

  it('contains valid well-formed language tags', () => {
    for (const option of BCP47_LANGUAGE_TAG_OPTIONS) {
      expect(() => new Intl.Locale(option.value)).not.toThrow()
    }
  })

  it('provides human-readable language labels', () => {
    expect(getBcp47LanguageTagLabel('en')).toMatch(/English/i)
    expect(getBcp47LanguageTagLabel('fa')).toMatch(/Persian/i)
    expect(getBcp47LanguageTagLabel('en-GB')).not.toBe('en-GB')
  })

  it('searches by language tag', () => {
    const results = searchBcp47LanguageTags('fr-CA')

    expect(
      results.some(option => option.value === 'fr-CA'),
    ).toBe(true)
  })

  it('searches by language name', () => {
    const results = searchBcp47LanguageTags('Persian')

    expect(
      results.some(option => option.value === 'fa'),
    ).toBe(true)
  })
})

describe('language-tag selection', () => {
  it('normalizes scalar and array values without changing their order', () => {
    expect(
      normalizeLanguageTagSelection([
        'en',
        ' fr-CA ',
        '',
        'zh-Hant',
      ]),
    ).toEqual([
      'en',
      'fr-CA',
      'zh-Hant',
    ])

    expect(normalizeLanguageTagSelection('en')).toEqual(['en'])
    expect(normalizeLanguageTagSelection(null)).toEqual([])
  })

  it('adds a selected language tag', () => {
    expect(
      toggleLanguageTagSelection(
        ['en'],
        'fr-CA',
      ),
    ).toEqual([
      'en',
      'fr-CA',
    ])
  })

  it('removes an already selected language tag', () => {
    expect(
      toggleLanguageTagSelection(
        ['en', 'fr-CA', 'zh-Hant'],
        'fr-CA',
      ),
    ).toEqual([
      'en',
      'zh-Hant',
    ])
  })

  it('compares selected tags case-insensitively', () => {
    expect(
      isLanguageTagSelected(['EN-us'], 'en-US'),
    ).toBe(true)

    expect(
      toggleLanguageTagSelection(['EN-us'], 'en-US'),
    ).toEqual([])
  })

  it('preserves existing values outside the current catalogue', () => {
    const existing = ['x-private-example', 'en']

    expect(normalizeLanguageTagSelection(existing)).toEqual(existing)
    expect(
      isBcp47LanguageTagAvailable('x-private-example'),
    ).toBe(false)

    expect(
      getBcp47LanguageTagLabel('x-private-example'),
    ).toBe('x-private-example')
  })
})