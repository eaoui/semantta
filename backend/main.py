"""
Semantta Backend — Main Application
=================================
FastAPI application providing ontology-based metadata management.
All endpoints, core business logic, and in-memory state are defined here.
"""

# ---------------------------------------------------------------------------
#  Imports
# ---------------------------------------------------------------------------
import asyncio
import hashlib
import importlib
import io
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from collections import defaultdict
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Callable, Dict, List, Optional, Set, cast
from dotenv import load_dotenv
load_dotenv()

import owlrl
import pyshacl
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, split_uri

from fuseki_store import FusekiStore, SHAPES_GRAPH
from utils import shape_uri_for_entity, property_shape_uri

# ---------------------------------------------------------------------------
#  Constants & Configuration
# ---------------------------------------------------------------------------
RDF_FORMAT_MAP = {
    "rdf": "xml", "owl": "xml", "xml": "xml",
    "ttl": "turtle", "n3": "n3", "nt": "nt", "nq": "nquads",
    "jsonld": "json-ld", "json": "json-ld",
    "trix": "trix", "trig": "trig",
}

_BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(_BASE_DIR, "data")
PLUGINS_DIR = os.path.join(_BASE_DIR, "plugins")
THEMES_DIR = os.path.join(DATA_DIR, "themes")
ONTOLOGY_DIR = os.path.join(DATA_DIR, "ontologies")
METADATA_DIR = os.path.join(DATA_DIR, "metadata")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
INDEX_CACHE_FILE = os.path.join(CACHE_DIR, "_indexes.json")
STARS_FILE = os.path.join(DATA_DIR, "stars.json")

OWL_FILE = os.path.join(_BASE_DIR, "vocab", "owl.ttl")
PREFERENCES_FILE = os.path.join(DATA_DIR, "preferences.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
PLUGINS_CONFIG_FILE = os.path.join(DATA_DIR, "plugins.json")
THEMES_CONFIG_FILE = os.path.join(DATA_DIR, "themes.json")
FRONTEND_ACTIVE_THEME_FILE = os.path.join(
    _BASE_DIR, "..", "frontend", "config", "active-theme.json"
)

SH = Namespace("http://www.w3.org/ns/shacl#")
GENERIC_RANGES = {str(OWL.Thing), str(RDFS.Resource)}
XSD_INTEGER = "http://www.w3.org/2001/XMLSchema#integer"
XSD_DECIMAL = "http://www.w3.org/2001/XMLSchema#decimal"
IGNORE_NAMESPACES = ["http://www.w3.org/2002/07/owl#"]

# ---------------------------------------------------------------------------
#  System Datatypes & Annotation Properties
# ---------------------------------------------------------------------------
SYSTEM_DATATYPES = [
    "http://www.w3.org/2000/01/rdf-schema#Literal",
    "http://www.w3.org/2002/07/owl#rational",
    "http://www.w3.org/2002/07/owl#real",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#PlainLiteral",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#XMLLiteral",
    "http://www.w3.org/2001/XMLSchema#string",
    "http://www.w3.org/2001/XMLSchema#boolean",
    "http://www.w3.org/2001/XMLSchema#decimal",
    "http://www.w3.org/2001/XMLSchema#integer",
    "http://www.w3.org/2001/XMLSchema#double",
    "http://www.w3.org/2001/XMLSchema#float",
    "http://www.w3.org/2001/XMLSchema#date",
    "http://www.w3.org/2001/XMLSchema#time",
    "http://www.w3.org/2001/XMLSchema#dateTime",
    "http://www.w3.org/2001/XMLSchema#dateTimeStamp",
    "http://www.w3.org/2001/XMLSchema#gYear",
    "http://www.w3.org/2001/XMLSchema#gMonth",
    "http://www.w3.org/2001/XMLSchema#gDay",
    "http://www.w3.org/2001/XMLSchema#gYearMonth",
    "http://www.w3.org/2001/XMLSchema#gMonthDay",
    "http://www.w3.org/2001/XMLSchema#duration",
    "http://www.w3.org/2001/XMLSchema#yearMonthDuration",
    "http://www.w3.org/2001/XMLSchema#dayTimeDuration",
    "http://www.w3.org/2001/XMLSchema#byte",
    "http://www.w3.org/2001/XMLSchema#short",
    "http://www.w3.org/2001/XMLSchema#int",
    "http://www.w3.org/2001/XMLSchema#long",
    "http://www.w3.org/2001/XMLSchema#unsignedByte",
    "http://www.w3.org/2001/XMLSchema#unsignedShort",
    "http://www.w3.org/2001/XMLSchema#unsignedInt",
    "http://www.w3.org/2001/XMLSchema#unsignedLong",
    "http://www.w3.org/2001/XMLSchema#positiveInteger",
    "http://www.w3.org/2001/XMLSchema#nonNegativeInteger",
    "http://www.w3.org/2001/XMLSchema#negativeInteger",
    "http://www.w3.org/2001/XMLSchema#nonPositiveInteger",
    "http://www.w3.org/2001/XMLSchema#hexBinary",
    "http://www.w3.org/2001/XMLSchema#base64Binary",
    "http://www.w3.org/2001/XMLSchema#anyURI",
    "http://www.w3.org/2001/XMLSchema#language",
    "http://www.w3.org/2001/XMLSchema#normalizedString",
    "http://www.w3.org/2001/XMLSchema#token",
    "http://www.w3.org/2001/XMLSchema#NMTOKEN",
    "http://www.w3.org/2001/XMLSchema#Name",
    "http://www.w3.org/2001/XMLSchema#NCName",
]

SYSTEM_ANNOTATION_PROPERTIES = [
    "http://www.w3.org/2000/01/rdf-schema#label",
    "http://www.w3.org/2000/01/rdf-schema#comment",
    "http://www.w3.org/2000/01/rdf-schema#seeAlso",
    "http://www.w3.org/2000/01/rdf-schema#isDefinedBy",
]

CORE_ACTIVE_DATATYPES = [
    "http://www.w3.org/2001/XMLSchema#string",
    "http://www.w3.org/2001/XMLSchema#boolean",
    "http://www.w3.org/2001/XMLSchema#decimal",
    "http://www.w3.org/2001/XMLSchema#integer",
    "http://www.w3.org/2000/01/rdf-schema#Literal",
]

CORE_ACTIVE_ANNOTATION_PROPERTIES = [
    "http://www.w3.org/2000/01/rdf-schema#label",
    "http://www.w3.org/2000/01/rdf-schema#comment",
    "http://www.w3.org/2000/01/rdf-schema#seeAlso",
    "http://www.w3.org/2000/01/rdf-schema#isDefinedBy",
]

# ---------------------------------------------------------------------------
#  Pydantic Models (must be defined before classes that use them)
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
#  Global State
# ---------------------------------------------------------------------------
state = {
    "ontologies": [],
    "combined_onto_graph": Graph(),
    "prefix_map": {},
    "instances": [],
    "display_format": "iri",
    "metadata_files": [],
    "metadata_only_sources": {},
    "non_integrated_uris": set(),
    "merged_metadata_graph": Graph(),
    "created_instances": set(),
    "created_instances_graph": Graph(),
    "all_ontology_namespaces": set(),
    "profile_version": 0,
    "full_label_properties": [],
    "starred_instance_uris": set(),
}

_subclass_pairs: Set[tuple] = set()
_property_domains: Dict[str, List[str]] = defaultdict(list)
_property_ranges: Dict[str, List[str]] = defaultdict(list)
_property_cardinalities: Dict[tuple, tuple] = {}
_disjoint_pairs: Set[tuple] = set()

_used_uris_set: Set[str] = set()
_metadata_uris: Set[str] = set()

progress = {"phase": "", "percent": 0}
validation_ontology_graph = Graph()
LABEL_PROPERTIES: List[str] = []

# ---------------------------------------------------------------------------
#  General Helpers
# ---------------------------------------------------------------------------
def is_valid_uri(uri: str) -> bool:
    return " " not in uri and "\t" not in uri and "\n" not in uri and (
        uri.startswith(("http://", "https://", "urn:"))
    )

def _is_specific_range(range_uri: str) -> bool:
    return range_uri not in GENERIC_RANGES

def safe_namespace(uri: str) -> str:
    idx = max(uri.rfind('/'), uri.rfind('#'))
    return uri[:idx + 1] if idx != -1 else uri

def update_prefix_map(g: Graph, prefix_map: dict):
    for prefix, ns in g.namespace_manager.namespaces():
        if ns not in prefix_map:
            prefix_map[ns] = prefix

@lru_cache(maxsize=1024)
def _cached_label(uri: str) -> str:
    for prop in LABEL_PROPERTIES:
        for onto in state["ontologies"]:
            label = onto["graph"].value(URIRef(uri), URIRef(prop))
            if label:
                return str(label)
    try:
        _, local = split_uri(uri)
        return local
    except:
        return uri

def get_label(uri: str) -> str:
    return _cached_label(uri)

def get_property_domains(prop: str) -> List[str]:
    return _property_domains.get(prop, [])

def get_property_ranges(prop: str) -> List[str]:
    return _property_ranges.get(prop, [])

def is_subclass(cls: str, parents: list) -> bool:
    if not parents:
        return True
    return any((cls, p) in _subclass_pairs for p in parents)

def _is_class_in_ontology(uri: str, g: Graph) -> bool:
    u = URIRef(uri)
    return (u, RDF.type, OWL.Class) in g or (u, RDF.type, RDFS.Class) in g

def _is_property_in_ontology(uri: str, g: Graph) -> bool:
    u = URIRef(uri)
    return any((u, RDF.type, t) in g for t in (
        RDF.Property, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty
    ))

def _is_individual_in_ontology(uri: str, g: Graph) -> bool:
    return any(g.objects(URIRef(uri), RDF.type))

def _format_constraint_value(pred: str, val) -> str:
    if isinstance(val, bool):
        return f'"{"true" if val else "false"}"^^xsd:boolean'
    if isinstance(val, int) or (isinstance(val, str) and val.lstrip('-').isdigit()):
        if pred in (
            str(SH.minCount), str(SH.maxCount),
            str(SH.minLength), str(SH.maxLength),
            str(SH.order),
        ):
            return f'"{val}"^^<{XSD_INTEGER}>'
        if pred in (str(SH.minInclusive), str(SH.maxInclusive)):
            return f'"{val}"^^<{XSD_DECIMAL}>'
    if isinstance(val, str) and (val.startswith("http://") or val.startswith("urn:")):
        return f"<{val}>"
    safe = str(val).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{safe}"'

def _flatten_class_expression(g: Graph, node) -> List[str]:
    if isinstance(node, URIRef):
        uri = str(node)
        if uri in GENERIC_RANGES:
            return []
        return [uri] if is_valid_uri(uri) else []
    if not isinstance(node, BNode):
        return []
    for container in (OWL.unionOf, OWL.intersectionOf, OWL.oneOf):
        collection_node = g.value(node, container)
        if collection_node:
            try:
                members = list(Collection(g, collection_node))
                items = []
                for member in members:
                    items.extend(_flatten_class_expression(g, member))
                return items
            except Exception:
                pass
    return []

def collapse_identical_blank_nodes(graph: Graph):
    """
    Merge blank nodes (both real BNodes and ``urn:bnid:...`` URIs)
    that have **exactly** identical outgoing triples.
    All references to a duplicate are redirected to its canonical node.
    """
    # ── 1. Identify blank‑node subjects ────────────────────────
    bnodes = [
        s for s in graph.subjects()
        if isinstance(s, BNode) or
           (isinstance(s, URIRef) and str(s).startswith("urn:bnid:"))
    ]
    if len(bnodes) <= 1:
        return

    # ── 2. Group by outgoing‑triple fingerprint ─────────────────
    fingerprints = defaultdict(list)
    for bn in bnodes:
        triples = sorted(
            (p.n3(), o.n3()) for _, p, o in graph.triples((bn, None, None))
        )
        fp = hashlib.sha256(str(triples).encode()).hexdigest()
        fingerprints[fp].append(bn)

    # ── 3. Build a mapping: duplicate → canonical ──────────────
    mapping = {}
    for nodes in fingerprints.values():
        if len(nodes) <= 1:
            continue
        canonical = nodes[0]
        for dup in nodes[1:]:
            mapping[dup] = canonical

    if not mapping:
        return

    # ── 4. Build a new graph with all references resolved ──────
    new_graph = Graph()
    for s, p, o in graph:
        ns = mapping.get(s, s)
        no = mapping.get(o, o) if isinstance(o, (BNode, URIRef)) else o
        # Avoid creating a triple with a blank‑node subject that is now canonical but identical?
        # No, we just add the triple.
        new_graph.add((ns, p, no))

    # ── 5. Replace the original graph’s content ────────────────
    graph.remove((None, None, None))
    for triple in new_graph:
        graph.add(triple)

def rewrite_uris_in_graph(g: Graph, mapping: dict):
    for s, p, o in list(g.triples((None, None, None))):
        new_s = mapping.get(s, s)
        new_o = mapping.get(o, o) if isinstance(o, URIRef) else o
        if new_s != s or new_o != o:
            g.remove((s, p, o))
            g.add((new_s, p, new_o))

# ---------------------------------------------------------------------------
#  Ontology Processing
# ---------------------------------------------------------------------------
def parse_ontology(file_bytes: bytes, fmt: str) -> Graph:
    g = Graph()
    try:
        g.parse(data=file_bytes, format=fmt)
    except Exception:
        if fmt == "xml":
            patched = file_bytes.decode("utf-8").replace('rdf:resource="', 'rdf:about="')
            g.parse(data=patched.encode("utf-8"), format="xml")
        else:
            raise
    return g

def load_owl_vocabulary(g: Graph):
    if not os.path.exists(OWL_FILE):
        raise FileNotFoundError(f"OWL vocabulary missing: {OWL_FILE}")
    g.parse(OWL_FILE, format="turtle")

def apply_reasoning(g: Graph):
    load_owl_vocabulary(g)
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g)

def process_ontology(g: Graph, filename: str) -> list:
    def is_domain_uri(uri):
        return not any(str(uri).startswith(ns) for ns in IGNORE_NAMESPACES)

    entities = []
    known_uris = set()
    rdf_property_subjects = set()

    for subj, typ in g.subject_objects(RDF.type):
        if not is_domain_uri(subj) or isinstance(subj, BNode):
            continue
        uri = str(subj)
        if not is_valid_uri(uri):
            continue

        if typ in (OWL.Class, RDFS.Class):
            if uri not in known_uris:
                entities.append({"uri": uri, "type": "class"})
                known_uris.add(uri)
        elif typ == OWL.ObjectProperty:
            entities.append({"uri": uri, "type": "object_property"})
            known_uris.add(uri)
        elif typ == OWL.DatatypeProperty:
            entities.append({"uri": uri, "type": "datatype_property"})
            known_uris.add(uri)
        elif typ == OWL.AnnotationProperty:
            entities.append({"uri": uri, "type": "annotation_property"})
            known_uris.add(uri)
        elif typ == RDF.Property:
            rdf_property_subjects.add(subj)
        elif typ == RDFS.Datatype:
            if uri not in known_uris:
                entities.append({"uri": uri, "type": "datatype"})
                known_uris.add(uri)
        elif typ == OWL.NamedIndividual:
            if uri not in known_uris:
                types = [str(t) for t in g.objects(subj, RDF.type)]
                entities.append({"uri": uri, "type": "individual", "types": types})
                known_uris.add(uri)

    for subj in rdf_property_subjects:
        uri = str(subj)
        if uri not in known_uris and is_domain_uri(subj):
            entities.append({"uri": uri, "type": "annotation_property"})
            known_uris.add(uri)

    return entities

def extract_ontology_metadata(g: Graph) -> dict:
    meta = {"title": "", "version": "", "iri": ""}
    for onto in g.subjects(RDF.type, OWL.Ontology):
        meta["iri"] = str(onto)
        if label := g.value(onto, RDFS.label):
            meta["title"] = str(label)
        if ver := g.value(onto, OWL.versionInfo):
            meta["version"] = str(ver)
        break
    if not meta["iri"]:
        for s in g.subjects(RDFS.label, None):
            if isinstance(s, URIRef):
                meta["iri"] = str(s)
                meta["title"] = str(g.value(s, RDFS.label))
                break
    return meta

def get_property_cardinality(class_uri: str, prop_uri: str) -> dict:
    minc, maxc = _property_cardinalities.get((class_uri, prop_uri), (None, None))
    return {"minCardinality": minc, "maxCardinality": maxc}

def _get_property_type(prop_uri: str) -> str:
    u = URIRef(prop_uri)
    g = state["combined_onto_graph"]
    if (u, RDF.type, OWL.ObjectProperty) in g:
        return "object"
    if (u, RDF.type, OWL.DatatypeProperty) in g:
        return "datatype"
    for r in g.objects(u, RDFS.range):
        if str(r).startswith("http://www.w3.org/2001/XMLSchema#"):
            return "datatype"
    return "object"

def get_ontology_namespaces(g: Graph) -> List[str]:
    known_ns = {str(ns) for _, ns in g.namespace_manager.namespaces() if ns}
    used_ns = set()
    for p in g.predicates():
        if isinstance(p, URIRef):
            uri = str(p)
            for ns in known_ns:
                if uri.startswith(ns):
                    used_ns.add(ns)
                    break
    for s in g.subjects(RDF.type, None):
        if isinstance(s, URIRef) and not str(s).startswith("urn:bnid:"):
            uri = str(s)
            for ns in known_ns:
                if uri.startswith(ns):
                    used_ns.add(ns)
                    break
    return sorted(used_ns)

# ---------------------------------------------------------------------------
#  Index Building & Caching
# ---------------------------------------------------------------------------
def rebuild_precomputed():
    # Single scan for core indexes (subclass, domains, ranges, cardinalities, disjointness)
    # NOTE: update_label_hierarchy() and rebuild_validation_ontology() scan the graph again.
    if load_indexes():
        return
    g = state["combined_onto_graph"]
    subclass_pairs = set()
    cardinality_bnodes = []

    for s, p, o in g:
        if p == RDFS.subClassOf:
            subclass_pairs.add((str(s), str(o)))
            if isinstance(o, BNode):
                cardinality_bnodes.append((str(s), o))
        elif p == RDFS.domain:
            for cls_uri in _flatten_class_expression(g, o):
                _property_domains[str(s)].append(cls_uri)
        elif p == RDFS.range:
            for cls_uri in _flatten_class_expression(g, o):
                _property_ranges[str(s)].append(cls_uri)
        elif p == OWL.disjointWith:
            for cls_uri in _flatten_class_expression(g, o):
                if isinstance(s, URIRef):
                    _disjoint_pairs.add((str(s), cls_uri))

    _property_cardinalities.clear()
    for cls_uri, bnode in cardinality_bnodes:
        prop = g.value(bnode, OWL.onProperty)
        if prop:
            prop_str = str(prop)
            minc = g.value(bnode, OWL.minCardinality)
            maxc = g.value(bnode, OWL.maxCardinality)
            exact = g.value(bnode, OWL.cardinality)
            mn = int(minc) if minc else None
            mx = int(maxc) if maxc else None
            if exact:
                mn = mx = int(exact)
            _property_cardinalities[(cls_uri, prop_str)] = (mn, mx)

    _subclass_pairs.clear()
    _subclass_pairs.update(subclass_pairs)
    update_label_hierarchy()
    rebuild_validation_ontology()
    save_indexes()

def save_indexes():
    os.makedirs(CACHE_DIR, exist_ok=True)
    data = {
        "subclass_pairs": list(_subclass_pairs),
        "property_domains": dict(_property_domains),
        "property_ranges": dict(_property_ranges),
        "property_cardinalities": [
            {"class": cls, "prop": prop, "min": mn, "max": mx}
            for (cls, prop), (mn, mx) in _property_cardinalities.items()
        ],
        "disjoint_pairs": list(_disjoint_pairs),
        "full_label_properties": state.get("full_label_properties", []),
    }
    with open(INDEX_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def load_indexes() -> bool:
    if not os.path.exists(INDEX_CACHE_FILE):
        return False
    try:
        with open(INDEX_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        _subclass_pairs.clear()
        _subclass_pairs.update((a, b) for a, b in data["subclass_pairs"])
        for k, v in data["property_domains"].items():
            _property_domains[k] = list(v)
        for k, v in data["property_ranges"].items():
            _property_ranges[k] = list(v)
        _property_cardinalities.clear()
        for entry in data["property_cardinalities"]:
            _property_cardinalities[(entry["class"], entry["prop"])] = (
                entry["min"], entry["max"]
            )
        _disjoint_pairs.clear()
        for a, b in data.get("disjoint_pairs", []):
            _disjoint_pairs.add((a, b))

        full_labels = data.get("full_label_properties", [])
        state["full_label_properties"] = full_labels
        prefs = load_preferences()
        excluded = prefs.get("excluded_label_properties", [])
        global LABEL_PROPERTIES
        LABEL_PROPERTIES = [uri for uri in full_labels if uri not in excluded]
        store.set_label_properties(LABEL_PROPERTIES)
        return True
    except Exception:
        return False

def update_label_hierarchy():
    global LABEL_PROPERTIES
    store.set_label_properties(LABEL_PROPERTIES)
    g = state["combined_onto_graph"]
    label_uri = str(RDFS.label)
    depths = {label_uri: 0}
    queue = [label_uri]
    while queue:
        cur = queue.pop(0)
        for sub in g.subjects(RDFS.subPropertyOf, URIRef(cur)):
            s_uri = str(sub)
            if s_uri not in depths:
                depths[s_uri] = depths[cur] + 1
                queue.append(s_uri)
    sorted_labels = sorted(depths.keys(), key=lambda u: (-depths[u], u))
    state["full_label_properties"] = sorted_labels[:]
    prefs = load_preferences()
    excluded = prefs.get("excluded_label_properties", [])
    LABEL_PROPERTIES = [uri for uri in sorted_labels if uri not in excluded]
    store.set_label_properties(LABEL_PROPERTIES)

# ---------------------------------------------------------------------------
#  Validation Ontology
# ---------------------------------------------------------------------------
SHACL_RELEVANT_PREDICATES = {
    str(RDFS.subClassOf), str(RDFS.subPropertyOf),
    str(RDFS.domain), str(RDFS.range),
    str(OWL.equivalentClass), str(OWL.equivalentProperty),
    str(OWL.inverseOf), str(OWL.sameAs), str(OWL.differentFrom),
    str(OWL.FunctionalProperty), str(OWL.InverseFunctionalProperty),
    str(OWL.TransitiveProperty), str(OWL.SymmetricProperty),
    str(OWL.AsymmetricProperty), str(OWL.ReflexiveProperty),
    str(OWL.IrreflexiveProperty),
}

def rebuild_validation_ontology():
    global validation_ontology_graph
    validation_ontology_graph = Graph()
    g = state["combined_onto_graph"]
    for s, p, o in g:
        if str(p) in SHACL_RELEVANT_PREDICATES:
            validation_ontology_graph.add((s, p, o))
    for subj, obj in g.subject_objects(RDF.type):
        if str(obj).startswith(str(OWL)):
            validation_ontology_graph.add((subj, RDF.type, obj))

# ---------------------------------------------------------------------------
#  Cache Invalidation
# ---------------------------------------------------------------------------
def invalidate_caches():
    global _profile_dirty
    _profile_dirty = True
    _subclass_pairs.clear()
    _property_domains.clear()
    _property_ranges.clear()
    _property_cardinalities.clear()
    _disjoint_pairs.clear()
    _cached_label.cache_clear()
    if os.path.exists(INDEX_CACHE_FILE):
        os.remove(INDEX_CACHE_FILE)
    rebuild_precomputed()

def invalidate_profile():
    ap.invalidate()
    shacl.invalidate_shapes_cache()
    state["profile_version"] = state.get("profile_version", 0) + 1

def invalidate_everything():
    invalidate_profile()
    invalidate_caches()

# ---------------------------------------------------------------------------
#  Async Utilities
# ---------------------------------------------------------------------------
async def get_global_property_order() -> Dict[str, int]:
    order_map = {}
    try:
        rows = await store._sparql_query(f"""
            SELECT ?propUri (SAMPLE(?order) AS ?ord) WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    ?propShape <{SH}path> ?propUri ;
                               <{SH}order> ?order .
                }}
            }} GROUP BY ?propUri
        """)
        for r in rows:
            order_map[r["propUri"]] = int(r["ord"])
    except Exception:
        pass
    return order_map

async def rebuild_used_uris():
    global _used_uris_set
    try:
        rows = await store._sparql_query("""
            SELECT DISTINCT ?uri WHERE {
                { ?uri a ?type . } UNION { ?s ?uri ?o . } UNION { ?s a ?uri . }
                FILTER(ISIRI(?uri) && !STRSTARTS(STR(?uri), "urn:bnid:"))
            }""")
        _used_uris_set = {r["uri"] for r in rows}
    except Exception:
        _used_uris_set = set()

async def refresh_instances_from_store():
    instances = await store.get_all_instances()
    starred = state.get("starred_instance_uris", set())
    for inst in instances:
        uri = inst["uri"]
        in_metadata = uri in _metadata_uris
        created = uri in state.get("created_instances", set())
        if created and in_metadata:
            inst["source"] = "both"
        elif created:
            inst["source"] = "created"
        else:
            inst["source"] = "imported"
        inst["starred"] = uri in starred
    state["instances"] = instances

async def get_instance_suggestions(range_uris: list) -> list:
    if not store:
        return []
    expanded = set(range_uris)
    for cls in range_uris:
        for sub, sup in _subclass_pairs:
            if sup == cls:
                expanded.add(sub)
    if not expanded:
        return []
    values = " ".join(f"<{r}>" for r in expanded)
    query = f"""PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    SELECT DISTINCT ?instance WHERE {{
        VALUES ?rangeClass {{ {values} }}
        ?instance a ?rangeClass .
        FILTER(!STRSTARTS(STR(?instance), "urn:bnid:"))
    }} LIMIT 100"""
    try:
        rows = await store._sparql_query(query)
        return [{"uri": r["instance"], "label": get_label(r["instance"])} for r in rows]
    except Exception:
        return []

async def check_disjoint_classes(class_uris: List[str]):
    all_disjoint = set(_disjoint_pairs)
    for cls in class_uris:
        shape_uri = shape_uri_for_entity(cls, "class", state["prefix_map"])
        rows = await store._sparql_query(f"""
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            SELECT ?other WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    <{shape_uri}> owl:disjointWith ?other .
                }}
            }}
        """)
        for r in rows:
            other = r["other"]
            all_disjoint.add((cls, other))
            all_disjoint.add((other, cls))
    for i in range(len(class_uris)):
        for j in range(i + 1, len(class_uris)):
            a, b = class_uris[i], class_uris[j]
            if (a, b) in all_disjoint or (b, a) in all_disjoint:
                raise HTTPException(400, f"Classes {a} and {b} are disjoint")

# ---------------------------------------------------------------------------
#  Metadata Parsing
# ---------------------------------------------------------------------------
def parse_metadata(file_bytes: bytes, fmt: str = "nt") -> Graph:
    """
    Parse a metadata file. Blank nodes are always rewritten to
    ``urn:bnid:...`` URIs, regardless of the original format.
    """
    content = file_bytes.decode("utf-8", errors="replace")
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    if content.startswith('\ufeff'):
        content = content[1:]

    # Regex‑based rewrite for line‑based formats (NT, NQuads)
    if fmt in ("nt", "nquads"):
        content = re.sub(r"_:([A-Za-z0-9\-\._~]+)", r"<urn:bnid:\1>", content)

    g = Graph()
    try:
        g.parse(data=content, format=fmt)
    except Exception:
        # Fallback: try N‑Triples for N‑Quads
        if fmt == "nquads":
            try:
                g = Graph()
                g.parse(data=content, format="nt")
            except Exception:
                pass
        # else: keep the empty graph

    # ── Universal blank‑node rewriting ────────────────────
    # After parsing, replace any remaining BNode objects
    # (from Turtle, RDF/XML, JSON‑LD, etc.) with urn:bnid: URIs.
    bnode_map = {}
    for s, p, o in list(g.triples((None, None, None))):
        new_s = _replace_bnode(s, bnode_map)
        new_o = _replace_bnode(o, bnode_map) if isinstance(o, BNode) else o
        if new_s != s or new_o != o:
            g.remove((s, p, o))
            g.add((new_s, p, new_o))

    return g


def _replace_bnode(term, bnode_map: dict) -> URIRef:
    """Return a urn:bnid: URI for the given BNode, creating one if needed."""
    if not isinstance(term, BNode):
        return term
    if term not in bnode_map:
        # Use a short, deterministic key based on the blank‑node id
        # to avoid collisions across different blank nodes.
        bnode_map[term] = URIRef(f"urn:bnid:{term}")
    return bnode_map[term]

def list_saved_metadata_files():
    if not os.path.isdir(METADATA_DIR):
        return []
    return [
        f for f in os.listdir(METADATA_DIR)
        if f.endswith(('.nt','.ttl','.rdf','.xml','.jsonld','.json','.trig','.trix','.nq'))
        and not f.endswith('.meta.json')
    ]

# ---------------------------------------------------------------------------
#  Preferences & Settings
# ---------------------------------------------------------------------------
def load_preferences():
    if os.path.exists(PREFERENCES_FILE):
        with open(PREFERENCES_FILE) as f:
            prefs = json.load(f)
            prefs.setdefault("excluded_label_properties", [])
            return prefs
    return {"display_format": "prefix", "excluded_label_properties": []}

def save_preferences(prefs):
    os.makedirs(os.path.dirname(PREFERENCES_FILE), exist_ok=True)
    with open(PREFERENCES_FILE, 'w') as f:
        json.dump(prefs, f, indent=2)

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    return {"site_title": "Semantta", "base_iri": ""}

def save_settings(settings):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

# ---------------------------------------------------------------------------
#  Constraint Helpers
# ---------------------------------------------------------------------------
def get_original_constraints(entity_uri: str, entity_type: str, g: Graph) -> dict:
    u = URIRef(entity_uri)
    constraints = defaultdict(list)
    for p, o in g.predicate_objects(u):
        pred = str(p)
        if pred.startswith(str(RDFS)) or pred.startswith(str(OWL)):
            constraints[pred].append(str(o))
    if "property" in entity_type:
        for t in g.objects(u, RDF.type):
            t_str = str(t)
            if t_str.startswith(str(OWL)):
                constraints[t_str].append("true")
    if entity_type == "class":
        for sup in g.objects(u, RDFS.subClassOf):
            if isinstance(sup, BNode):
                prop = g.value(sup, OWL.onProperty)
                if prop:
                    pstr = str(prop)
                    for card in [OWL.minCardinality, OWL.maxCardinality, OWL.cardinality]:
                        val = g.value(sup, card)
                        if val:
                            constraints[str(card)].append(f"{pstr} {val}")
    return dict(constraints)

def validate_constraints(entity_uri: str, entity_type: str, proposed: dict):
    original = get_original_constraints(entity_uri, entity_type, state["combined_onto_graph"])
    for pred, new_vals in proposed.items():
        if pred not in original:
            continue
        orig_vals = original[pred]
        if pred == str(OWL.equivalentClass):
            new_list = new_vals if isinstance(new_vals, list) else [new_vals]
            for n in new_list:
                if not any(is_subclass(n, [o]) or n == o for o in orig_vals):
                    raise HTTPException(400,
                        f"Value {n} for {pred} must be a subclass of an original value")
        elif pred.startswith(str(OWL)) and orig_vals == ["true"] and not new_vals:
            raise HTTPException(400, f"Cannot remove {pred}")
    return True

async def _apply_constraints(shape_uri: str, constraints: dict,
                             keep_predicates: set) -> None:
    keep_filter = ", ".join(f"<{p}>" for p in keep_predicates)
    await store._sparql_update(f"""
        DELETE {{ GRAPH <{SHAPES_GRAPH}> {{ <{shape_uri}> ?p ?o }} }}
        WHERE  {{ GRAPH <{SHAPES_GRAPH}> {{
            <{shape_uri}> ?p ?o .
            FILTER(?p NOT IN ({keep_filter}))
        }} }}
    """)
    triples = ""
    for pred, val in constraints.items():
        if val is None or val == "":
            continue
        if isinstance(val, list):
            for v in val:
                triples += f"<{shape_uri}> <{pred}> {_format_constraint_value(pred, v)} .\n"
        else:
            triples += f"<{shape_uri}> <{pred}> {_format_constraint_value(pred, val)} .\n"
    if triples:
        await store._sparql_update(
            f"INSERT DATA {{ GRAPH <{SHAPES_GRAPH}> {{ {triples} }} }}"
        )

def _require_keys(data: dict, *keys: str):
    """Raise a 400 error if any of the given keys is missing or has a falsy value."""
    for key in keys:
        if not data.get(key):
            raise HTTPException(400, f"'{key}' is required")
        
# ---------------------------------------------------------------------------
#  Application Profile Service
# ---------------------------------------------------------------------------
class ApplicationProfile:
    def __init__(self, store: FusekiStore):
        self.store = store
        self._cache: List[ProfileEntityItem] = []
        self._dirty = True
        self._order_map: Dict[str, int] = {}
        self._order_loaded = False
        self._cached_domains = None
        self._cache_version = -1

    def invalidate(self):
        self._dirty = True
        self._order_loaded = False
        self._cached_domains = None

    async def _ensure_order_map(self):
        if self._order_loaded:
            return
        self._order_map.clear()
        try:
            rows = await self.store._sparql_query(f"""
                PREFIX sh: <http://www.w3.org/ns/shacl#>
                SELECT ?propUri (SAMPLE(?order) AS ?ord) WHERE {{
                    GRAPH <{SHAPES_GRAPH}> {{
                        ?shape sh:path ?propUri ; sh:order ?order .
                    }}
                }} GROUP BY ?propUri
            """)
            for r in rows:
                self._order_map[r["propUri"]] = int(r["ord"])
        except Exception:
            pass
        self._order_loaded = True

    async def get_entity_type(self, uri: str) -> str:
        entities = await self.build_profile_entities()
        if not hasattr(self, '_entity_type_map') or self._dirty:
            self._entity_type_map = {e.uri: e.type for e in entities}
        if uri not in self._entity_type_map:
            raise HTTPException(404, "Entity not found in profile")
        return self._entity_type_map[uri]

    async def build_profile_entities(self) -> List[ProfileEntityItem]:
        current_version = state.get("profile_version", 0)
        if not self._dirty and self._cache_version == current_version:
            return self._cache

        candidates: Dict[str, dict] = {}

        for onto in state["ontologies"]:
            for e in onto["entities"]:
                uri = e["uri"]
                if uri not in candidates:
                    candidates[uri] = {"type": e["type"], "sources": [], "in_onto": True}
                candidates[uri]["sources"].append(onto["filename"])

        for uri in SYSTEM_DATATYPES:
            candidates.setdefault(uri, {"type": "datatype", "sources": [], "in_onto": False})
            if "System" not in candidates[uri]["sources"]:
                candidates[uri]["sources"].append("System")

        for uri in SYSTEM_ANNOTATION_PROPERTIES:
            candidates.setdefault(uri, {"type": "annotation_property", "sources": [], "in_onto": False})
            if "System" not in candidates[uri]["sources"]:
                candidates[uri]["sources"].append("System")

        if not _used_uris_set:
            await rebuild_used_uris()
        md_uri_list = [
            uri for uri in _used_uris_set
            if uri not in candidates
            and not any(uri.startswith(ns) for ns in IGNORE_NAMESPACES)
        ]
        types_map: Dict[str, List[str]] = {}
        if md_uri_list:
            values = " ".join(f"<{u}>" for u in md_uri_list)
            batch_query = f"SELECT ?uri ?type WHERE {{ VALUES ?uri {{ {values} }} . ?uri a ?type . }}"
            try:
                rows = await self.store._sparql_query(batch_query)
                for r in rows:
                    types_map.setdefault(r["uri"], []).append(r["type"])
            except Exception:
                pass
        role_map = await self._batch_entity_roles(md_uri_list) if md_uri_list else {}
        for uri in md_uri_list:
            types = types_map.get(uri, [])
            if types and all(any(t.startswith(ns) for ns in IGNORE_NAMESPACES) for t in types):
                continue
            entity_type = role_map.get(uri, "individual")
            source_file = state["metadata_only_sources"].get(uri, "Metadata")
            candidates[uri] = {
                "type": entity_type,
                "sources": [source_file],
                "in_onto": False,
            }

        active_classes = set(await shacl.get_active_classes())
        active_props = set(await shacl.get_active_properties())
        active_individuals = set(await shacl.get_active_individuals())

        result = []
        for uri, cand in candidates.items():
            etype = cand["type"]
            if etype == "class":
                active = uri in active_classes
            elif etype in ("object_property", "datatype_property", "annotation_property"):
                active = uri in active_props
            else:
                active = uri in active_individuals

            item = ProfileEntityItem(
                uri=uri, type=etype, in_onto=cand["in_onto"], active=active,
                sources=list(dict.fromkeys(cand["sources"])),
                ontology=cand["sources"][0] if cand["sources"] else None,
            )
            if etype in ("object_property", "datatype_property", "annotation_property"):
                item.domain = get_property_domains(uri)
            if etype in ("object_property", "datatype_property", "annotation_property"):
                await self._ensure_order_map()
                item.order = self._order_map.get(uri)
            if etype == "individual":
                onto_entity = next(
                    (e for o in state["ontologies"] for e in o["entities"] if e["uri"] == uri),
                    None
                )
                if onto_entity:
                    item.types = onto_entity.get("types", [])
            result.append(item)

        shacl_domains = await self._get_shacl_domains()
        for item in result:
            if item.type in ("object_property", "datatype_property", "annotation_property"):
                if item.uri in shacl_domains:
                    item.domain = shacl_domains[item.uri]

        result.sort(key=lambda x: (x.order is None, x.order or 0)
                    if x.type in ("object_property", "datatype_property", "annotation_property")
                    else (0, 0))
        self._cache = result
        self._dirty = False
        self._cache_version = current_version
        return result

    async def get_active_classes(self) -> List[str]:
        entities = await self.build_profile_entities()
        return [e.uri for e in entities if e.active and e.type == "class"]

    async def _list_active_properties(self, class_uri: str) -> List[dict]:
        shape_uri = shape_uri_for_entity(class_uri, "class", state["prefix_map"])
        linked = await self.store._sparql_query(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            SELECT ?propUri ?order WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    <{shape_uri}> sh:property ?propShape .
                    ?propShape sh:path ?propUri .
                    OPTIONAL {{ ?propShape sh:order ?order }}
                }}
            }}""")

        orphan = await self.store._sparql_query(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            SELECT ?propUri ?order WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    ?propShape sh:path ?propUri .
                    OPTIONAL {{ ?propShape sh:order ?order }}
                    FILTER NOT EXISTS {{ ?any sh:property ?propShape }}
                }}
            }}""")
        return [
            {"uri": r["propUri"], "order": int(r["order"]) if r.get("order") else None}
            for r in linked + orphan
        ]

    async def _get_property_constraints(self, prop_uri: str) -> dict:
        pshape_uri = shape_uri_for_entity(prop_uri, "property", state["prefix_map"])
        rows = await self.store._sparql_query(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            SELECT ?pred ?val WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    <{pshape_uri}> ?pred ?val .
                    FILTER(?pred IN (sh:class, sh:datatype, sh:minCount, sh:maxCount,
                                    sh:minLength, sh:maxLength, sh:pattern, sh:flags,
                                    sh:languageIn, sh:in, sh:hasValue, sh:nodeKind))
                }}
            }}""")
        constraints = {}
        for r in rows:
            p, v = r["pred"], r["val"]
            if p == str(SH["class"]):
                constraints["class"] = v
            elif p == str(SH.datatype):
                constraints["datatype"] = v
            elif p in (str(SH.minCount), str(SH.maxCount),
                       str(SH.minLength), str(SH.maxLength)):
                try:
                    constraints[p.split('#')[-1]] = int(v)
                except ValueError:
                    pass
            elif p == str(SH.pattern):
                constraints["pattern"] = v
            elif p == str(SH.flags):
                constraints["flags"] = v
            elif p == str(SH.languageIn):
                constraints["languageIn"] = v.split() if v else []
            elif p == str(SH['in']):
                constraints["in"] = v
            elif p == str(SH.nodeKind):
                constraints["nodeKind"] = v
            elif p == str(SH.hasValue):
                constraints["hasValue"] = v
        return constraints

    async def get_properties_for_class(self, class_uri: str) -> List[dict]:
        prop_refs = await self._list_active_properties(class_uri)
        props = []
        for ref in prop_refs:
            prop_uri = ref["uri"]
            ptype = _get_property_type(prop_uri)
            ranges = get_property_ranges(prop_uri)
            datatype = ranges[0] if ptype == "datatype" and ranges else "http://www.w3.org/2001/XMLSchema#string"
            suggestions = await get_instance_suggestions(ranges) if ptype == "object" else []
            card = get_property_cardinality(class_uri, prop_uri)
            shacl_constraints = await self._get_property_constraints(prop_uri)

            if "class" in shacl_constraints:
                ranges = [shacl_constraints["class"]]
                suggestions = await get_instance_suggestions(ranges) if ptype == "object" else []
            if "datatype" in shacl_constraints:
                datatype = shacl_constraints["datatype"]
            if "minCount" in shacl_constraints:
                card["minCardinality"] = shacl_constraints["minCount"]
            if "maxCount" in shacl_constraints:
                card["maxCardinality"] = shacl_constraints["maxCount"]

            props.append({
                "uri": prop_uri,
                "label": get_label(prop_uri),
                "type": ptype,
                "ranges": ranges,
                "datatype": datatype,
                "suggestions": suggestions,
                "allowMultiple": card["maxCardinality"] != 1,
                "order": ref["order"],
                "constraints": shacl_constraints,
            })

        props.sort(key=lambda p: (p["order"] is None, p["order"] or 0))
        return props

    async def merge_metadata_only_entity(self, uri: str, source: str):
        if uri not in state["metadata_only_sources"]:
            state["metadata_only_sources"][uri] = source
        self.invalidate()

    async def resolve_entity_with_ontology(self, entity_uri: str):
        if entity_uri in state["metadata_only_sources"]:
            del state["metadata_only_sources"][entity_uri]
        self.invalidate()

    async def _batch_entity_roles(self, uris: list[str]) -> Dict[str, str]:
        if not uris:
            return {}
        values = " ".join(f"<{u}>" for u in uris)

        # Three concurrent SELECT DISTINCT queries – each returns URIs of one role
        async def select_classes():
            q = f"SELECT DISTINCT ?uri WHERE {{ VALUES ?uri {{ {values} }} . ?s a ?uri }}"
            rows = await self.store._sparql_query(q)
            return {r["uri"] for r in rows}

        async def select_object_props():
            q = f"SELECT DISTINCT ?uri WHERE {{ VALUES ?uri {{ {values} }} . ?s ?uri ?o . FILTER(isIRI(?o)) }}"
            rows = await self.store._sparql_query(q)
            return {r["uri"] for r in rows}

        async def select_datatype_props():
            q = f"SELECT DISTINCT ?uri WHERE {{ VALUES ?uri {{ {values} }} . ?s ?uri ?o . FILTER(isLiteral(?o)) }}"
            rows = await self.store._sparql_query(q)
            return {r["uri"] for r in rows}

        classes_set, obj_props_set, data_props_set = await asyncio.gather(
            select_classes(), select_object_props(), select_datatype_props()
        )

        # Build role map: class takes priority over property
        role_map = {}
        for uri in uris:
            if uri in classes_set:
                role_map[uri] = "class"
            elif uri in obj_props_set:
                role_map[uri] = "object_property"
            elif uri in data_props_set:
                role_map[uri] = "datatype_property"
            else:
                role_map[uri] = "individual"
        return role_map

    async def _get_shacl_domains(self) -> Dict[str, List[str]]:
        if hasattr(self, '_cached_domains') and self._cached_domains is not None:
            return self._cached_domains
        rows = await self.store._sparql_query(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            SELECT ?propUri ?class WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    ?classShape sh:targetClass ?class ; sh:property ?propShape .
                    ?propShape sh:path ?propUri .
                }}
            }}
        """)
        mapping = defaultdict(list)
        for r in rows:
            mapping[r["propUri"]].append(r["class"])
        self._cached_domains = dict(mapping)
        return self._cached_domains

# ---------------------------------------------------------------------------
#  SHACL Profile Manager
# ---------------------------------------------------------------------------
class SHACLProfile:
    def __init__(self, store: FusekiStore, on_change: Optional[Callable[[], None]] = None):
        self.store = store
        self._shapes_cache = None
        self._on_change = on_change

    def _changed(self):
        if self._on_change:
            self._on_change()

    async def _get_shapes_graph(self) -> Graph:
        if self._shapes_cache is None:
            self._shapes_cache = await self.store.load_shapes_graph()
        return self._shapes_cache

    def invalidate_shapes_cache(self):
        self._shapes_cache = None

    async def _set_default_constraints(self, prop_uri: str, class_uri: Optional[str] = None):
        shape_uri = shape_uri_for_entity(prop_uri, "property", state["prefix_map"])
        ptype = _get_property_type(prop_uri)
        ranges = get_property_ranges(prop_uri)
        card = get_property_cardinality(class_uri, prop_uri) if class_uri else None

        constraints = {}
        if ptype == "object" and ranges and _is_specific_range(ranges[0]):
            constraints[str(SH["class"])] = ranges[0]
        elif ptype == "datatype" and ranges:
            constraints[str(SH.datatype)] = ranges[0]

        if card:
            minc = card.get("minCardinality")
            maxc = card.get("maxCardinality")
            if minc is not None:
                constraints[str(SH.minCount)] = minc
            if maxc is not None:
                constraints[str(SH.maxCount)] = maxc

        for pred, val in constraints.items():
            val_triple = _format_constraint_value(pred, val)
            await self.store._sparql_update(f"""
                INSERT {{
                    GRAPH <{SHAPES_GRAPH}> {{ <{shape_uri}> <{pred}> {val_triple} }}
                }}
                WHERE {{
                    FILTER NOT EXISTS {{
                        GRAPH <{SHAPES_GRAPH}> {{ <{shape_uri}> <{pred}> ?existing }}
                    }}
                }}
            """)

    async def add_class(self, class_uri: str):
        shape_uri = shape_uri_for_entity(class_uri, "class", state["prefix_map"])
        triples = f"<{shape_uri}> a sh:NodeShape ; sh:targetClass <{class_uri}> .\n"
        await self.store.insert_shapes(triples)
        self._changed()

    async def remove_class(self, class_uri: str):
        await self.store.remove_class_shape(class_uri, state["prefix_map"])
        self._changed()

    async def add_property_to_class(self, class_uri: str, prop_uri: str):
        domains = get_property_domains(prop_uri)
        if domains and not any(is_subclass(class_uri, [d]) or class_uri == d for d in domains):
            raise HTTPException(400, f"Class {class_uri} is not in domain of {prop_uri}")

        prop_shape_uri = shape_uri_for_entity(prop_uri, "property", state["prefix_map"])
        class_shape_uri = shape_uri_for_entity(class_uri, "class", state["prefix_map"])

        # Ensure property shape exists
        await self.store._sparql_update(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            INSERT {{
                GRAPH <{SHAPES_GRAPH}> {{
                    <{prop_shape_uri}> a sh:PropertyShape ; sh:path <{prop_uri}> .
                }}
            }}
            WHERE {{
                FILTER NOT EXISTS {{
                    GRAPH <{SHAPES_GRAPH}> {{ <{prop_shape_uri}> a sh:PropertyShape }}
                }}
            }}
        """)

        # Link class to property (if not already linked)
        await self.store._sparql_update(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            INSERT {{
                GRAPH <{SHAPES_GRAPH}> {{ <{class_shape_uri}> sh:property <{prop_shape_uri}> }}
            }}
            WHERE {{
                FILTER NOT EXISTS {{
                    GRAPH <{SHAPES_GRAPH}> {{ <{class_shape_uri}> sh:property <{prop_shape_uri}> }}
                }}
            }}
        """)

        await self._set_default_constraints(prop_uri, class_uri)
        self._changed()

    async def remove_property_from_class(self, class_uri: str, prop_uri: str):
        await self.store.remove_property_shape(class_uri, prop_uri, state["prefix_map"])
        self._changed()

    async def add_datatype(self, uri: str):
        shape_uri = shape_uri_for_entity(uri, "datatype", state["prefix_map"])
        triples = f"<{shape_uri}> a sh:NodeShape ; sh:targetNode <{uri}> .\n"
        await self.store.insert_shapes(triples)
        self._changed()

    async def remove_datatype(self, uri: str):
        shape_uri = shape_uri_for_entity(uri, "datatype", state["prefix_map"])
        await self.store._sparql_update(f"DELETE WHERE {{ GRAPH <{SHAPES_GRAPH}> {{ <{shape_uri}> ?p ?o }} }}")
        self._changed()

    async def add_individual(self, uri: str):
        shape_uri = shape_uri_for_entity(uri, "individual", state["prefix_map"])
        triples = f"<{shape_uri}> a sh:NodeShape ; sh:targetNode <{uri}> .\n"
        await self.store.insert_shapes(triples)
        self._changed()

    async def remove_individual(self, uri: str):
        if uri in CORE_ACTIVE_DATATYPES:
            raise HTTPException(400, "Core datatypes cannot be removed.")
        shape_uri = shape_uri_for_entity(uri, "individual", state["prefix_map"])
        await self.store._sparql_update(f"DELETE WHERE {{ GRAPH <{SHAPES_GRAPH}> {{ <{shape_uri}> ?p ?o }} }}")
        self._changed()

    async def add_property_global(self, prop_uri: str):
        shape_uri = shape_uri_for_entity(prop_uri, "property", state["prefix_map"])
        await self.store._sparql_update(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            INSERT {{
                GRAPH <{SHAPES_GRAPH}> {{
                    <{shape_uri}> a sh:PropertyShape ; sh:path <{prop_uri}> .
                }}
            }}
            WHERE {{
                FILTER NOT EXISTS {{
                    GRAPH <{SHAPES_GRAPH}> {{ <{shape_uri}> a sh:PropertyShape }}
                }}
            }}
        """)
        await self._set_default_constraints(prop_uri)
        self._changed()

    async def remove_property_global(self, prop_uri: str):
        if prop_uri in CORE_ACTIVE_ANNOTATION_PROPERTIES:
            raise HTTPException(400, "Core annotation properties cannot be removed.")
        shape_uri = shape_uri_for_entity(prop_uri, "property", state["prefix_map"])
        await self.store._sparql_update(f"DELETE WHERE {{ GRAPH <{SHAPES_GRAPH}> {{ <{shape_uri}> ?p ?o }} }}")
        self._changed()

    async def get_active_classes(self) -> List[str]:
        rows = await self.store._sparql_query(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            SELECT DISTINCT ?class WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    ?shape a sh:NodeShape ; sh:targetClass ?class .
                }}
            }}
        """)
        return [r["class"] for r in rows]

    async def get_active_properties(self) -> List[str]:
        rows = await self.store._sparql_query(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            SELECT DISTINCT ?prop WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    ?shape sh:path ?prop .
                }}
            }}
        """)
        return [r["prop"] for r in rows]

    async def get_active_individuals(self) -> List[str]:
        rows = await self.store._sparql_query(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            SELECT DISTINCT ?uri WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    ?shape a sh:NodeShape ; sh:targetNode ?uri .
                }}
            }}
        """)
        return [r["uri"] for r in rows]

    async def generate_from_metadata(self):
        if not _used_uris_set:
            await rebuild_used_uris()
        rows = await self.store._sparql_query("""
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT DISTINCT ?class ?prop WHERE {
                ?instance a ?class . ?instance ?prop ?value .
                FILTER(?prop != rdf:type) }""")
        if not rows:
            raise HTTPException(400, "No metadata instances found.")

        pairs = defaultdict(set)
        for r in rows:
            pairs[r["class"]].add(r["prop"])

        order_map = await get_global_property_order()
        NS = str(SH)

        for class_uri in pairs:
            class_shape_uri = shape_uri_for_entity(class_uri, "class", state["prefix_map"])
            await self.store._sparql_update(f"""
                INSERT {{
                    GRAPH <{SHAPES_GRAPH}> {{ <{class_shape_uri}> a <{NS}NodeShape> ; <{NS}targetClass> <{class_uri}> . }}
                }}
                WHERE {{ FILTER NOT EXISTS {{
                    GRAPH <{SHAPES_GRAPH}> {{ <{class_shape_uri}> a <{NS}NodeShape> }} }} }}""")

        all_props = {prop for props in pairs.values() for prop in props}
        for prop_uri in all_props:
            prop_shape_uri = shape_uri_for_entity(prop_uri, "property", state["prefix_map"])
            await self.store._sparql_update(f"""
                INSERT {{
                    GRAPH <{SHAPES_GRAPH}> {{ <{prop_shape_uri}> a <{NS}PropertyShape> ; <{NS}path> <{prop_uri}> . }}
                }}
                WHERE {{ FILTER NOT EXISTS {{
                    GRAPH <{SHAPES_GRAPH}> {{ <{prop_shape_uri}> a <{NS}PropertyShape> }} }} }}""")
            await self._set_default_constraints(prop_uri)
            if prop_uri in order_map:
                ord_val = order_map[prop_uri]
                ord_triple = f"<{prop_shape_uri}> <{NS}order> {_format_constraint_value(NS+'order', ord_val)} ."
                await self.store._sparql_update(f"""
                    INSERT {{ GRAPH <{SHAPES_GRAPH}> {{ {ord_triple} }} }}
                    WHERE {{ FILTER NOT EXISTS {{
                        GRAPH <{SHAPES_GRAPH}> {{ <{prop_shape_uri}> <{NS}order> ?o }} }} }}""")

        for class_uri, props in pairs.items():
            valid_props = []
            for prop_uri in props:
                domains = get_property_domains(prop_uri)
                if domains and not any(is_subclass(class_uri, [d]) or class_uri == d for d in domains):
                    continue
                valid_props.append(prop_uri)
            if valid_props:
                await _sync_entity_links(class_uri, "class", valid_props)

        dt_rows = await self.store._sparql_query("""
            SELECT DISTINCT ?dt WHERE { ?s ?p ?o . FILTER(isLiteral(?o))
            BIND(DATATYPE(?o) AS ?dt) FILTER(?dt != "") }""")
        for r in dt_rows:
            if r["dt"] in SYSTEM_DATATYPES:
                try:
                    await self.add_datatype(r["dt"])
                except Exception:
                    pass

        prop_rows = await self.store._sparql_query("SELECT DISTINCT ?prop WHERE { ?s ?prop ?o . }")
        for r in prop_rows:
            if r["prop"] in SYSTEM_ANNOTATION_PROPERTIES:
                try:
                    await self.add_property_global(r["prop"])
                except Exception:
                    pass

        self._changed()

    async def validate_instance(self, class_uris: List[str], properties: Dict[str, List[str]]):
        data_g = Graph()
        inst_uri = URIRef("urn:temp:instance")
        for cls in class_uris:
            data_g.add((inst_uri, RDF.type, URIRef(cls)))
        for pred, vals in properties.items():
            if not isinstance(vals, list):
                vals = [vals]
            for val in vals:
                if val.startswith(("http://", "urn:")):
                    data_g.add((inst_uri, URIRef(pred), URIRef(val)))
                else:
                    data_g.add((inst_uri, URIRef(pred), Literal(val)))

        explicit_shapes = await self._get_shapes_graph()
        combined = explicit_shapes + validation_ontology_graph

        if len(explicit_shapes) == 0:
            for class_uri in class_uris:
                for prop_uri, values in properties.items():
                    card = get_property_cardinality(class_uri, prop_uri)
                    if (minc := card["minCardinality"]) is not None and len(values) < minc:
                        raise HTTPException(400, f"{prop_uri} requires at least {minc} value(s)")
                    if (maxc := card["maxCardinality"]) is not None and len(values) > maxc:
                        raise HTTPException(400, f"{prop_uri} allows at most {maxc} value(s)")
            return True

        conforms, raw_graph, _ = pyshacl.validate(
            data_g, shacl_graph=combined,
            do_owl_imports=False, inference='none', abort_on_first=False
        )
        report_graph = cast(Graph, raw_graph)

        if not conforms:
            msgs = [str(o) for _, _, o in report_graph.triples((None, SH.resultMessage, None))]
            raise HTTPException(400, "SHACL validation failed: " + "; ".join(msgs))
        return True

# ---------------------------------------------------------------------------
#  Sync Entity Links
# ---------------------------------------------------------------------------
async def _sync_entity_links(entity_uri: str, etype: str, linked_uris: List[str]):
    if etype in ("object_property", "datatype_property", "annotation_property"):
        prop_shape_uri = shape_uri_for_entity(entity_uri, "property", state["prefix_map"])
        desired_classes = set(linked_uris)

        cur_rows = await store._sparql_query(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            SELECT ?class WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    ?classShape sh:targetClass ?class ; sh:property <{prop_shape_uri}> .
                }}
            }}
        """)
        current_classes = {r["class"] for r in cur_rows}

        for cls in current_classes - desired_classes:
            class_shape_uri = shape_uri_for_entity(cls, "class", state["prefix_map"])
            await store._sparql_update(f"""
                PREFIX sh: <http://www.w3.org/ns/shacl#>
                DELETE {{ GRAPH <{SHAPES_GRAPH}> {{ <{class_shape_uri}> sh:property <{prop_shape_uri}> }} }}
                WHERE  {{ GRAPH <{SHAPES_GRAPH}> {{ <{class_shape_uri}> sh:property <{prop_shape_uri}> }} }}
            """)

        for cls in desired_classes - current_classes:
            domains = get_property_domains(entity_uri)
            if domains and not any(is_subclass(cls, [d]) or cls == d for d in domains):
                raise HTTPException(400,
                    f"Class {cls} is not in the domain of property {entity_uri}")
            class_shape_uri = shape_uri_for_entity(cls, "class", state["prefix_map"])
            # Ensure class shape exists
            await store._sparql_update(f"""
                PREFIX sh: <http://www.w3.org/ns/shacl#>
                INSERT {{
                    GRAPH <{SHAPES_GRAPH}> {{ <{class_shape_uri}> a sh:NodeShape ; sh:targetClass <{cls}> }}
                }}
                WHERE {{
                    FILTER NOT EXISTS {{
                        GRAPH <{SHAPES_GRAPH}> {{ <{class_shape_uri}> a sh:NodeShape }}
                    }}
                }}
            """)
            await store._sparql_update(f"""
                PREFIX sh: <http://www.w3.org/ns/shacl#>
                INSERT {{
                    GRAPH <{SHAPES_GRAPH}> {{ <{class_shape_uri}> sh:property <{prop_shape_uri}> }}
                }}
                WHERE {{
                    FILTER NOT EXISTS {{
                        GRAPH <{SHAPES_GRAPH}> {{ <{class_shape_uri}> sh:property <{prop_shape_uri}> }}
                    }}
                }}
            """)

    elif etype == "class":
        class_shape_uri = shape_uri_for_entity(entity_uri, "class", state["prefix_map"])
        desired_props = set(linked_uris)

        await store._sparql_update(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            DELETE {{ GRAPH <{SHAPES_GRAPH}> {{ <{class_shape_uri}> sh:property ?ps }} }}
            WHERE  {{ GRAPH <{SHAPES_GRAPH}> {{ <{class_shape_uri}> sh:property ?ps }} }}
        """)

        for prop_uri in desired_props:
            domains = get_property_domains(prop_uri)
            if domains and not any(is_subclass(entity_uri, [d]) or entity_uri == d for d in domains):
                raise HTTPException(400,
                    f"Property {prop_uri} does not have class {entity_uri} in its domain")
            prop_shape_uri = shape_uri_for_entity(prop_uri, "property", state["prefix_map"])
            await store._sparql_update(f"""
                PREFIX sh: <http://www.w3.org/ns/shacl#>
                INSERT {{
                    GRAPH <{SHAPES_GRAPH}> {{ <{prop_shape_uri}> a sh:PropertyShape ; sh:path <{prop_uri}> }}
                }}
                WHERE {{
                    FILTER NOT EXISTS {{
                        GRAPH <{SHAPES_GRAPH}> {{ <{prop_shape_uri}> a sh:PropertyShape }}
                    }}
                }}
            """)
            await store._sparql_update(f"""
                PREFIX sh: <http://www.w3.org/ns/shacl#>
                INSERT DATA {{
                    GRAPH <{SHAPES_GRAPH}> {{ <{class_shape_uri}> sh:property <{prop_shape_uri}> }}
                }}
            """)

# ---------------------------------------------------------------------------
#  Plugin & Theme Helpers
# ---------------------------------------------------------------------------
def load_plugins_config():
    if not os.path.exists(PLUGINS_CONFIG_FILE):
        return {}
    with open(PLUGINS_CONFIG_FILE) as f:
        return json.load(f)

def save_plugins_config(config):
    os.makedirs(os.path.dirname(PLUGINS_CONFIG_FILE), exist_ok=True)
    with open(PLUGINS_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def list_plugins():
    if not os.path.isdir(PLUGINS_DIR):
        return []
    config = load_plugins_config()
    plugins = []
    for entry in os.listdir(PLUGINS_DIR):
        plugin_path = os.path.join(PLUGINS_DIR, entry)
        if not os.path.isdir(plugin_path):
            continue
        meta_file = os.path.join(plugin_path, "plugin.json")
        if not os.path.exists(meta_file):
            continue
        try:
            with open(meta_file) as f:
                meta = json.load(f)
        except Exception:
            meta = {}
        plugins.append({
            "folder": entry,
            "name": meta.get("name", entry),
            "version": meta.get("version", ""),
            "description": meta.get("description", ""),
            "enabled": config.get(entry, {}).get("enabled", False),
        })
    return plugins

def load_plugins():
    if not os.path.isdir(PLUGINS_DIR):
        return
    config = load_plugins_config()
    for entry in os.listdir(PLUGINS_DIR):
        plugin_path = os.path.join(PLUGINS_DIR, entry)
        if not os.path.isdir(plugin_path):
            continue
        if not config.get(entry, {}).get("enabled", False):
            continue
        backend_init = os.path.join(plugin_path, "backend", "__init__.py")
        if not os.path.exists(backend_init):
            continue
        try:
            mod = importlib.import_module(f"plugins.{entry}.backend")
            if hasattr(mod, "register"):
                mod.register({
                    "app": app,
                    "store": store,
                    "state": state,
                    "shacl": shacl,
                    "ap": ap,
                })
        except Exception as e:
            print(f"Failed to load plugin {entry}: {e}")

def load_themes_config():
    if not os.path.exists(THEMES_CONFIG_FILE):
        return {}
    with open(THEMES_CONFIG_FILE) as f:
        return json.load(f)

def save_themes_config(config):
    os.makedirs(os.path.dirname(THEMES_CONFIG_FILE), exist_ok=True)
    with open(THEMES_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def list_themes():
    themes = [{
        "folder": "default",
        "name": "Default Theme",
        "version": "",
        "description": "The built‑in public theme.",
        "enabled": True,
        "removable": False,
    }]
    if not os.path.isdir(THEMES_DIR):
        return themes
    config = load_themes_config()
    for entry in os.listdir(THEMES_DIR):
        theme_path = os.path.join(THEMES_DIR, entry)
        if not os.path.isdir(theme_path):
            continue
        meta_file = os.path.join(theme_path, "theme.json")
        if not os.path.exists(meta_file):
            continue
        try:
            with open(meta_file) as f:
                meta = json.load(f)
        except Exception:
            meta = {}
        themes.append({
            "folder": entry,
            "name": meta.get("name", entry),
            "version": meta.get("version", ""),
            "description": meta.get("description", ""),
            "enabled": config.get(entry, {}).get("enabled", False),
            "removable": True,
        })
    return themes

def set_active_theme(theme_folder: str):
    os.makedirs(os.path.dirname(FRONTEND_ACTIVE_THEME_FILE), exist_ok=True)
    with open(FRONTEND_ACTIVE_THEME_FILE, "w") as f:
        json.dump({"active_theme": theme_folder}, f)

# ---------------------------------------------------------------------------
#  Startup Helpers
# ---------------------------------------------------------------------------
async def seed_core_active_entities():
    for uri in CORE_ACTIVE_DATATYPES:
        try:
            await shacl.add_datatype(uri)
        except Exception:
            pass
    for uri in CORE_ACTIVE_ANNOTATION_PROPERTIES:
        try:
            await shacl.add_property_global(uri)
        except Exception:
            pass

def add_default_prefixes():
    default_prefixes = {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "owl": "http://www.w3.org/2002/07/owl#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
    }
    for prefix, ns in default_prefixes.items():
        if ns not in state["prefix_map"]:
            state["prefix_map"][ns] = prefix
        state["all_ontology_namespaces"].add(ns)

def get_reasoned_graph(original_path: str, fmt: str) -> tuple[Graph, Graph]:
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_filename = os.path.basename(original_path) + ".reasoned.ttl"
    cache_path = os.path.join(CACHE_DIR, cache_filename)

    if os.path.exists(cache_path) and os.path.getmtime(cache_path) >= os.path.getmtime(original_path):
        g = Graph()
        g.parse(cache_path, format="turtle")
        with open(original_path, 'rb') as fh:
            content = fh.read()
        unreasoned = parse_ontology(content, fmt)
        return unreasoned, g

    with open(original_path, 'rb') as fh:
        content = fh.read()
    unreasoned = parse_ontology(content, fmt)
    g = Graph()
    for t in unreasoned:
        g.add(t)
    apply_reasoning(g)
    g.serialize(destination=cache_path, format="turtle")
    return unreasoned, g

def load_saved_ontologies():
    if not os.path.isdir(ONTOLOGY_DIR):
        return
    for f in os.listdir(ONTOLOGY_DIR):
        if not f.endswith(('.rdf','.owl','.xml','.ttl','.nt','.jsonld','.json','.trig','.trix')):
            continue
        path = os.path.join(ONTOLOGY_DIR, f)
        try:
            ext = f.rsplit('.', 1)[-1].lower()
            fmt = RDF_FORMAT_MAP.get(ext, "xml")
            unreasoned_g, g = get_reasoned_graph(path, fmt)
            entities = process_ontology(g, f)
            meta = extract_ontology_metadata(g)
            onto = {
                "filename": f,
                "graph": g,
                "original_graph": unreasoned_g,
                "meta": meta,
                "entities": entities,
            }
            onto["namespaces"] = get_ontology_namespaces(g)
            state["ontologies"].append(onto)
            state["all_ontology_namespaces"].update(onto["namespaces"])
            for t in g:
                state["combined_onto_graph"].add(t)
            update_prefix_map(g, state["prefix_map"])
        except Exception as e:
            print(f"Warning: Could not load {f}: {e}")

def load_saved_metadata():
    if not os.path.isdir(METADATA_DIR):
        return
    for f in list_saved_metadata_files():
        path = os.path.join(METADATA_DIR, f)
        try:
            with open(path, 'rb') as fh:
                data = fh.read()
            g = parse_metadata(data, RDF_FORMAT_MAP.get(f.rsplit('.',1)[-1].lower(), "nt"))
            meta_path = path + ".meta.json"
            vocab_int = True
            inst_merge = True
            if os.path.exists(meta_path):
                try:
                    with open(meta_path) as mf:
                        meta_info = json.load(mf)
                    vocab_int = meta_info.get("vocab_integrated", True)
                    inst_merge = meta_info.get("instances_merged", True)
                except Exception:
                    pass
            state["metadata_files"].append({
                "filename": f,
                "graph": g,
                "vocab_integrated": vocab_int,
                "instances_merged": inst_merge
            })
            for s in g.subjects():
                if not str(s).startswith("urn:bnid:"):
                    _metadata_uris.add(str(s))
            for t in g:
                state["merged_metadata_graph"].add(t)
            if not vocab_int:
                for s, p, o in g:
                    for term in (s, p, o):
                        if isinstance(term, URIRef):
                            uri = str(term)
                            if not uri.startswith("urn:bnid:"):
                                state["non_integrated_uris"].add(uri)
        except Exception as e:
            print(f"Warning: Could not load metadata {f}: {e}")

# Create global service instances (after all class definitions)
FUSEKI_DATASET_URL = os.getenv("FUSEKI_DATASET_URL", "http://localhost:3030/obmms")
store = FusekiStore(dataset_url=FUSEKI_DATASET_URL, label_properties=LABEL_PROPERTIES)
ap = ApplicationProfile(store)
shacl = SHACLProfile(store, on_change=invalidate_profile)

@asynccontextmanager
async def lifespan(app: FastAPI):
    add_default_prefixes()
    progress["phase"] = "Loading ontologies…"
    load_saved_ontologies()
    progress["phase"] = "Building indexes…"
    rebuild_precomputed()
    store.set_label_properties(LABEL_PROPERTIES)
    progress["phase"] = "Loading metadata…"
    load_saved_metadata()
    # Load starred instances
    if os.path.exists(STARS_FILE):
        with open(STARS_FILE) as f:
            state["starred_instance_uris"] = set(json.load(f))
    if state["created_instances"]:
        values = " ".join(f"<{u}>" for u in state["created_instances"])
        query = f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ VALUES ?s {{ {values} }} . ?s ?p ?o . }}"
        turtle = await store._sparql_construct(query)
        state["created_instances_graph"].parse(data=turtle, format="turtle")
    await rebuild_used_uris()
    load_plugins()
    state["display_format"] = load_preferences().get("display_format", "iri")
    state["public_display_blank_nodes"] = load_preferences().get("public_display_blank_nodes", False)
    settings = load_settings()
    state["site_title"] = settings.get("site_title", "Semantta")
    state["base_iri"] = settings.get("base_iri", "")
    active_theme = settings.get("active_theme", "default")
    set_active_theme(active_theme)
    await seed_core_active_entities()
    progress["phase"] = ""
    yield
    await store.close()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ===========================================================================
#  API ENDPOINTS
# ===========================================================================

@app.get("/api/state", response_model=StateResponse)
async def get_state():
    profile_entities = await ap.build_profile_entities()
    ontos = [OntologyInfo(
        filename=o["filename"],
        title=o["meta"]["title"],
        version=o["meta"]["version"],
        iri=o["meta"]["iri"],
        namespaces=o.get("namespaces", []),
    ) for o in state["ontologies"]]
    meta_files = []
    for mf in state["metadata_files"]:
        g = mf["graph"]
        primary = next((str(s) for s in g.subjects() if not str(s).startswith("urn:bnid:")), None)
        vocab_ns = set()
        for p in g.predicates():
            if isinstance(p, URIRef):
                ns = safe_namespace(str(p))
                if ns: vocab_ns.add(ns)
        for t in g.objects(None, RDF.type):
            if isinstance(t, URIRef):
                ns = safe_namespace(str(t))
                if ns: vocab_ns.add(ns)
        inst_count = len({s for s in g.subjects() if not str(s).startswith("urn:bnid:")})
        meta_files.append(MetadataFileInfo(
            filename=mf["filename"], primary_iri=primary, namespaces=sorted(vocab_ns),
            instances_count=inst_count, triples_count=len(g),
            vocab_integrated=mf.get("vocab_integrated", True), instances_merged=mf.get("instances_merged", True)
        ))
    await refresh_instances_from_store()
    return StateResponse(
        ontologies=ontos,
        metadata_files=meta_files,
        profile_entities=profile_entities,
        instances=state["instances"],
        display_format=state["display_format"],
        prefix_map=state["prefix_map"],
        public_display_blank_nodes=load_preferences().get("public_display_blank_nodes", False),
        ontology_namespaces=sorted(state["all_ontology_namespaces"]),
        site_title=state.get("site_title", "Semantta"),
        base_iri=state.get("base_iri", "")
    )

@app.post("/api/ontology/upload")
async def upload_ontology(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "No file selected")
    # At this point file.filename is guaranteed to be a string,
    # but Pylance doesn't narrow it inside nested functions.
    filename: str = file.filename

    if any(o["filename"] == filename for o in state["ontologies"]):
        raise HTTPException(400, f"Ontology '{filename}' is already imported.")

    contents = await file.read()
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    fmt = RDF_FORMAT_MAP.get(ext)
    if not fmt:
        raise HTTPException(400, f"Unsupported extension: .{ext}")

    def do_import():
        progress["phase"] = "Parsing RDF/XML…"
        g = parse_ontology(contents, fmt)
        unreasoned = Graph()
        for t in g:
            unreasoned.add(t)
        progress["phase"] = "Applying OWL‑RL reasoning…"
        apply_reasoning(g)
        progress["phase"] = "Extracting entities…"
        entities = process_ontology(g, "")
        meta = extract_ontology_metadata(g)
        progress["phase"] = "Saving to disk…"
        os.makedirs(ONTOLOGY_DIR, exist_ok=True)
        with open(os.path.join(ONTOLOGY_DIR, filename), 'wb') as f:
            f.write(contents)
        g.serialize(
            destination=os.path.join(CACHE_DIR, filename + ".reasoned.ttl"),
            format="turtle"
        )
        return unreasoned, g, entities, meta

    try:
        unreasoned_g, g, entities, meta = await asyncio.to_thread(do_import)
    except Exception as e:
        raise HTTPException(400, detail=f"Import failed: {str(e)}")
    finally:
        progress["phase"] = ""

    onto = {
        "filename": filename,
        "graph": g,
        "original_graph": unreasoned_g,
        "meta": meta,
        "entities": entities,
    }
    onto["namespaces"] = get_ontology_namespaces(g)
    state["ontologies"].append(onto)
    state["all_ontology_namespaces"].update(onto["namespaces"])
    for t in g:
        state["combined_onto_graph"].add(t)
    update_prefix_map(g, state["prefix_map"])
    for e in entities:
        await ap.resolve_entity_with_ontology(e["uri"])
    invalidate_caches()
    ap.invalidate()
    return {"status": "ok", "filename": filename}

@app.delete("/api/ontology/{filename}")
async def delete_ontology(filename: str):
    before = len(state["ontologies"])
    state["ontologies"] = [o for o in state["ontologies"] if o["filename"] != filename]
    if len(state["ontologies"]) == before:
        raise HTTPException(404, "Ontology not found")
    filepath = os.path.join(ONTOLOGY_DIR, filename)
    if os.path.exists(filepath): os.remove(filepath)
    cache_path = os.path.join(CACHE_DIR, filename + ".reasoned.ttl")
    if os.path.exists(cache_path): os.remove(cache_path)
    state["combined_onto_graph"] = Graph()
    state["prefix_map"].clear()
    for o in state["ontologies"]:
        for t in o["graph"]: state["combined_onto_graph"].add(t)
        update_prefix_map(o["graph"], state["prefix_map"])
    state["all_ontology_namespaces"].clear()
    for o in state["ontologies"]:
        if "namespaces" in o: state["all_ontology_namespaces"].update(o["namespaces"])
    invalidate_everything()
    active_props = await shacl.get_active_properties()
    for prop_uri in active_props:
        await shacl._set_default_constraints(prop_uri, class_uri=None)
    return {"status": "ok"}

@app.post("/api/metadata/upload")
async def upload_metadata(
    file: UploadFile = File(...),
    integrate_vocab: bool = Form(True),
    merge_instances: bool = Form(True)
):
    if not state["ontologies"]:
        raise HTTPException(400, "Upload an ontology first.")
    if not file.filename:
        raise HTTPException(400, "No file selected.")

    # Safely capture the filename as a plain string
    filename: str = file.filename

    if not state["metadata_files"] and not state["created_instances"]:
        merge_instances = True

    contents = await file.read()
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    fmt = RDF_FORMAT_MAP.get(ext)
    if not fmt:
        raise HTTPException(400, f"Unsupported extension: .{ext}")

    def do_import():
        progress["phase"] = "Parsing metadata…"
        new_g = parse_metadata(contents, fmt)

        progress["phase"] = "Merging metadata…"
        if merge_instances:
            for t in new_g:
                state["merged_metadata_graph"].add(t)
            collapse_identical_blank_nodes(state["merged_metadata_graph"])
        else:
            state["merged_metadata_graph"] = new_g
            for t in state["created_instances_graph"]:
                state["merged_metadata_graph"].add(t)
            collapse_identical_blank_nodes(state["merged_metadata_graph"])
            state["metadata_files"] = []
            state["non_integrated_uris"].clear()
            state["metadata_only_sources"].clear()

        return new_g

    try:
        new_g = await asyncio.to_thread(do_import)
    except Exception as e:
        raise HTTPException(400, detail=f"Import failed: {str(e)}")
    finally:
        progress["phase"] = ""

    # ── Save to disk ──
    progress["phase"] = "Saving metadata to disk…"
    os.makedirs(METADATA_DIR, exist_ok=True)
    with open(os.path.join(METADATA_DIR, filename), 'wb') as f:
        f.write(contents)

    # Save integration flags as a .meta.json sidecar
    meta_path = os.path.join(METADATA_DIR, filename + ".meta.json")
    meta_info = {
        "vocab_integrated": integrate_vocab,
        "instances_merged": merge_instances,
    }
    with open(meta_path, 'w') as mf:
        json.dump(meta_info, mf)

    # ── Update in‑memory state ──
    state["metadata_files"].append({
        "filename": filename,
        "graph": new_g,
        "vocab_integrated": integrate_vocab,
        "instances_merged": merge_instances
    })

    for s in new_g.subjects():
        if not str(s).startswith("urn:bnid:"):
            _metadata_uris.add(str(s))

    progress["phase"] = "Importing into Fuseki…"
    nt_data = state["merged_metadata_graph"].serialize(format="nt")
    await store._sparql_update("CLEAR DEFAULT")
    await store.bulk_load_nt(nt_data)

    if integrate_vocab:
        progress["phase"] = "Integrating vocabulary…"
        for s in new_g.subjects():
            if not str(s).startswith("urn:bnid:"):
                await ap.merge_metadata_only_entity(str(s), filename)
    else:
        for s, p, o in new_g:
            for term in (s, p, o):
                if isinstance(term, URIRef) and not str(term).startswith("urn:bnid:"):
                    state["non_integrated_uris"].add(str(term))

    progress["phase"] = "Rebuilding caches…"
    invalidate_caches()
    ap.invalidate()
    await refresh_instances_from_store()
    await rebuild_used_uris()

    progress["phase"] = ""
    return {"status": "ok", "filename": filename}

@app.post("/api/metadata/create")
async def create_instance(data: dict):
    class_uris = data.get("class_uris", [data.get("class_uri")])
    class_uris = [c for c in class_uris if c]
    if not class_uris:
        raise HTTPException(400, "At least one valid class URI is required")
    await check_disjoint_classes(class_uris)
    for cls in class_uris:
        if not is_valid_uri(cls):
            raise HTTPException(400, f"Invalid class URI: {cls}")

    instance_uri = data.get("instance_uri")
    if not instance_uri:
        base_iri = state.get("base_iri", "").strip()
        if base_iri:
            if not base_iri.endswith('/'):
                base_iri += '/'
            instance_uri = f"{base_iri}{uuid.uuid4()}"
        else:
            instance_uri = f"urn:uuid:{uuid.uuid4()}"
            while True:
                candidate = f"urn:uuid:{uuid.uuid4()}"
                rows = await store._sparql_query(f"SELECT ?p WHERE {{ <{candidate}> ?p ?o }} LIMIT 1")
                if not rows:
                    instance_uri = candidate
                    break

    properties = data.get("properties", {})
    await shacl.validate_instance(class_uris, properties)

    lines = [f"<{instance_uri}> a <{c}> ." for c in class_uris]
    for pred, vals in properties.items():
        if not isinstance(vals, list): vals = [vals]
        for val in vals:
            if isinstance(val, str) and (val.startswith(("http://", "urn:"))):
                lines.append(f"<{instance_uri}> <{pred}> <{val}> .")
            else:
                safe = val.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
                lines.append(f'<{instance_uri}> <{pred}> "{safe}" .')
    triples = "\n".join(lines)
    await store._sparql_update(f"INSERT DATA {{ {triples} }}")
    g = Graph()
    g.parse(data=triples, format="turtle")
    for t in g: state["created_instances_graph"].add(t)
    state["created_instances"].add(instance_uri)
    await refresh_instances_from_store()
    invalidate_profile()
    return {"status": "created", "uri": instance_uri}

@app.get("/api/instances/{uri:path}/syntax")
async def get_instance_syntax(uri: str, format: str = "turtle"):
    mime_map = {
        "turtle": "text/turtle",
        "nt": "application/n-triples",
        "xml": "application/rdf+xml",
        "jsonld": "application/ld+json",
        "json-ld": "application/ld+json",
        "trig": "application/trig",
        "nquads": "application/n-quads",
    }
    accept = mime_map.get(format, "text/turtle")
    query = f"""
        CONSTRUCT {{ <{uri}> ?p ?o . ?s ?p <{uri}> . }}
        WHERE {{ {{ <{uri}> ?p ?o . }} UNION {{ ?s ?p <{uri}> . }} }}
    """
    resp = await store.client.get(store.query_url, params={"query": query}, headers={"Accept": accept})
    resp.raise_for_status()
    return Response(content=resp.text, media_type=accept)

@app.post("/api/instances/{uri:path}/star")
async def toggle_star(uri: str):
    starred = state.setdefault("starred_instance_uris", set())
    if uri in starred:
        starred.discard(uri)
    else:
        starred.add(uri)

    # Persist to disk
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STARS_FILE, "w") as f:
        json.dump(list(starred), f)

    # Update the in‑memory instance list
    for inst in state.get("instances", []):
        if inst["uri"] == uri:
            inst["starred"] = uri in starred
            break

    return {"status": "ok", "starred": uri in starred}

@app.get("/api/instances/{uri:path}")
async def get_instance(uri: str):
    if uri == "undefined" or not uri.startswith(("http://", "https://", "urn:")):
        raise HTTPException(400, "Invalid instance URI")

    rows = await store._sparql_query(f"""
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?type ?prop ?value WHERE {{
            <{uri}> a ?type .
            OPTIONAL {{ <{uri}> ?prop ?value . FILTER(?prop != rdf:type) }}
        }}
    """)
    if not rows:
        raise HTTPException(404, "Instance not found")

    types = []
    props: Dict[str, List[str]] = {}
    for r in rows:
        t = r.get("type")
        if t and t not in types:
            types.append(t)
        p = r.get("prop")
        v = r.get("value")
        if p and v:
            props.setdefault(p, []).append(v)

    for pred in props:
        props[pred] = list(set(props[pred]))

    # (blank‑node handling unchanged – keep as is)
    bnodes: Dict[str, dict] = {}
    blank_node_uris = [val for vals in props.values() for val in vals if val.startswith("urn:bnid:")]
    if blank_node_uris:
        values = " ".join(f"<{u}>" for u in blank_node_uris)
        bnode_rows = await store._sparql_query(f"""
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?bnode ?type ?prop ?value WHERE {{
                VALUES ?bnode {{ {values} }}
                OPTIONAL {{ ?bnode a ?type . }}
                OPTIONAL {{ ?bnode ?prop ?value . FILTER(?prop != rdf:type) }}
            }}
        """)
        for r in bnode_rows:
            bnode = r["bnode"]
            if bnode not in bnodes:
                bnodes[bnode] = {"types": [], "properties": {}, "label": None}
            t = r.get("type")
            if t and t not in bnodes[bnode]["types"]:
                bnodes[bnode]["types"].append(t)
            p = r.get("prop")
            v = r.get("value")
            if p and v:
                if p == str(RDFS.label) and bnodes[bnode]["label"] is None:
                    bnodes[bnode]["label"] = v
                bnodes[bnode]["properties"].setdefault(p, []).append(v)
        for bnode in bnodes:
            for pred in bnodes[bnode]["properties"]:
                bnodes[bnode]["properties"][pred] = list(set(bnodes[bnode]["properties"][pred]))

    return {"uri": uri, "types": types, "properties": props, "bnodes": bnodes}

@app.put("/api/instances/{uri:path}")
async def update_instance(uri: str, data: dict):
    class_uris = data.get("class_uris", [])
    class_uris = [c for c in class_uris if c]
    if not class_uris:
        raise HTTPException(400, "At least one valid class URI is required")
    await check_disjoint_classes(class_uris)
    properties = data.get("properties", {})
    await shacl.validate_instance(class_uris, properties)
    await store._sparql_update(f"DELETE {{ <{uri}> ?p ?o }} WHERE {{ <{uri}> ?p ?o }}")
    triples = "\n".join(f"<{uri}> a <{c}> ." for c in class_uris)
    for pred, vals in properties.items():
        if not isinstance(vals, list): vals = [vals]
        for val in vals:
            if isinstance(val, str) and (val.startswith(("http://", "urn:"))):
                triples += f"\n<{uri}> <{pred}> <{val}> ."
            else:
                safe_val = val.replace("\\","\\\\").replace('"','\\"').replace("\n","\\n")
                triples += f'\n<{uri}> <{pred}> "{safe_val}" .'
    if triples: await store._sparql_update(f"INSERT DATA {{ {triples} }}")
    await refresh_instances_from_store()
    invalidate_profile()
    return {"status": "ok"}

@app.delete("/api/instances/{uri:path}")
async def delete_instance(uri: str):
    await store._sparql_update(f"DELETE WHERE {{ <{uri}> ?p ?o }}")
    await store._sparql_update(f"DELETE WHERE {{ ?s ?p <{uri}> }}")
    state["created_instances"].discard(uri)
    for t in list(state["created_instances_graph"].triples((URIRef(uri), None, None))):
        state["created_instances_graph"].remove(t)
    await refresh_instances_from_store()
    invalidate_profile()
    return {"status": "ok"}

@app.post("/api/metadata/file/{filename:path}/integrate-vocab")
async def integrate_file_vocab(filename: str):
    mf = next((f for f in state["metadata_files"] if f["filename"] == filename), None)
    if not mf: raise HTTPException(404, "Metadata file not found")
    if mf.get("vocab_integrated", True): return {"status": "already integrated"}
    for s, p, o in mf["graph"]:
        for term in (s, p, o):
            if isinstance(term, URIRef) and not str(term).startswith("urn:bnid:"):
                state["non_integrated_uris"].discard(str(term))
                await ap.merge_metadata_only_entity(str(term), filename)
    mf["vocab_integrated"] = True
    meta_path = os.path.join(METADATA_DIR, filename + ".meta.json")
    try:
        with open(meta_path) as mf_meta: meta = json.load(mf_meta)
    except Exception: meta = {}
    meta["vocab_integrated"] = True
    with open(meta_path, 'w') as mf_meta: json.dump(meta, mf_meta)
    invalidate_profile()
    return {"status": "ok"}

@app.post("/api/metadata/file/{filename:path}/merge-metadata")
async def merge_file_metadata(filename: str):
    mf = next((f for f in state["metadata_files"] if f["filename"] == filename), None)
    if not mf: raise HTTPException(404, "Metadata file not found")
    if mf.get("instances_merged", True): return {"status": "already merged"}
    for t in mf["graph"]: state["merged_metadata_graph"].add(t)
    collapse_identical_blank_nodes(state["merged_metadata_graph"])
    nt_data = state["merged_metadata_graph"].serialize(format="nt")
    await store._sparql_update("CLEAR DEFAULT")
    await store.bulk_load_nt(nt_data)
    mf["instances_merged"] = True
    await refresh_instances_from_store()
    await rebuild_used_uris()
    invalidate_profile()
    return {"status": "ok"}

@app.get("/api/metadata/raw/{filename:path}")
async def get_raw_metadata(filename: str):
    filepath = os.path.join(METADATA_DIR, filename)
    if not os.path.exists(filepath): raise HTTPException(404, "Metadata file not found")
    return FileResponse(filepath)

@app.delete("/api/metadata/{filename}")
async def delete_metadata(filename: str):
    before = len(state["metadata_files"])
    state["metadata_files"] = [mf for mf in state["metadata_files"] if mf["filename"] != filename]
    if len(state["metadata_files"]) == before: raise HTTPException(404, "Metadata file not found")
    _metadata_uris.clear()
    for mf in state["metadata_files"]:
        for s in mf["graph"].subjects():
            if not str(s).startswith("urn:bnid:"): _metadata_uris.add(str(s))
    filepath = os.path.join(METADATA_DIR, filename)
    if os.path.exists(filepath): os.remove(filepath)
    meta_path = filepath + ".meta.json"
    if os.path.exists(meta_path): os.remove(meta_path)
    state["merged_metadata_graph"] = Graph()
    for mf in state["metadata_files"]:
        for t in mf["graph"]: state["merged_metadata_graph"].add(t)
    for t in state["created_instances_graph"]: state["merged_metadata_graph"].add(t)
    await store._sparql_update("CLEAR DEFAULT")
    if state["metadata_files"] or state["created_instances_graph"]:
        nt_data = state["merged_metadata_graph"].serialize(format="nt")
        await store.bulk_load_nt(nt_data)
    await refresh_instances_from_store()
    await rebuild_used_uris()
    invalidate_everything()
    return {"status": "ok"}

@app.post("/api/profile/toggle")
async def toggle_entity(req: ToggleRequest):
    etype = await ap.get_entity_type(req.uri)
    if etype == "class":
        if req.active: await shacl.add_class(req.uri)
        else: await shacl.remove_class(req.uri)
    elif etype in ("object_property", "datatype_property", "annotation_property"):
        if req.active: await shacl.add_property_global(req.uri)
        else: await shacl.remove_property_global(req.uri)
    elif etype == "individual":
        if req.active: await shacl.add_individual(req.uri)
        else: await shacl.remove_individual(req.uri)
    elif etype == "datatype":
        if req.active: await shacl.add_datatype(req.uri)
        else: await shacl.remove_datatype(req.uri)
    return {"status": "ok"}

@app.get("/api/create-form/classes")
async def get_active_classes():
    return [{"uri": uri, "label": get_label(uri)} for uri in await ap.get_active_classes()]

@app.get("/api/create-form/properties")
async def get_properties_for_class(class_uri: str):
    return {"class_uri": class_uri, "properties": await ap.get_properties_for_class(class_uri)}

@app.get("/api/profile/constraints/{entity_uri:path}")
async def get_entity_constraints(entity_uri: str):
    etype = await ap.get_entity_type(entity_uri)
    original = get_original_constraints(entity_uri, etype, state["combined_onto_graph"])
    overrides = {}

    if etype in ("object_property", "datatype_property", "annotation_property"):
        rows = await store._sparql_query(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?pred ?val WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    ?ps sh:path <{entity_uri}> ; ?pred ?val .
                    FILTER(?pred NOT IN (sh:path, sh:order, rdf:type))
                }}
            }}
        """)
        grouped = defaultdict(list)
        for r in rows: grouped[r["pred"]].append(r["val"])
        multi_valued = {str(SH["in"]), str(SH.languageIn)}
        for pred, vals in grouped.items():
            if pred in multi_valued or len(vals) > 1: overrides[pred] = vals
            else: overrides[pred] = vals[0]

        prop_shape_uri = shape_uri_for_entity(entity_uri, "property", state["prefix_map"])
        domain_rows = await store._sparql_query(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            SELECT ?class WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    ?classShape sh:targetClass ?class ; sh:property <{prop_shape_uri}> .
                }}
            }}
        """)
        domain_classes = [r["class"] for r in domain_rows]
        if domain_classes: overrides["urn:domainClasses"] = domain_classes
        orig_domains = get_property_domains(entity_uri)
        original["urn:domainClasses"] = orig_domains if orig_domains else []

        if etype == "object_property":
            ranges = original.get(str(RDFS.range), [])
            if ranges: original[str(SH["class"])] = [ranges[0]]
        elif etype in ("datatype_property", "annotation_property"):
            ranges = original.get(str(RDFS.range), [])
            if ranges: original[str(SH.datatype)] = [ranges[0]]

    elif etype == "class":
        class_shape_uri = shape_uri_for_entity(entity_uri, "class", state["prefix_map"])
        rows = await store._sparql_query(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?pred ?val WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    <{class_shape_uri}> ?pred ?val .
                    FILTER(?pred NOT IN (rdf:type, sh:targetClass, sh:property))
                }}
            }}
        """)
        grouped = defaultdict(list)
        for r in rows: grouped[r["pred"]].append(r["val"])
        multi_valued = {str(SH["in"]), str(SH.languageIn)}
        for pred, vals in grouped.items():
            if pred in multi_valued or len(vals) > 1: overrides[pred] = vals
            else: overrides[pred] = vals[0]

        prop_shape_rows = await store._sparql_query(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            SELECT ?propShape WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{ <{class_shape_uri}> sh:property ?propShape . }}
            }}
        """)
        if prop_shape_rows:
            prop_shape_uris = [r["propShape"] for r in prop_shape_rows]
            values = " ".join(f"<{u}>" for u in prop_shape_uris)
            prop_uri_rows = await store._sparql_query(f"""
                PREFIX sh: <http://www.w3.org/ns/shacl#>
                SELECT ?propShape ?propUri WHERE {{
                    GRAPH <{SHAPES_GRAPH}> {{
                        VALUES ?propShape {{ {values} }}
                        ?propShape sh:path ?propUri .
                    }}
                }}
            """)
            prop_uri_map = {r["propShape"]: r["propUri"] for r in prop_uri_rows}
            property_uris = [prop_uri_map.get(ps, ps) for ps in prop_shape_uris]
            overrides[str(SH.property)] = property_uris

        original_props = []
        for prop_uri in _property_domains:
            if entity_uri in get_property_domains(prop_uri): original_props.append(prop_uri)
        original[str(SH.property)] = original_props

    return {"uri": entity_uri, "type": etype, "original": original, "overrides": overrides}

@app.put("/api/profile/constraints/{entity_uri:path}")
async def set_entity_constraints(entity_uri: str, constraints: dict):
    etype = await ap.get_entity_type(entity_uri)
    validate_constraints(entity_uri, etype, constraints)

    if etype in ("object_property", "datatype_property", "annotation_property"):
        rows = await store._sparql_query(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            SELECT ?ps WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{ ?ps sh:path <{entity_uri}> . }}
            }}
        """)
        for r in rows:
            await _apply_constraints(r["ps"], constraints,
                                     keep_predicates={RDF.type, SH.path, SH.order, SH.property})
        if "urn:domainClasses" in constraints:
            await _sync_entity_links(entity_uri, etype, constraints["urn:domainClasses"])
            del constraints["urn:domainClasses"]

    elif etype == "class":
        class_shape_uri = shape_uri_for_entity(entity_uri, "class", state["prefix_map"])
        await _apply_constraints(class_shape_uri, constraints,
                                 keep_predicates={RDF.type, SH.targetClass, SH.property})
        if str(SH.property) in constraints:
            prop_uris = (constraints[str(SH.property)]
                         if isinstance(constraints[str(SH.property)], list)
                         else [constraints[str(SH.property)]])
            await _sync_entity_links(entity_uri, etype, prop_uris)
            del constraints[str(SH.property)]

    invalidate_profile()
    return {"status": "ok"}

@app.post("/api/profile/add-property")
async def add_property_to_class_endpoint(req: dict):
    _require_keys(req, "class_uri", "prop_uri")
    await shacl.add_property_to_class(req["class_uri"], req["prop_uri"])
    return {"status": "ok"}

@app.post("/api/profile/remove-property")
async def remove_property_from_class_endpoint(req: dict):
    _require_keys(req, "class_uri", "prop_uri")
    await shacl.remove_property_from_class(req["class_uri"], req["prop_uri"])
    return {"status": "ok"}

@app.post("/api/profile/add-property-global")
async def add_property_global_endpoint(req: dict):
    _require_keys(req, "prop_uri")
    await shacl.add_property_global(req["prop_uri"])
    return {"status": "ok"}

@app.post("/api/profile/remove-property-global")
async def remove_property_global_endpoint(req: dict):
    _require_keys(req, "prop_uri")
    await shacl.remove_property_global(req["prop_uri"])
    return {"status": "ok"}

@app.post("/api/profile/add-individual")
async def add_individual_endpoint(req: dict):
    _require_keys(req, "uri")
    await shacl.add_individual(req["uri"])
    return {"status": "ok"}

@app.post("/api/profile/remove-individual")
async def remove_individual_endpoint(req: dict):
    _require_keys(req, "uri")
    await shacl.remove_individual(req["uri"])
    return {"status": "ok"}

@app.post("/api/profile/add-datatype")
async def add_datatype_endpoint(req: dict):
    _require_keys(req, "uri")
    await shacl.add_datatype(req["uri"])
    return {"status": "ok"}

@app.post("/api/profile/remove-datatype")
async def remove_datatype_endpoint(req: dict):
    _require_keys(req, "uri")
    await shacl.remove_datatype(req["uri"])
    return {"status": "ok"}

@app.post("/api/profile/generate")
async def generate_profile_from_metadata():
    try:
        await shacl.generate_from_metadata()
        return {"status": "ok"}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(500, f"Profile generation failed: {str(e)}")

@app.post("/api/profile/update-order")
async def update_profile_order(data: dict):
    items = data.get("items", [])
    for item in items:
        uri = item["uri"]
        order_val = item["order"]
        shape_uri = shape_uri_for_entity(uri, "property", state["prefix_map"])

        await store._sparql_update(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            DELETE {{ GRAPH <{SHAPES_GRAPH}> {{ <{shape_uri}> sh:order ?old }} }}
            WHERE  {{ GRAPH <{SHAPES_GRAPH}> {{ <{shape_uri}> sh:order ?old }} }}
        """)

        ord_triple = _format_constraint_value(str(SH.order), order_val)
        await store._sparql_update(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            INSERT DATA {{ GRAPH <{SHAPES_GRAPH}> {{ <{shape_uri}> sh:order {ord_triple} }} }}
        """)

    invalidate_profile()
    return {"status": "ok"}

@app.post("/api/instances/exists")
async def check_instances_exist(data: dict):
    uris = data.get("uris", [])
    if not uris: return {"existing": []}
    safe = [u for u in uris if re.match(r'^https?://|^urn:', u) and '"' not in u]
    if not safe: return {"existing": []}
    values = " ".join(f"<{u}>" for u in safe)
    query = f"SELECT ?uri WHERE {{ VALUES ?uri {{ {values} }} {{ ?uri ?p ?o . }} UNION {{ ?s ?p ?uri . }} }}"
    rows = await store._sparql_query(query)
    return {"existing": list({r["uri"] for r in rows})}

@app.post("/api/preferences/public/blank-nodes")
async def set_public_blank_nodes(data: dict):
    show = data.get("show", False)
    prefs = load_preferences()
    prefs["public_display_blank_nodes"] = show
    save_preferences(prefs)
    state["public_display_blank_nodes"] = show
    return {"status": "ok"}

@app.get("/api/preferences/label-properties")
def get_label_preferences():
    prefs = load_preferences()
    return {"available": state.get("full_label_properties", []),
            "excluded": prefs.get("excluded_label_properties", [])}

@app.post("/api/preferences/label-properties/toggle")
async def toggle_label_property(data: dict):
    uri = data.get("uri")
    exclude = data.get("exclude", True)
    prefs = load_preferences()
    excluded = prefs.get("excluded_label_properties", [])
    if exclude and uri not in excluded: excluded.append(uri)
    elif not exclude and uri in excluded: excluded.remove(uri)
    prefs["excluded_label_properties"] = excluded
    save_preferences(prefs)
    update_label_hierarchy()
    return {"status": "ok"}

@app.post("/api/display-format")
async def set_display_format(format: str = Form(...)):
    state["display_format"] = format
    save_preferences({**load_preferences(), "display_format": format})
    return {"status": "ok"}

@app.get("/api/settings")
def get_settings():
    return {"site_title": state.get("site_title", "Semantta"), "base_iri": state.get("base_iri", "")}

@app.post("/api/settings")
async def update_settings(data: dict):
    changed = False
    if "site_title" in data:
        title = data["site_title"].strip()
        if title: state["site_title"] = title; changed = True
    if "base_iri" in data:
        iri = data["base_iri"].strip()
        state["base_iri"] = iri; changed = True
    if changed: save_settings({"site_title": state["site_title"], "base_iri": state["base_iri"]})
    return {"status": "ok"}

@app.post("/api/settings/apply-base-iri")
async def apply_base_iri():
    base_iri = state.get("base_iri", "").strip()
    if not base_iri: raise HTTPException(400, "Base IRI is not set.")
    if not base_iri.endswith('/'): base_iri += '/'
    mapping = {}
    for old_uri in list(state["created_instances"]):
        if old_uri.startswith("urn:uuid:"):
            new_uri = base_iri + old_uri[len("urn:uuid:"):]
            mapping[URIRef(old_uri)] = URIRef(new_uri)
            state["created_instances"].discard(old_uri)
            state["created_instances"].add(new_uri)
    if not mapping: return {"status": "ok", "updated": 0}
    rewrite_uris_in_graph(state["merged_metadata_graph"], mapping)
    rewrite_uris_in_graph(state["created_instances_graph"], mapping)
    nt_data = state["merged_metadata_graph"].serialize(format="nt")
    await store._sparql_update("CLEAR DEFAULT")
    await store.bulk_load_nt(nt_data)
    await refresh_instances_from_store()
    await rebuild_used_uris()
    return {"status": "ok", "updated": len(mapping)}

@app.get("/api/ontology/raw/{filename:path}")
async def get_raw_ontology(filename: str):
    filepath = os.path.join(ONTOLOGY_DIR, filename)
    if not os.path.exists(filepath): raise HTTPException(404, "Ontology file not found")
    return FileResponse(filepath)

@app.post("/api/admin/purge")
async def purge_all_data():
    try: await store._sparql_update("CLEAR ALL")
    except Exception:
        try:
            await store._sparql_update("CLEAR DEFAULT")
            await store._sparql_update("CLEAR GRAPH <urn:profile:shapes>")
            await store._sparql_update("CLEAR GRAPH <urn:profile:constraints>")
        except Exception: raise HTTPException(500, "Could not clear Fuseki store.")

    for directory in [ONTOLOGY_DIR, METADATA_DIR, CACHE_DIR]:
        if os.path.exists(directory):
            shutil.rmtree(directory)
            os.makedirs(directory, exist_ok=True)

    state["ontologies"].clear()
    state["combined_onto_graph"] = Graph()
    state["prefix_map"].clear()
    state["metadata_files"].clear()
    state["instances"].clear()
    state["merged_metadata_graph"] = Graph()
    state["created_instances"].clear()
    state["created_instances_graph"] = Graph()
    state["non_integrated_uris"].clear()
    state["metadata_only_sources"].clear()
    state["all_ontology_namespaces"].clear()
    invalidate_everything()
    if os.path.exists(PREFERENCES_FILE): os.remove(PREFERENCES_FILE)
    if os.path.exists(SETTINGS_FILE): os.remove(SETTINGS_FILE)
    state["display_format"] = "iri"
    state["site_title"] = "Semantta"
    state["base_iri"] = ""
    await rebuild_used_uris()
    add_default_prefixes()
    await seed_core_active_entities()
    return {"status": "ok", "message": "All data purged. System reset to factory mode."}

# ---- Plugins ----
@app.get("/api/plugins")
async def get_plugins():
    return {"plugins": list_plugins()}

@app.post("/api/plugins/upload")
async def upload_plugin(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(400, "Only .zip files are accepted.")
    tmp_dir = tempfile.mkdtemp()
    try:
        contents = await file.read()
        with zipfile.ZipFile(io.BytesIO(contents)) as zf:
            zf.extractall(tmp_dir)
        entries = os.listdir(tmp_dir)
        if len(entries) != 1 or not os.path.isdir(os.path.join(tmp_dir, entries[0])):
            raise HTTPException(400, "Invalid plugin structure: must contain a single folder with plugin.json")
        plugin_folder = entries[0]
        src = os.path.join(tmp_dir, plugin_folder)
        if not os.path.exists(os.path.join(src, "plugin.json")):
            raise HTTPException(400, "Missing plugin.json")
        dest = os.path.join(PLUGINS_DIR, plugin_folder)
        if os.path.exists(dest):
            raise HTTPException(400, f"Plugin '{plugin_folder}' already exists. Delete it first.")
        os.makedirs(PLUGINS_DIR, exist_ok=True)
        shutil.move(src, dest)
        config = load_plugins_config()
        config[plugin_folder] = {"enabled": False}
        save_plugins_config(config)
        return {"status": "ok", "plugin": plugin_folder}
    finally:
        if os.path.exists(tmp_dir): shutil.rmtree(tmp_dir)

@app.post("/api/plugins/toggle")
async def toggle_plugin(data: dict):
    name = data.get("name")
    enabled = data.get("enabled", True)
    config = load_plugins_config()
    if name not in config: raise HTTPException(404, "Plugin not found")
    config[name]["enabled"] = enabled
    save_plugins_config(config)
    return {"status": "ok", "message": f"Plugin {'enabled' if enabled else 'disabled'}. Restart server to apply changes."}

@app.delete("/api/plugins/{name:path}")
async def delete_plugin(name: str):
    config = load_plugins_config()
    if name not in config: raise HTTPException(404, "Plugin not found")
    plugin_path = os.path.join(PLUGINS_DIR, name)
    if os.path.exists(plugin_path): shutil.rmtree(plugin_path)
    del config[name]
    save_plugins_config(config)
    return {"status": "ok"}

# ---- Themes ----
@app.get("/api/themes")
async def get_themes():
    return {"themes": list_themes()}

@app.post("/api/themes/upload")
async def upload_theme(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(400, "Only .zip files are accepted.")
    tmp_dir = tempfile.mkdtemp()
    try:
        contents = await file.read()
        with zipfile.ZipFile(io.BytesIO(contents)) as zf:
            zf.extractall(tmp_dir)
        entries = os.listdir(tmp_dir)
        if len(entries) != 1 or not os.path.isdir(os.path.join(tmp_dir, entries[0])):
            raise HTTPException(400, "Invalid theme structure: must contain a single folder with theme.json")
        theme_folder = entries[0]
        src = os.path.join(tmp_dir, theme_folder)
        if not os.path.exists(os.path.join(src, "theme.json")):
            raise HTTPException(400, "Missing theme.json")
        dest = os.path.join(THEMES_DIR, theme_folder)
        if os.path.exists(dest): raise HTTPException(400, f"Theme '{theme_folder}' already exists.")
        os.makedirs(THEMES_DIR, exist_ok=True)
        shutil.move(src, dest)
        config = load_themes_config()
        config[theme_folder] = {"enabled": False}
        save_themes_config(config)
        return {"status": "ok", "theme": theme_folder}
    finally:
        if os.path.exists(tmp_dir): shutil.rmtree(tmp_dir)

@app.post("/api/themes/toggle")
async def toggle_theme(data: dict):
    name = data.get("name")
    enabled = data.get("enabled", True)
    if name == "default": raise HTTPException(400, "The default theme cannot be disabled.")
    config = load_themes_config()
    if name not in config: raise HTTPException(404, "Theme not found")
    config[name]["enabled"] = enabled
    save_themes_config(config)
    return {"status": "ok", "message": f"Theme {'enabled' if enabled else 'disabled'}. Restart frontend to apply changes."}

@app.delete("/api/themes/{name:path}")
async def delete_theme(name: str):
    if name == "default": raise HTTPException(400, "The default theme cannot be deleted.")
    config = load_themes_config()
    if name not in config: raise HTTPException(404, "Theme not found")
    theme_path = os.path.join(THEMES_DIR, name)
    if os.path.exists(theme_path): shutil.rmtree(theme_path)
    del config[name]
    save_themes_config(config)
    return {"status": "ok"}

@app.post("/api/themes/set-active")
async def set_active_theme_endpoint(data: dict):
    theme = data.get("theme", "default")
    if theme != "default" and not os.path.isdir(os.path.join(THEMES_DIR, theme)):
        raise HTTPException(404, "Theme not found")
    set_active_theme(theme)
    settings = load_settings()
    settings["active_theme"] = theme
    save_settings(settings)
    return {"status": "ok", "message": f"Active theme set to '{theme}'. Restart frontend to apply."}

@app.get("/api/progress")
async def get_progress():
    return progress