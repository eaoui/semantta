const SH_IN_URI = 'http://www.w3.org/ns/shacl#in'

export type ProfileFieldMode = 'default' | 'override'

export function shouldShowEmptyShInNotice(
  predicateUri: string,
  value: unknown,
  mode: ProfileFieldMode | undefined,
): boolean {
  return (
    predicateUri === SH_IN_URI &&
    mode === 'override' &&
    Array.isArray(value) &&
    value.length === 0
  )
}