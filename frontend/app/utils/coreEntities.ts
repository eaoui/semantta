// utils/coreEntities.ts
// The set of core entity URIs that are always present and cannot be removed.
// Mirrors the backend's CORE_ACTIVE_DATATYPES + CORE_ACTIVE_ANNOTATION_PROPERTIES.

export const CORE_ENTITY_URIS = new Set([
  // Core datatypes
  'http://www.w3.org/2001/XMLSchema#string',
  'http://www.w3.org/2001/XMLSchema#boolean',
  'http://www.w3.org/2001/XMLSchema#decimal',
  'http://www.w3.org/2001/XMLSchema#integer',
  'http://www.w3.org/2000/01/rdf-schema#Literal',
  // Core annotation properties
  'http://www.w3.org/2000/01/rdf-schema#label',
  'http://www.w3.org/2000/01/rdf-schema#comment',
  'http://www.w3.org/2000/01/rdf-schema#seeAlso',
  'http://www.w3.org/2000/01/rdf-schema#isDefinedBy',
])