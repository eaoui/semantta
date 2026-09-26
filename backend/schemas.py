"""
Semantta API schemas.

Pydantic models used by the FastAPI API and application-profile logic.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel


class OntologyInfo(BaseModel):
    filename: str
    title: str = ""
    version: str = ""
    iri: str = ""
    namespaces: List[str] = []


class MetadataFileInfo(BaseModel):
    filename: str
    primary_iri: Optional[str] = None
    namespaces: List[str] = []
    instances_count: int = 0
    triples_count: int = 0
    vocab_integrated: bool = True
    instances_merged: bool = True


class ProfileEntityItem(BaseModel):
    uri: str
    type: str
    in_onto: bool
    active: bool
    types: Optional[List[str]] = None
    domain: Optional[List[str]] = None
    ontology: Optional[str] = None
    sources: List[str] = []
    source_file: Optional[str] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    pattern_flags: Optional[str] = None
    node_kind: Optional[str] = None
    language_in: Optional[List[str]] = None
    min_inclusive: Optional[float] = None
    max_inclusive: Optional[float] = None
    in_vocabulary: Optional[List[str]] = None
    has_value: Optional[str] = None
    order: Optional[int] = None


class Instance(BaseModel):
    uri: str
    types: List[str]
    properties: Dict[str, List[str]]
    is_blank: bool
    label: Optional[str] = None
    source: str = "imported"
    starred: bool = False


class ToggleRequest(BaseModel):
    uri: str
    active: bool


class StateResponse(BaseModel):
    ontologies: List[OntologyInfo]
    instances: List[Instance]
    display_format: str
    prefix_map: Dict[str, str]
    metadata_files: List[MetadataFileInfo]
    profile_entities: List[ProfileEntityItem] = []
    public_display_blank_nodes: bool = False
    ontology_namespaces: List[str] = []
    site_title: str = "Semantta"
    base_iri: str = ""