import type { ProfileEntityItem } from '@/types'

export function isInactiveProfileEntity(
  uri: string,
  entities: readonly Pick<ProfileEntityItem, 'uri' | 'active'>[],
): boolean {
  return entities.find(entity => entity.uri === uri)?.active === false
}