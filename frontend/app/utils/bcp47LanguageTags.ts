import availableLocales from 'cldr-core/availableLocales.json'

export interface Bcp47LanguageTagOption {
  value: string
  label: string
}

interface AvailableLocalesData {
  availableLocales: {
    full: string[]
  }
}

const localeTags = (
  availableLocales as unknown as AvailableLocalesData
).availableLocales.full

if (!Array.isArray(localeTags) || localeTags.length === 0) {
  throw new Error('The CLDR language-tag catalogue is unavailable.')
}

const displayNames = new Intl.DisplayNames(['en'], {
  type: 'language',
})

const collator = new Intl.Collator('en', {
  sensitivity: 'base',
})

function getDisplayName(tag: string): string {
  try {
    return displayNames.of(tag) || tag
  } catch {
    return tag
  }
}

const options = Array.from(new Set(localeTags))
  .map(value => ({
    value,
    label: getDisplayName(value),
  }))
  .sort((left, right) =>
    collator.compare(left.label, right.label) ||
    collator.compare(left.value, right.value),
  )

export const BCP47_LANGUAGE_TAG_OPTIONS:
  readonly Bcp47LanguageTagOption[] = Object.freeze(options)

const optionByTag = new Map(
  BCP47_LANGUAGE_TAG_OPTIONS.map(option => [
    option.value.toLowerCase(),
    option,
  ]),
)

export function getBcp47LanguageTagLabel(tag: string): string {
  return optionByTag.get(tag.toLowerCase())?.label ?? tag
}

export function isBcp47LanguageTagAvailable(tag: string): boolean {
  return optionByTag.has(tag.toLowerCase())
}

export function searchBcp47LanguageTags(
  query: string,
): Bcp47LanguageTagOption[] {
  const normalizedQuery = query.trim().toLowerCase()

  if (!normalizedQuery) {
    return [...BCP47_LANGUAGE_TAG_OPTIONS]
  }

  return BCP47_LANGUAGE_TAG_OPTIONS.filter(option =>
    option.value.toLowerCase().includes(normalizedQuery) ||
    option.label.toLowerCase().includes(normalizedQuery),
  )
}

export function normalizeLanguageTagSelection(
  value: unknown,
): string[] {
  const values = Array.isArray(value)
    ? value
    : value == null || value === ''
      ? []
      : [value]

  return values
    .filter((item): item is string => typeof item === 'string')
    .map(item => item.trim())
    .filter(Boolean)
}

export function isLanguageTagSelected(
  values: unknown,
  tag: string,
): boolean {
  const normalizedTag = tag.toLowerCase()

  return normalizeLanguageTagSelection(values)
    .some(value => value.toLowerCase() === normalizedTag)
}

export function toggleLanguageTagSelection(
  values: unknown,
  tag: string,
): string[] {
  const selected = normalizeLanguageTagSelection(values)

  if (isLanguageTagSelected(selected, tag)) {
    return selected.filter(
      value => value.toLowerCase() !== tag.toLowerCase(),
    )
  }

  return [...selected, tag]
}