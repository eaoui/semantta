// utils/constraintConfig.ts
// Defines the editable SHACL constraints, their UI input types,
// and the entity types each constraint applies to.

export const constraintConfig: Record<
  string,
  {
    label: string
    type: 'class' | 'integer' | 'boolean' | 'text' | 'number' | 'dropdown' | 'datatype' | 'property'
    multiple?: boolean
    appliesTo: string[]
    options?: string[]
  }
> = {
  'http://www.w3.org/ns/shacl#property': {
    label: 'Properties',
    type: 'property',
    multiple: true,
    appliesTo: ['class'],
  },
  'urn:domainClasses': {
    label: 'Domain Classes',
    type: 'class',
    multiple: true,
    appliesTo: ['object_property', 'datatype_property', 'annotation_property'],
  },
  'http://www.w3.org/ns/shacl#class': {
    label: 'Range Classes',
    type: 'class',
    appliesTo: ['object_property', 'annotation_property'],
  },
  'http://www.w3.org/ns/shacl#datatype': {
    label: 'Range Datatypes',
    type: 'datatype',
    appliesTo: ['datatype_property', 'annotation_property'],
  },
  'http://www.w3.org/ns/shacl#minCount': {
    label: 'Min Count',
    type: 'integer',
    appliesTo: ['object_property', 'datatype_property', 'annotation_property'],
  },
  'http://www.w3.org/ns/shacl#maxCount': {
    label: 'Max Count',
    type: 'integer',
    appliesTo: ['object_property', 'datatype_property', 'annotation_property'],
  },
  'http://www.w3.org/ns/shacl#minLength': {
    label: 'Min Length',
    type: 'integer',
    appliesTo: ['datatype_property'],
  },
  'http://www.w3.org/ns/shacl#maxLength': {
    label: 'Max Length',
    type: 'integer',
    appliesTo: ['datatype_property'],
  },
  'http://www.w3.org/ns/shacl#pattern': {
    label: 'Pattern (Regex)',
    type: 'text',
    appliesTo: ['datatype_property'],
  },
  'http://www.w3.org/ns/shacl#flags': {
    label: 'Pattern Flags',
    type: 'text',
    appliesTo: ['datatype_property'],
  },
  'http://www.w3.org/ns/shacl#nodeKind': {
    label: 'Node Kind',
    type: 'dropdown',
    appliesTo: ['object_property', 'datatype_property'],
    options: [
      'http://www.w3.org/ns/shacl#IRI',
      'http://www.w3.org/ns/shacl#Literal',
      'http://www.w3.org/ns/shacl#BlankNode',
    ],
  },
  'http://www.w3.org/ns/shacl#languageIn': {
    label: 'Language (comma‑separated)',
    type: 'text',
    appliesTo: ['datatype_property'],
  },
  'http://www.w3.org/ns/shacl#minInclusive': {
    label: 'Min Inclusive',
    type: 'number',
    appliesTo: ['datatype_property'],
  },
  'http://www.w3.org/ns/shacl#maxInclusive': {
    label: 'Max Inclusive',
    type: 'number',
    appliesTo: ['datatype_property'],
  },
  'http://www.w3.org/ns/shacl#in': {
    label: 'Controlled Vocabulary',
    type: 'class',
    multiple: true,
    appliesTo: ['object_property'],
  },
  'http://www.w3.org/ns/shacl#hasValue': {
    label: 'Fixed Value',
    type: 'class',
    appliesTo: ['object_property'],
  },
}