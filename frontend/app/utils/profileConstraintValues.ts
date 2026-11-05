export function getIndividualConstraintPayloadValue(
  value: unknown,
  multiple: boolean,
): string | string[] | undefined {
  const values = (
    Array.isArray(value)
      ? value
      : value == null || value === ''
        ? []
        : [value]
  )
    .map(String)
    .filter(item => item.trim() !== '')

  if (multiple) {
    return values
  }

  return values[0]
}