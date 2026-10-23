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
import stat
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import quote, unquote, urlsplit
from collections import defaultdict
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Callable, Dict, List, Optional, Set, cast, Any
from dotenv import load_dotenv
load_dotenv()

import owlrl
import pyshacl
from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, Response

from schemas import (
    Instance,
    InstanceListResponse,
    MetadataFileInfo,
    OntologyInfo,
    ProfileEntityItem,
    StateResponse,
    ToggleRequest,
)

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, split_uri


from config import FUSEKI_CONFIG, is_loopback_host
from fuseki_store import FusekiStore, SHAPES_GRAPH
from rdf_store import RDFStore
from streaming_rdf import (
    RelativeIRIWithoutBaseError,
    stream_rdf_to_ntriples,
)
from utils import (
    atomic_write_json,
    shape_uri_for_entity,
    property_shape_uri,
)
from logging_config import logger


from paths import (
    ACTIVE_THEME_FILE,
    CACHE_DIR,
    CREATED_INSTANCES_FILE,
    DATA_DIR,
    INDEX_CACHE_FILE,
    METADATA_DIR,
    ONTOLOGY_DIR,
    OWL_FILE,
    PLUGINS_CONFIG_FILE,
    PLUGINS_DIR,
    PREFERENCES_FILE,
    reasoned_cache_metadata_path,
    reasoned_cache_path,
    SETTINGS_FILE,
    STARS_FILE,
    THEMES_CONFIG_FILE,
    THEMES_DIR,
    ensure_data_dirs,
    plugin_dir,
    plugin_manifest_path,
    theme_dir,
    theme_manifest_path,
)

# ---------------------------------------------------------------------------
#  Constants & Configuration
# ---------------------------------------------------------------------------
RDF_FORMAT_MAP = {
    "rdf": "xml", "owl": "xml", "xml": "xml",
    "ttl": "turtle", "n3": "n3", "nt": "nt",
    "jsonld": "json-ld", "json": "json-ld",
    "trix": "trix", "trig": "trig",
}

METADATA_GRAPH_PREFIX = "urn:semantta:metadata:"

# User-installed plugins are importable as a namespace package from the
# user-data directory. This keeps plugin code outside the application tree.
if str(DATA_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_DIR))

INDEX_CACHE_VERSION = 1
REASONED_CACHE_VERSION = 1

SH = Namespace("http://www.w3.org/ns/shacl#")
GENERIC_RANGES = {str(OWL.Thing), str(RDFS.Resource)}
XSD_INTEGER = "http://www.w3.org/2001/XMLSchema#integer"
XSD_DECIMAL = "http://www.w3.org/2001/XMLSchema#decimal"
IGNORE_NAMESPACES = ["http://www.w3.org/2002/07/owl#"]
XSD_NAMESPACE = "http://www.w3.org/2001/XMLSchema#"

DEFAULT_ONTOLOGY_UPLOAD_LIMIT_MB = 200
DEFAULT_METADATA_UPLOAD_LIMIT_MB = 2048
DEFAULT_PLUGIN_UPLOAD_LIMIT_MB = 100
DEFAULT_THEME_UPLOAD_LIMIT_MB = 100

DEFAULT_ZIP_MEMBER_LIMIT = 10_000
DEFAULT_ZIP_TOTAL_UNCOMPRESSED_MB = 500
DEFAULT_ZIP_MEMBER_UNCOMPRESSED_MB = 100


def _env_size_limit(name: str, default_mb: int) -> int:
    raw = os.getenv(name)

    if raw is None:
        return default_mb * 1024 * 1024

    try:
        value_mb = int(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"{name} must be a positive integer."
        ) from exc

    if value_mb <= 0:
        raise RuntimeError(
            f"{name} must be greater than zero."
        )

    return value_mb * 1024 * 1024


MAX_ONTOLOGY_UPLOAD_BYTES = _env_size_limit(
    "SEMANTTA_MAX_ONTOLOGY_UPLOAD_MB",
    DEFAULT_ONTOLOGY_UPLOAD_LIMIT_MB,
)

MAX_METADATA_UPLOAD_BYTES = _env_size_limit(
    "SEMANTTA_MAX_METADATA_UPLOAD_MB",
    DEFAULT_METADATA_UPLOAD_LIMIT_MB,
)

MAX_PLUGIN_UPLOAD_BYTES = _env_size_limit(
    "SEMANTTA_MAX_PLUGIN_UPLOAD_MB",
    DEFAULT_PLUGIN_UPLOAD_LIMIT_MB,
)

MAX_THEME_UPLOAD_BYTES = _env_size_limit(
    "SEMANTTA_MAX_THEME_UPLOAD_MB",
    DEFAULT_THEME_UPLOAD_LIMIT_MB,
)

MAX_ZIP_MEMBER_COUNT = int(
    os.getenv(
        "SEMANTTA_MAX_ZIP_MEMBER_COUNT",
        DEFAULT_ZIP_MEMBER_LIMIT,
    )
)

MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES = (
    int(
        os.getenv(
            "SEMANTTA_MAX_ZIP_TOTAL_UNCOMPRESSED_MB",
            DEFAULT_ZIP_TOTAL_UNCOMPRESSED_MB,
        )
    )
    * 1024
    * 1024
)

MAX_ZIP_MEMBER_UNCOMPRESSED_BYTES = (
    int(
        os.getenv(
            "SEMANTTA_MAX_ZIP_MEMBER_UNCOMPRESSED_MB",
            DEFAULT_ZIP_MEMBER_UNCOMPRESSED_MB,
        )
    )
    * 1024
    * 1024
)


def _env_list(name: str, default: str) -> list[str]:
    values = [
        value.strip()
        for value in os.getenv(name, default).split(",")
        if value.strip()
    ]

    if not values or "*" in values:
        raise RuntimeError(
            f"{name} must contain explicit, non-wildcard values."
        )

    return values

CORS_ALLOWED_ORIGINS = _env_list(
    "SEMANTTA_CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
)

TRUSTED_HOSTS = _env_list(
    "SEMANTTA_ALLOWED_HOSTS",
    "127.0.0.1,localhost",
)

# HTTP methods that can change application state.
UNSAFE_HTTP_METHODS = frozenset({
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
})

# Must match APP_SCHEME and APP_HOST in frontend/electron/main.cjs.
ELECTRON_APP_ORIGIN = "semantta://bundle"

# Browser origins trusted to submit state-changing requests.
# The Electron application origin is trusted separately because it
# is not part of the normal HTTP frontend origin configuration.
TRUSTED_REQUEST_ORIGINS = frozenset(
    [*CORS_ALLOWED_ORIGINS, ELECTRON_APP_ORIGIN]
)

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
#  Global State
# ---------------------------------------------------------------------------
state = {
    "ontologies": [],
    "combined_onto_graph": Graph(),
    "prefix_map": {},
    "display_prefix_map": {},
    "instances": [],
    "instance_count_cache": {},
    "display_format": "iri",
    "metadata_files": [],
    "metadata_graph_stats": {},
    "metadata_only_sources": {},
    "non_integrated_uris": set(),
    "created_instances": set(),
    "created_instances_graph": Graph(),
    "all_ontology_namespaces": set(),
    "profile_version": 0,
    "full_label_properties": [],
    "starred_instance_uris": set(),
    "applied_base_iri": "",
}

_subclass_pairs: Set[tuple] = set()
_property_domains: Dict[str, List[str]] = defaultdict(list)
_property_ranges: Dict[str, List[str]] = defaultdict(list)
_property_cardinalities: Dict[tuple, tuple] = {}
_disjoint_pairs: Set[tuple] = set()

_used_uris_set: Set[str] = set()

progress = {"phase": "", "percent": 0}
validation_ontology_graph = Graph()
LABEL_PROPERTIES: List[str] = []

# ---------------------------------------------------------------------------
#  General Helpers
# ---------------------------------------------------------------------------
def is_valid_uri(uri: str) -> bool:
    if not isinstance(uri, str) or not uri:
        return False

    if not uri.startswith(
        ("http://", "https://", "urn:")
    ):
        return False

    # SPARQL IRIREF cannot contain these characters.
    if any(
        char in uri
        for char in (
            "<",
            ">",
            '"',
            "{",
            "}",
            "|",
            "\\",
            "^",
            "`",
        )
    ):
        return False

    if any(
        ord(char) < 0x20
        for char in uri
    ):
        return False

    return True


def _sparql_iri(
    uri: str,
    label: str = "URI",
) -> str:
    if not is_valid_uri(uri):
        raise HTTPException(
            400,
            f"Invalid {label}: {uri}",
        )

    return URIRef(uri).n3()

def _is_iri_value(value: object) -> bool:
    return isinstance(value, str) and value.startswith(
        ("http://", "https://", "urn:")
    )

def _metadata_literal(
    value: object,
    prop_uri: str,
    datatype_uri: Optional[str],
) -> Literal:
    """Construct a validated RDF literal using the declared datatype."""
    if datatype_uri is None:
        return Literal(str(value))

    if (
        datatype_uri == "http://www.w3.org/2001/XMLSchema#boolean"
        and isinstance(value, bool)
    ):
        lexical_value = "true" if value else "false"
    else:
        lexical_value = str(value)

    literal = Literal(
        lexical_value,
        datatype=URIRef(datatype_uri),
        normalize=False,
    )

    if literal.ill_typed:
        raise HTTPException(
            400,
            f"Invalid value for {prop_uri}: "
            f"expected a valid value of datatype {datatype_uri}.",
        )

    return literal

def _require_safe_path_component(
    name: str | None,
    label: str = "name",
) -> str:
    """Validate and return a single safe filesystem path component."""
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(
            400,
            f"{label} must not be empty",
        )

    value = name.strip()

    # Use a standard-library basename operation and reject, rather than
    # silently strip, any input that is not already a single component.
    basename = os.path.basename(value)
    windows_basename = PureWindowsPath(value).name

    if (
        not basename
        or basename != value
        or windows_basename != value
        or value in {".", ".."}
        or ".." in value
        or re.search(r'[<>:"/\\|?*\x00-\x1f]', value)
    ):
        raise HTTPException(
            400,
            f"{label} contains illegal characters",
        )

    return basename

def _path_within_directory(
    base_dir: Path,
    name: str,
) -> Path:
    """Resolve one filename and ensure it remains within a managed directory."""
    basename = os.path.basename(name)

    if (
        not basename
        or basename != name
        or basename in {".", ".."}
        or ".." in basename
        or PureWindowsPath(basename).name != basename
    ):
        raise HTTPException(
            400,
            "Invalid filename.",
        )

    base = os.path.realpath(os.fspath(base_dir))
    candidate = os.path.realpath(
        os.path.join(base, basename)
    )

    # Keep the explicit prefix guard alongside commonpath and realpath.
    # The trailing separator prevents sibling paths such as /data-other
    # from being treated as children of /data.
    base_prefix = os.path.join(base, "")

    try:
        is_within_base = (
            os.path.commonpath((base, candidate)) == base
        )
    except ValueError:
        is_within_base = False

    if (
        not candidate.startswith(base_prefix)
        or not is_within_base
    ):
        raise HTTPException(
            400,
            "Requested path is outside the managed data directory.",
        )

    return Path(candidate)

async def _read_upload_with_limit(
    file: UploadFile,
    max_bytes: int,
) -> bytes:
    chunks = []
    total = 0

    while True:
        chunk = await file.read(1024 * 1024)

        if not chunk:
            break

        total += len(chunk)

        if total > max_bytes:
            max_mb = max_bytes // (1024 * 1024)

            raise HTTPException(
                413,
                f"Uploaded file exceeds the {max_mb} MB limit.",
            )

        chunks.append(chunk)

    return b"".join(chunks)

def _safe_extract_zip(
    zf: zipfile.ZipFile,
    target_dir: Path,
) -> None:
    """
    Extract ZIP members while preventing path traversal and symlink entries.

    Archive members must remain strictly inside target_dir.
    """
    infos = zf.infolist()

    if len(infos) > MAX_ZIP_MEMBER_COUNT:
        raise HTTPException(
            400,
            (
                "Archive contains too many files "
                f"(maximum: {MAX_ZIP_MEMBER_COUNT})."
            ),
        )

    total_uncompressed = 0

    for info in infos:
        if info.file_size > MAX_ZIP_MEMBER_UNCOMPRESSED_BYTES:
            raise HTTPException(
                400,
                (
                    f"Archive member '{info.filename}' exceeds the "
                    "maximum uncompressed file size."
                ),
            )

        total_uncompressed += info.file_size

        if (
            total_uncompressed
            > MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES
        ):
            raise HTTPException(
                400,
                "Archive exceeds the maximum total uncompressed size.",
            )
        
    target_dir = target_dir.resolve()
    seen_paths: set[Path] = set()

    for info in infos:
        raw_name = info.filename

        if not raw_name or "\x00" in raw_name:
            raise HTTPException(
                400,
                "Archive contains an invalid member name.",
            )

        normalized_name = raw_name.replace("\\", "/")

        posix_name = PurePosixPath(normalized_name)
        windows_name = PureWindowsPath(normalized_name)

        if (
            posix_name.is_absolute()
            or windows_name.is_absolute()
            or windows_name.drive
            or any(
                part == ".."
                for part in posix_name.parts
            )
        ):
            raise HTTPException(
                400,
                "Archive contains an unsafe path.",
            )

        relative_path = Path(*posix_name.parts)
        destination = (
            target_dir / relative_path
        ).resolve()
        destination_text = str(destination)
        target_prefix = os.path.join(str(target_dir), "")

        if not destination_text.startswith(target_prefix):
            raise HTTPException(
                400,
                "Archive contains a path outside the extraction directory.",
            )
        
        try:
            destination.relative_to(target_dir)
        except ValueError as exc:
            raise HTTPException(
                400,
                "Archive contains a path outside the extraction directory.",
            ) from exc

        if destination in seen_paths:
            raise HTTPException(
                400,
                f"Archive contains duplicate member: {normalized_name}",
            )

        seen_paths.add(destination)

        mode = (
            info.external_attr >> 16
        ) & 0xFFFF

        if stat.S_ISLNK(mode):
            raise HTTPException(
                400,
                "Archive contains a symbolic link.",
            )

        if normalized_name.endswith("/"):
            destination.mkdir(
                parents=True,
                exist_ok=True,
            )
            continue

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with (
            zf.open(info, "r") as source,
            destination.open("wb") as target,
        ):
            shutil.copyfileobj(
                source,
                target,
            )

async def _validate_metadata_profile_membership(
    class_uris: list[str],
    properties: dict,
):
    if not isinstance(properties, dict):
        raise HTTPException(
            400,
            "properties must be an object",
        )

    for cls in class_uris:
        _sparql_iri(cls, "class URI")

    for prop in properties:
        _sparql_iri(prop, "property URI")

    active_classes = set(
        await shacl.get_active_classes()
    )

    for cls in class_uris:
        if cls not in active_classes:
            raise HTTPException(
                400,
                f"Class is not active in the Application Profile: {cls}",
            )

    active_properties = set(
        await shacl.get_active_properties()
    )

    for prop in properties:
        if prop not in active_properties:
            raise HTTPException(
                400,
                f"Property is not active in the Application Profile: {prop}",
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

def _generated_display_prefix(
    namespace: str,
    used_prefixes: set[str],
) -> str:
    """Generate a stable, valid display prefix for an unmapped namespace."""
    base = namespace.rstrip("/#:")
    segments = re.split(r"[/#:]", base)

    candidate = next(
        (
            segment
            for segment in reversed(segments)
            if segment and not segment.isdigit()
        ),
        "ns",
    )

    candidate = re.sub(r"[^A-Za-z0-9_-]+", "_", candidate)
    candidate = candidate.strip("_-") or "ns"

    if not re.match(r"^[A-Za-z_]", candidate):
        candidate = f"ns_{candidate}"

    candidate = candidate[:32]

    if candidate in used_prefixes:
        suffix = hashlib.sha256(
            namespace.encode("utf-8")
        ).hexdigest()[:6]
        candidate = f"{candidate[:25]}_{suffix}"

        counter = 2
        while candidate in used_prefixes:
            candidate = f"{candidate[:28]}_{counter}"
            counter += 1

    return candidate


def build_display_prefix_map() -> dict[str, str]:
    """
    Extend declared namespace bindings with generated prefixes for ontology
    namespaces that RDFLib could not match to an existing binding.

    This mapping is for URI display only. It does not modify the internal
    namespace map used by RDF and SHACL operations.
    """
    display_map = {
        str(namespace): str(prefix)
        for namespace, prefix in state["prefix_map"].items()
    }
    used_prefixes = set(display_map.values())
    missing_namespaces: set[str] = set()

    for ontology in state["ontologies"]:
        graph = ontology.get("graph")

        if not isinstance(graph, Graph):
            continue

        for subject, predicate, obj in graph:
            for term in (subject, predicate, obj):
                if not isinstance(term, URIRef):
                    continue

                uri = str(term)

                # These are Semantta-generated identifiers, not ontology
                # vocabulary terms that need display prefixes.
                if uri.startswith(("urn:bnid:", "urn:shape:")):
                    continue

                try:
                    namespace, local_name = split_uri(uri)
                except ValueError:
                    continue

                namespace = str(namespace)

                if namespace and local_name and namespace not in display_map:
                    missing_namespaces.add(namespace)

    # Stable ordering prevents upload order from affecting generated prefixes.
    for namespace in sorted(missing_namespaces):
        if namespace in display_map:
            continue

        prefix = _generated_display_prefix(
            namespace,
            used_prefixes,
        )

        display_map[namespace] = prefix
        used_prefixes.add(prefix)

    return display_map

def refresh_display_prefix_map() -> None:
    """Refresh display-only prefixes after ontology state changes."""
    state["display_prefix_map"] = build_display_prefix_map()

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

async def _get_stored_labels(uris: List[str]) -> Dict[str, str]:
    """Retrieve stored labels for a batch of RDF resources."""
    unique_uris = list(dict.fromkeys(uri for uri in uris if uri))
    labels: Dict[str, str] = {}

    for offset in range(0, len(unique_uris), 250):
        result = await store.get_instance_labels(
            unique_uris[offset:offset + 250]
        )
        if isinstance(result, dict):
            labels.update(result)

    return labels

async def _resolve_display_labels(
    uris: List[str],
) -> Dict[str, str]:
    """Prefer stored labels, then ontology labels, then URI local names."""
    unique_uris = list(dict.fromkeys(uri for uri in uris if uri))
    labels = await _get_stored_labels(unique_uris)

    for uri in unique_uris:
        if not labels.get(uri):
            labels[uri] = get_label(uri)

    return labels

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
    if isinstance(val, str) and val.startswith(
        ("http://", "https://", "urn:")
    ):
        return URIRef(val).n3()
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

def rewrite_uris_in_graph(g: Graph, mapping: dict):
    for s, p, o in list(g.triples((None, None, None))):
        new_s = mapping.get(s, s)
        new_p = mapping.get(p, p) if isinstance(p, URIRef) else p
        new_o = mapping.get(o, o) if isinstance(o, URIRef) else o

        if new_s != s or new_p != p or new_o != o:
            g.remove((s, p, o))
            g.add((new_s, new_p, new_o))

def _build_uri_rewrite_update(
    mapping: dict[str, str],
    graph_uris: list[str],
) -> str:
    mapping_values = " ".join(
        f"({_sparql_iri(old, 'old instance URI')} "
        f"{_sparql_iri(new, 'new instance URI')})"
        for old, new in sorted(mapping.items())
    )

    graph_values = " ".join(
        _sparql_iri(uri, "metadata graph URI")
        for uri in sorted(set(graph_uris))
    )

    positions = [
        ("?old ?p ?o", "?new ?p ?o"),
        ("?s ?old ?o", "?s ?new ?o"),
        ("?s ?p ?old", "?s ?p ?new"),
    ]

    operations = []

    if graph_values:
        for pattern, replacement in positions:
            operations.append(f"""
                DELETE {{
                    GRAPH ?g {{ {pattern} }}
                }}
                INSERT {{
                    GRAPH ?g {{ {replacement} }}
                }}
                WHERE {{
                    VALUES (?old ?new) {{ {mapping_values} }}
                    VALUES ?g {{ {graph_values} }}
                    GRAPH ?g {{ {pattern} . }}
                }}
            """)

    for pattern, replacement in positions:
        operations.append(f"""
            DELETE {{ {pattern} }}
            INSERT {{ {replacement} }}
            WHERE {{
                VALUES (?old ?new) {{ {mapping_values} }}
                {pattern} .
            }}
        """)

    return ";\n".join(operations)

def save_created_instances() -> None:
    atomic_write_json(
        CREATED_INSTANCES_FILE,
        sorted(
            state["created_instances"]
        ),
    )

def _build_base_iri_mapping(
    created_uris: set[str],
    applied_base_iri: str,
    base_iri: str,
) -> dict[str, str]:
    if applied_base_iri and not applied_base_iri.endswith("/"):
        applied_base_iri += "/"

    uuid_suffix = re.compile(
        r"(?:^|/)"
        r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{12})$"
    )

    mapping = {}

    for old_uri in sorted(created_uris):
        if old_uri.startswith("urn:uuid:"):
            suffix = old_uri[len("urn:uuid:"):]

        elif applied_base_iri and old_uri.startswith(applied_base_iri):
            suffix = old_uri[len(applied_base_iri):]

        else:
            # Recover previously generated UUID-based URIs if an
            # older version saved the new setting before applying it.
            match = uuid_suffix.search(old_uri)
            if not match:
                continue
            suffix = match.group(1)

        new_uri = base_iri + suffix

        if new_uri != old_uri:
            mapping[old_uri] = new_uri

    return mapping

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

def _ontology_literal(
    graph: Graph,
    subject,
    predicate,
) -> str:
    """Return a deterministic literal value for an ontology annotation."""
    values = [
        value
        for value in graph.objects(subject, predicate)
        if isinstance(value, Literal)
    ]

    if not values:
        return ""

    values.sort(
        key=lambda value: (
            value.language is not None,
            (value.language or "").casefold(),
            str(value).casefold(),
            str(value),
            str(value.datatype or ""),
        )
    )

    return str(values[0])

def extract_ontology_metadata(g: Graph) -> dict:
    """Extract metadata for the canonical ontology IRI, not its version IRI."""
    meta = {
        "title": "",
        "version": "",
        "iri": "",
    }

    ontology_nodes = {
        subject
        for subject in g.subjects(RDF.type, OWL.Ontology)
        if isinstance(subject, URIRef)
    }

    # A version IRI is not the canonical ontology IRI of the ontology
    # that declares it.
    version_iri_targets = {
        version_iri
        for version_iri in g.objects(None, OWL.versionIRI)
        if isinstance(version_iri, URIRef)
    }

    candidates = ontology_nodes - version_iri_targets

    # Prefer an ontology that explicitly declares its version IRI.
    versioned_candidates = {
        subject
        for subject in candidates
        if any(
            isinstance(value, URIRef)
            for value in g.objects(subject, OWL.versionIRI)
        )
    }

    if versioned_candidates:
        candidates = versioned_candidates
    elif not candidates:
        candidates = ontology_nodes

    if candidates:
        # Prefer candidates with descriptive metadata. URI is the final
        # tie-breaker so selection does not depend on RDF graph iteration.
        def candidate_score(subject):
            rdfs_title = _ontology_rdfs_label(g, subject)
            dc_title = _ontology_literal(g, subject, DC_TITLE)
            dcterms_title = _ontology_literal(g, subject, DCTERMS_TITLE)
            title = rdfs_title or dc_title or dcterms_title
            version = _ontology_literal(
                g, subject, OWL.versionInfo
            )

            label_predicates = _ontology_rdfs_label_predicates(g)
            label_count = sum(
                1
                for predicate in label_predicates
                for _ in g.objects(subject, predicate)
            )
            version_count = sum(
                1 for _ in g.objects(subject, OWL.versionInfo)
            )

            return (
                bool(rdfs_title),
                bool(title),
                bool(version),
                label_count,
                version_count,
                str(subject),
            )

        onto = max(candidates, key=candidate_score)

        meta["iri"] = str(onto)
        meta["title"] = _preferred_ontology_title(g, onto)
        meta["version"] = _ontology_literal(
            g, onto, OWL.versionInfo
        )

        return meta

    return meta

DC_TITLE = URIRef(
    "http://purl.org/dc/elements/1.1/title"
)

DCTERMS_TITLE = URIRef(
    "http://purl.org/dc/terms/title"
)


def _ontology_rdfs_label_predicates(g: Graph) -> set[URIRef]:
    """Return rdfs:label and all declared transitive subproperties."""
    predicates: set[URIRef] = {RDFS.label}

    changed = True
    while changed:
        changed = False

        for subproperty, superproperty in g.subject_objects(
            RDFS.subPropertyOf
        ):
            if (
                isinstance(subproperty, URIRef)
                and superproperty in predicates
                and subproperty not in predicates
            ):
                predicates.add(subproperty)
                changed = True

    return predicates


def _ontology_rdfs_label(g: Graph, subject) -> str:
    """Prefer rdfs:label, then a declared subproperty of rdfs:label."""
    direct_label = _ontology_literal(g, subject, RDFS.label)
    if direct_label:
        return direct_label

    subproperties = sorted(
        _ontology_rdfs_label_predicates(g) - {RDFS.label},
        key=str,
    )

    for predicate in subproperties:
        label = _ontology_literal(g, subject, predicate)
        if label:
            return label

    return ""


def _preferred_ontology_title(g: Graph, subject) -> str:
    """Prefer RDFS labels, then DC Elements title, then DCMI Terms title."""
    label = _ontology_rdfs_label(g, subject)
    if label:
        return label

    dc_title = _ontology_literal(g, subject, DC_TITLE)
    if dc_title:
        return dc_title

    return _ontology_literal(g, subject, DCTERMS_TITLE)

def _load_ontology_metadata(
    filename: str,
    source_graph: Graph,
) -> dict:
    """Load saved ontology metadata or derive it from the original graph."""
    source_path = os.path.join(ONTOLOGY_DIR, filename)
    metadata_path = reasoned_cache_metadata_path(filename)
    source_signature = _file_signature(source_path)

    cache_metadata = {}

    try:
        with open(metadata_path, "r", encoding="utf-8") as file:
            cache_metadata = json.load(file)
    except (OSError, json.JSONDecodeError):
        cache_metadata = {}

    saved_metadata = cache_metadata.get("ontology_metadata")

    if (
        cache_metadata.get("source_signature") == source_signature
        and isinstance(saved_metadata, dict)
        and all(
            isinstance(saved_metadata.get(key), str)
            for key in ("title", "version", "iri")
        )
    ):
        return {
            "title": saved_metadata["title"],
            "version": saved_metadata["version"],
            "iri": saved_metadata["iri"],
        }

    metadata = extract_ontology_metadata(source_graph)

    cache_metadata = {
        "cache_version": REASONED_CACHE_VERSION,
        "source_signature": source_signature,
        "owl_vocabulary_signature": _file_signature(OWL_FILE),
        "ontology_metadata": metadata,
    }

    atomic_write_json(metadata_path, cache_metadata)

    return metadata

def get_property_cardinality(class_uri: str, prop_uri: str) -> dict:
    minc, maxc = _property_cardinalities.get((class_uri, prop_uri), (None, None))
    return {"minCardinality": minc, "maxCardinality": maxc}

def _is_datatype_uri(
    uri: str,
    graph: Optional[Graph] = None,
    active_datatypes: Optional[set[str]] = None,
) -> bool:
    """Return whether Semantta recognizes a URI as a datatype."""
    if uri in SYSTEM_DATATYPES or uri.startswith(XSD_NAMESPACE):
        return True

    if active_datatypes and uri in active_datatypes:
        return True

    ontology_graph = (
        graph
        if graph is not None
        else state["combined_onto_graph"]
    )

    if (
        URIRef(uri),
        RDF.type,
        RDFS.Datatype,
    ) in ontology_graph:
        return True

    # Use processed ontology entities as a fallback when the combined
    # graph does not contain the original datatype declaration.
    return any(
        entity.get("uri") == uri
        and entity.get("type") == "datatype"
        for ontology in state.get("ontologies", [])
        for entity in ontology.get("entities", [])
    )

def _get_property_type(
    prop_uri: str,
    active_datatypes: Optional[set[str]] = None,
) -> str:
    """Classify a property according to its declared type and ranges."""
    property_uri = URIRef(prop_uri)
    ontology_graph = state["combined_onto_graph"]

    # Explicit OWL property declarations take precedence.
    if (
        property_uri,
        RDF.type,
        OWL.ObjectProperty,
    ) in ontology_graph:
        return "object"

    if (
        property_uri,
        RDF.type,
        OWL.DatatypeProperty,
    ) in ontology_graph:
        return "datatype"

    # Otherwise, classify the property using all known datatype ranges.
    ranges = [
        str(value)
        for value in ontology_graph.objects(
            property_uri,
            RDFS.range,
        )
        if isinstance(value, URIRef)
    ]

    if any(
        _is_datatype_uri(
            range_uri,
            ontology_graph,
            active_datatypes,
        )
        for range_uri in ranges
    ):
        return "datatype"

    return "object"

def _normalize_namespace_delimiters(uri: str) -> str:
    """Remove trailing namespace delimiters for comparison only."""
    return re.sub(r"[/#]+$", "", uri)

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
                
    ontology_iri = extract_ontology_metadata(g).get("iri", "")

    if ontology_iri:
        normalized_ontology_iri = _normalize_namespace_delimiters(
            ontology_iri
        )

        used_ns = {
            namespace
            for namespace in used_ns
            if _normalize_namespace_delimiters(namespace)
            != normalized_ontology_iri
        }

    return sorted(used_ns)


def _file_signature(path: str | os.PathLike) -> dict:
    """
    Return a lightweight signature for a persistent source file.

    Modification time and file size are used deliberately instead of hashing
    the whole file, because ontology files may be very large.
    """
    stat = os.stat(path)
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _ontology_source_signature() -> dict:
    """
    Return the signature of all ontology sources that contribute to the
    precomputed indexes.

    The built-in OWL vocabulary is included because it participates in
    reasoning and therefore can affect the resulting ontology graph.
    """
    ontologies = {}

    if os.path.isdir(ONTOLOGY_DIR):
        for filename in sorted(os.listdir(ONTOLOGY_DIR)):
            if not filename.endswith(
                (".rdf", ".owl", ".xml", ".ttl", ".nt", ".jsonld",
                 ".json", ".trig", ".trix")
            ):
                continue

            path = os.path.join(ONTOLOGY_DIR, filename)

            if os.path.isfile(path):
                ontologies[filename] = _file_signature(path)

    return {
        "owl_vocabulary": _file_signature(OWL_FILE),
        "ontologies": ontologies,
    }

# ---------------------------------------------------------------------------
#  Index Building & Caching
# ---------------------------------------------------------------------------
def rebuild_precomputed():
    # Single scan for core indexes (subclass, domains, ranges, cardinalities, disjointness)
    # NOTE: update_label_hierarchy() and rebuild_validation_ontology() scan the graph again.
    if load_indexes():
        rebuild_validation_ontology()
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
        "cache_version": INDEX_CACHE_VERSION,
        "source_signature": _ontology_source_signature(),
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

        # Derived indexes are valid only when their format and all of their
        # authoritative ontology sources are unchanged.
        if data.get("cache_version") != INDEX_CACHE_VERSION:
            return False

        if data.get("source_signature") != _ontology_source_signature():
            return False

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

async def get_cached_instance_count(
    include_blank_nodes: bool = False,
) -> int:
    cached_counts = state.get(
        "instance_count_cache"
    )

    if not isinstance(cached_counts, dict):
        cached_counts = {}
        state["instance_count_cache"] = (
            cached_counts
        )

    if include_blank_nodes in cached_counts:
        return cached_counts[include_blank_nodes]

    count = await store.count_instances(
        include_blank_nodes=include_blank_nodes,
    )

    cached_counts[include_blank_nodes] = count

    return count


def invalidate_instance_count() -> None:
    state["instance_count_cache"] = {}

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
        rows = await store.query(f"""
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
        rows = await store.query("""
            SELECT DISTINCT ?uri WHERE {
                { ?uri a ?type . } UNION { ?s ?uri ?o . } UNION { ?s a ?uri . }
                FILTER(ISIRI(?uri) && !STRSTARTS(STR(?uri), "urn:bnid:"))
            }""")
        _used_uris_set = {r["uri"] for r in rows}
    except Exception:
        _used_uris_set = set()

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
        rows = await store.query(query)
        return [{"uri": r["instance"], "label": get_label(r["instance"])} for r in rows]
    except Exception:
        return []

async def check_disjoint_classes(class_uris: List[str]):
    all_disjoint = set(_disjoint_pairs)
    for cls in class_uris:
        shape_uri = shape_uri_for_entity(cls, "class", state["prefix_map"])
        rows = await store.query(f"""
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
#  Metadata Helpers
# ---------------------------------------------------------------------------

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

def metadata_graph_uri(filename: str) -> str:
    return (
        METADATA_GRAPH_PREFIX
        + quote(
            filename,
            safe="",
        )
    )

def metadata_filename_from_graph(
    graph_uri: str,
) -> str:
    if not graph_uri.startswith(
        METADATA_GRAPH_PREFIX
    ):
        raise ValueError(
            f"Not a Semantta metadata graph URI: {graph_uri}"
        )

    return unquote(
        graph_uri[len(METADATA_GRAPH_PREFIX):]
    )

def _metadata_graph_values(graph_uris: List[str]) -> str:
    """Return a validated, deterministic SPARQL VALUES list."""
    unique_graph_uris = sorted(set(graph_uris))
    if not unique_graph_uris:
        raise ValueError("At least one metadata graph URI is required.")

    return " ".join(
        _sparql_iri(uri, "metadata graph URI")
        for uri in unique_graph_uris
    )


def _metadata_vocabulary_query(
    graph_uris: List[str],
    known_individual_uris: Optional[List[str]] = None,
    include_graph: bool = False,
) -> str:
    """Extract vocabulary references by URI and semantic role."""
    graph_values = _metadata_graph_values(graph_uris)

    select_variables = (
        "?graph ?term ?role"
        if include_graph
        else "?term ?role"
    )

    declaration_types = (
        OWL.Class,
        RDFS.Class,
        OWL.ObjectProperty,
        OWL.DatatypeProperty,
        OWL.AnnotationProperty,
        RDF.Property,
        RDFS.Datatype,
        OWL.NamedIndividual,
        OWL.Ontology,
        OWL.FunctionalProperty,
        OWL.InverseFunctionalProperty,
        OWL.TransitiveProperty,
        OWL.SymmetricProperty,
        OWL.AsymmetricProperty,
        OWL.ReflexiveProperty,
        OWL.IrreflexiveProperty,
        OWL.Restriction,
        OWL.Axiom,
        OWL.AllDifferent,
        OWL.AllDisjointClasses,
        OWL.AllDisjointProperties,
        OWL.NegativePropertyAssertion,
        RDF.List,
    )

    excluded_types = ", ".join(
        _sparql_iri(str(uri), "RDF type")
        for uri in declaration_types
    )

    property_types = (
        OWL.ObjectProperty,
        OWL.DatatypeProperty,
        OWL.AnnotationProperty,
        RDF.Property,
        OWL.FunctionalProperty,
        OWL.InverseFunctionalProperty,
        OWL.TransitiveProperty,
        OWL.SymmetricProperty,
        OWL.AsymmetricProperty,
        OWL.ReflexiveProperty,
        OWL.IrreflexiveProperty,
    )

    property_type_values = " ".join(
        _sparql_iri(str(uri), "property type")
        for uri in property_types
    )

    individual_branch = ""

    known_individual_uris = known_individual_uris or []
    if known_individual_uris:
        individual_values = " ".join(
            _sparql_iri(uri, "individual URI")
            for uri in sorted(set(known_individual_uris))
        )

        individual_branch = f"""
            UNION
            {{
                VALUES ?knownIndividual {{ {individual_values} }}
                {{
                    ?knownIndividual ?p ?o .
                }}
                UNION
                {{
                    ?s ?p ?knownIndividual .
                }}
                BIND(?knownIndividual AS ?term)
                BIND("individual" AS ?role)
            }}
        """

    return f"""
        PREFIX rdf: <{RDF}>
        PREFIX rdfs: <{RDFS}>
        PREFIX owl: <{OWL}>

        SELECT DISTINCT {select_variables} WHERE {{
            VALUES ?graph {{ {graph_values} }}

            GRAPH ?graph {{
                {{
                    ?subject rdf:type ?term .
                    FILTER(?term NOT IN ({excluded_types}))
                    BIND("class" AS ?role)
                }}
                UNION
                {{
                    ?subject ?term ?value .
                    FILTER(?term != rdf:type)
                    FILTER NOT EXISTS {{
                        ?subject rdf:type ?subjectType .
                        VALUES ?subjectType {{
                            owl:Class
                            rdfs:Class
                            owl:ObjectProperty
                            owl:DatatypeProperty
                            owl:AnnotationProperty
                            rdf:Property
                            rdfs:Datatype
                            owl:Ontology
                        }}
                    }}
                    BIND("property" AS ?role)
                }}
                UNION
                {{
                    ?subject ?predicate ?literal .
                    FILTER(isLiteral(?literal))
                    BIND(DATATYPE(?literal) AS ?term)
                    BIND("datatype" AS ?role)
                }}
                UNION
                {{
                    ?term rdf:type owl:Class .
                    BIND("class" AS ?role)
                }}
                UNION
                {{
                    ?term rdf:type rdfs:Class .
                    BIND("class" AS ?role)
                }}
                UNION
                {{
                    ?term rdf:type ?propertyType .
                    VALUES ?propertyType {{
                        {property_type_values}
                    }}
                    BIND("property" AS ?role)
                }}
                UNION
                {{
                    ?term rdf:type rdfs:Datatype .
                    BIND("datatype" AS ?role)
                }}
                UNION
                {{
                    ?term rdf:type owl:NamedIndividual .
                    BIND("individual" AS ?role)
                }}
                {individual_branch}
            }}

            FILTER(
                isIRI(?term)
                && !STRSTARTS(STR(?term), "urn:bnid:")
            )
        }}
    """

async def get_cached_metadata_graph_stats(
    graph_uri: str,
) -> Dict[str, Any]:
    cached = state["metadata_graph_stats"].get(
        graph_uri
    )

    if cached is not None:
        return cached

    stats = await store.get_graph_stats(
        graph_uri
    )

    state["metadata_graph_stats"][
        graph_uri
    ] = stats

    return stats


def invalidate_metadata_graph_stats(
    graph_uri: str,
) -> None:
    state["metadata_graph_stats"].pop(
        graph_uri,
        None,
    )

def clear_metadata_graph_stats() -> None:
    state["metadata_graph_stats"].clear()

def _summarize_metadata_integration_status(
    required_entities: Dict[str, List[str]],
    active_entities: Dict[str, Set[str]],
) -> Dict[str, Any]:
    """Compare a file's vocabulary with the active profile entities."""
    roles = (
        "class",
        "property",
        "datatype",
        "individual",
    )

    required_count = 0
    missing_count = 0

    for role in roles:
        required = set(
            required_entities.get(role, [])
        )
        active = active_entities.get(role, set())

        required_count += len(required)
        missing_count += len(required - active)

    if required_count == 0:
        status = "no_vocabulary"
    elif missing_count == 0:
        status = "integrated"
    else:
        status = "not_integrated"

    return {
        "status": status,
        "required_count": required_count,
        "missing_count": missing_count,
    }

async def rebuild_default_data_graph() -> None:
    """
    Rebuild the Fuseki default graph from all metadata named graphs
    plus application-created instances.

    Metadata named graphs remain the authoritative source.
    """
    invalidate_instance_count()
    await store.update("CLEAR DEFAULT")

    for metadata_file in state["metadata_files"]:
        graph_uri = metadata_file["graph_uri"]

        if not await store.graph_exists(graph_uri):
            logger.warning(
                "Skipping metadata graph that does not exist: %s",
                graph_uri,
            )
            continue

        await store.update(
            f"ADD GRAPH <{graph_uri}> TO DEFAULT"
        )

    created_nt = (
        state["created_instances_graph"]
        .serialize(format="nt")
    )

    if created_nt.strip():
        await store.bulk_load_nt(
            created_nt
        )

def _metadata_staging_graph_uri(kind: str) -> str:
    return (
        "urn:semantta:staging:"
        f"metadata-{kind}:"
        f"{uuid.uuid4().hex}"
    )

def _metadata_files_after_upload(
    filename: str,
    graph_uri: str,
) -> list[dict]:
    new_entry = {
        "filename": filename,
        "graph_uri": graph_uri,
    }

    result = []
    replaced = False

    for existing in state["metadata_files"]:
        if existing["filename"] == filename:
            result.append(new_entry)
            replaced = True
        else:
            result.append(existing)

    if not replaced:
        result.append(new_entry)

    return result

async def _stage_metadata_default_graph(
    candidate_files: list[dict],
    filename: str,
    staged_graph_uri: str,
    work_dir: Path,
) -> str | None:
    staging_default_uri = (
        _metadata_staging_graph_uri("default")
    )

    has_content = False

    created_nt = (
        state["created_instances_graph"]
        .serialize(format="nt")
    )

    if created_nt.strip():
        created_path = (
            work_dir / "created-instances.nt"
        )

        created_path.write_text(
            created_nt,
            encoding="utf-8",
        )

        await store.bulk_load_nt_file(
            created_path,
            staging_default_uri,
        )

        has_content = True

    add_operations = []

    for metadata_file in candidate_files:
        source_graph_uri = (
            staged_graph_uri
            if metadata_file["filename"] == filename
            else metadata_file["graph_uri"]
        )

        add_operations.append(
            "ADD GRAPH "
            f"<{source_graph_uri}> "
            "TO GRAPH "
            f"<{staging_default_uri}>"
        )

    if add_operations:
        await store.update(
            ";\n".join(add_operations)
        )
        has_content = True

    if not has_content:
        return None

    return staging_default_uri

def _backup_existing_file(
    source: Path,
    backup: Path,
) -> bool:
    if not source.exists():
        return False

    shutil.copy2(
        source,
        backup,
    )

    return True

def _restore_file(
    destination: Path,
    backup: Path,
    existed_before: bool,
) -> None:
    if existed_before:
        if not backup.exists():
            raise FileNotFoundError(
                f"Backup file not found: {backup}"
            )

        os.replace(
            backup,
            destination,
        )
        return

    try:
        destination.unlink()
    except FileNotFoundError:
        pass

async def _save_upload_to_file(
    file: UploadFile,
    destination: Path,
    max_bytes: int,
) -> int:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".upload",
        dir=destination.parent,
    )

    total = 0

    try:
        with os.fdopen(
            temp_fd,
            "wb",
        ) as output:
            while True:
                chunk = await file.read(
                    1024 * 1024
                )

                if not chunk:
                    break

                total += len(chunk)

                if total > max_bytes:
                    max_mb = (
                        max_bytes
                        // (1024 * 1024)
                    )

                    raise HTTPException(
                        413,
                        f"Uploaded file exceeds the {max_mb} MB limit.",
                    )

                output.write(chunk)

            output.flush()
            os.fsync(output.fileno())

        os.replace(
            temp_name,
            destination,
        )

        return total

    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass

        raise


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
    atomic_write_json(
        PREFERENCES_FILE,
        prefs,
    )

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    return {"site_title": "Semantta", "base_iri": ""}

def save_settings(settings):
    atomic_write_json(
        SETTINGS_FILE,
        settings,
    )

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
    await store.update(f"""
        DELETE {{ GRAPH <{SHAPES_GRAPH}> {{ <{shape_uri}> ?p ?o }} }}
        WHERE  {{ GRAPH <{SHAPES_GRAPH}> {{
            <{shape_uri}> ?p ?o .
            FILTER(?p NOT IN ({keep_filter}))
        }} }}
    """)

    list_constraints = {
        str(SH["in"]),
        str(SH.languageIn),
    }

    triples = ""
    next_list_id = 0

    for pred, val in constraints.items():
        if val is None or val == "":
            continue

        if isinstance(val, list) and pred in list_constraints:
            if not val:
                triples += (
                    f"<{shape_uri}> <{pred}> "
                    f"<{RDF.nil}> .\n"
                )
                continue

            nodes = [
                f"_:semantta_constraint_list_{next_list_id + i}"
                for i in range(len(val))
            ]
            next_list_id += len(val)

            triples += (
                f"<{shape_uri}> <{pred}> {nodes[0]} .\n"
            )

            for i, item in enumerate(val):
                rest = (
                    nodes[i + 1]
                    if i + 1 < len(nodes)
                    else f"<{RDF.nil}>"
                )

                triples += (
                    f"{nodes[i]} <{RDF.first}> "
                    f"{_format_constraint_value(pred, item)} ; "
                    f"<{RDF.rest}> {rest} .\n"
                )

        elif isinstance(val, list):
            for item in val:
                triples += (
                    f"<{shape_uri}> <{pred}> "
                    f"{_format_constraint_value(pred, item)} .\n"
                )

        else:
            triples += (
                f"<{shape_uri}> <{pred}> "
                f"{_format_constraint_value(pred, val)} .\n"
            )

    if triples:
        await store.update(
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
    def __init__(self, store: RDFStore):
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
            rows = await self.store.query(f"""
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

        active_classes = set(
            await shacl.get_active_classes()
        )
        active_props = set(
            await shacl.get_active_properties()
        )
        active_datatypes = set(
            await shacl.get_active_datatypes()
        )
        active_individuals = set(
            await shacl.get_active_individuals()
        )

        if not _used_uris_set:
            await rebuild_used_uris()

        md_uri_list = [
            uri
            for uri in _used_uris_set
            if uri not in candidates
            and not any(
                uri.startswith(ns)
                for ns in IGNORE_NAMESPACES
            )
        ]

        role_map = (
            await self._batch_entity_roles(md_uri_list)
            if md_uri_list
            else {}
        )

        for uri in md_uri_list:
            entity_type = role_map.get(uri)

            # Do not invent a role for a URI merely because it occurs
            # in the metadata graph.
            if entity_type is None:
                continue

            source_file = state["metadata_only_sources"].get(
                uri,
                "Metadata",
            )

            candidates[uri] = {
                "type": entity_type,
                "sources": [source_file],
                "in_onto": False,
            }

        # Include entities represented by active SHACL shapes, even when
        # they are not discoverable from instance-type/predicate usage.
        for uri in active_classes:
            candidates.setdefault(
                uri,
                {
                    "type": "class",
                    "sources": [
                        state["metadata_only_sources"].get(
                            uri,
                            "Metadata",
                        )
                    ],
                    "in_onto": False,
                },
            )

        for uri in active_props:
            if uri in candidates:
                continue

            if uri in SYSTEM_ANNOTATION_PROPERTIES:
                entity_type = "annotation_property"
            elif _get_property_type(uri, active_datatypes) == "datatype":
                entity_type = "datatype_property"
            else:
                entity_type = "object_property"

            candidates[uri] = {
                "type": entity_type,
                "sources": [
                    state["metadata_only_sources"].get(
                        uri,
                        "Metadata",
                    )
                ],
                "in_onto": False,
            }

        for uri in active_datatypes:
            candidates.setdefault(
                uri,
                {
                    "type": "datatype",
                    "sources": [
                        state["metadata_only_sources"].get(
                            uri,
                            "Metadata",
                        )
                    ],
                    "in_onto": False,
                },
            )

        for uri in active_individuals:
            candidates.setdefault(
                uri,
                {
                    "type": "individual",
                    "sources": [
                        state["metadata_only_sources"].get(
                            uri,
                            "Metadata",
                        )
                    ],
                    "in_onto": False,
                },
            )

        entity_labels = {
            uri: get_label(uri)
            for uri in candidates
        }

        metadata_only_uris = [
            uri
            for uri, candidate in candidates.items()
            if not candidate["in_onto"]
        ]

        entity_labels.update(
            await _get_stored_labels(metadata_only_uris)
        )

        result = []
        for uri, cand in candidates.items():
            etype = cand["type"]
            if etype == "class":
                active = uri in active_classes
            elif etype == "datatype":
                active = uri in active_datatypes
            elif etype in (
                "object_property",
                "datatype_property",
                "annotation_property",
            ):
                active = uri in active_props
            elif etype == "individual":
                active = uri in active_individuals
            else:
                active = False

            item = ProfileEntityItem(
                uri=uri,
                label=entity_labels.get(uri) or get_label(uri),
                type=etype,
                in_onto=cand["in_onto"],
                active=active,
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
        linked = await self.store.query(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            SELECT ?propUri ?order WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    <{shape_uri}> sh:property ?propShape .
                    ?propShape sh:path ?propUri .
                    OPTIONAL {{ ?propShape sh:order ?order }}
                }}
            }}""")

        orphan = await self.store.query(f"""
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
        rows = await self.store.query(f"""
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
        active_datatypes = set(
            await shacl.get_active_datatypes()
        )
        for ref in prop_refs:
            prop_uri = ref["uri"]
            ptype = _get_property_type(
                prop_uri,
                active_datatypes,
            )
            ranges = get_property_ranges(prop_uri)
            datatype = ranges[0] if ptype == "datatype" and ranges else "http://www.w3.org/2001/XMLSchema#string"
            suggestions = await get_instance_suggestions(ranges) if ptype == "object" else []
            card = get_property_cardinality(class_uri, prop_uri)
            shacl_constraints = await self._get_property_constraints(prop_uri)

            if "class" in shacl_constraints:
                ptype = "object"
                ranges = [shacl_constraints["class"]]
                suggestions = await get_instance_suggestions(ranges)
            if "datatype" in shacl_constraints:
                ptype = "datatype"
                suggestions = []
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

    async def _batch_entity_roles(
        self,
        uris: list[str],
    ) -> Dict[str, str]:
        unique_uris = sorted(set(uris))
        valid_uris = [
            uri
            for uri in unique_uris
            if is_valid_uri(uri)
        ]

        if len(valid_uris) != len(unique_uris):
            logger.warning(
                "Skipping %d unsupported URI(s) during "
                "Application Profile entity discovery. "
                "The RDF data has not been modified.",
                len(unique_uris) - len(valid_uris),
            )

        if not valid_uris:
            return {}

        values = " ".join(
            _sparql_iri(uri, "entity URI")
            for uri in valid_uris
        )

        async def select_classes():
            rows = await self.store.query(f"""
                SELECT DISTINCT ?uri WHERE {{
                    VALUES ?uri {{ {values} }}
                    ?s a ?uri .
                }}
            """)
            return {row["uri"] for row in rows}

        async def select_object_props():
            rows = await self.store.query(f"""
                SELECT DISTINCT ?uri WHERE {{
                    VALUES ?uri {{ {values} }}
                    ?s ?uri ?o .
                    FILTER(isIRI(?o))
                }}
            """)
            return {row["uri"] for row in rows}

        async def select_datatype_props():
            rows = await self.store.query(f"""
                SELECT DISTINCT ?uri WHERE {{
                    VALUES ?uri {{ {values} }}
                    ?s ?uri ?o .
                    FILTER(isLiteral(?o))
                }}
            """)
            return {row["uri"] for row in rows}

        async def select_individuals():
            rows = await self.store.query(f"""
                SELECT DISTINCT ?uri WHERE {{
                    VALUES ?uri {{ {values} }}
                    ?uri a <{OWL.NamedIndividual}> .
                }}
            """)
            return {row["uri"] for row in rows}

        (
            classes_set,
            obj_props_set,
            data_props_set,
            individuals_set,
        ) = await asyncio.gather(
            select_classes(),
            select_object_props(),
            select_datatype_props(),
            select_individuals(),
        )

        role_map = {}

        for uri in valid_uris:
            if uri in classes_set:
                role_map[uri] = "class"
            elif uri in individuals_set:
                role_map[uri] = "individual"
            elif uri in obj_props_set:
                role_map[uri] = "object_property"
            elif uri in data_props_set:
                role_map[uri] = "datatype_property"

        return role_map

    async def _get_shacl_domains(self) -> Dict[str, List[str]]:
        if hasattr(self, '_cached_domains') and self._cached_domains is not None:
            return self._cached_domains
        rows = await self.store.query(f"""
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
    def __init__(self, store: RDFStore, on_change: Optional[Callable[[], None]] = None):
        self.store = store
        self._shapes_cache = None
        self._on_change = on_change

    def _changed(self):
        if self._on_change:
            self._on_change()

    async def _repair_legacy_datatype_constraints(
        self,
        shapes_graph: Graph,
    ) -> None:
        """Migrate property shapes that use datatype ranges as classes."""
        active_datatypes = set(
            await self.get_active_datatypes()
        )

        repairs = []

        # Only inspect property shapes, which are identified by sh:path.
        for shape_uri, _property_uri in list(
            shapes_graph.subject_objects(SH.path)
        ):
            if not isinstance(shape_uri, URIRef):
                continue

            # Older generated profiles may have emitted sh:class for
            # custom datatypes because they were not recognized as datatypes.
            for old_range in list(
                shapes_graph.objects(shape_uri, SH["class"])
            ):
                if not isinstance(old_range, URIRef):
                    continue

                if not _is_datatype_uri(
                    str(old_range),
                    state["combined_onto_graph"],
                    active_datatypes,
                ):
                    continue


                new_predicate = SH.datatype
                new_value = old_range

                repairs.append((
                    shape_uri,
                    SH["class"],
                    old_range,
                    new_predicate,
                    new_value,
                ))

        for (
            shape_uri,
            old_predicate,
            old_value,
            new_predicate,
            new_value,
        ) in repairs:
            await self.store.update(f"""
                DELETE {{
                    GRAPH <{SHAPES_GRAPH}> {{
                        {shape_uri.n3()}
                        {old_predicate.n3()}
                        {old_value.n3()} .
                    }}
                }}
                INSERT {{
                    GRAPH <{SHAPES_GRAPH}> {{
                        {shape_uri.n3()}
                        {new_predicate.n3()}
                        {new_value.n3()} .
                    }}
                }}
                WHERE {{
                    GRAPH <{SHAPES_GRAPH}> {{
                        {shape_uri.n3()}
                        {old_predicate.n3()}
                        {old_value.n3()} .
                    }}
                }}
            """)

            shapes_graph.remove((
                shape_uri,
                old_predicate,
                old_value,
            ))
            shapes_graph.add((
                shape_uri,
                new_predicate,
                new_value,
            ))

        if repairs:
            self._changed()

    async def _get_shapes_graph(self) -> Graph:
        if self._shapes_cache is None:
            shapes_graph = await self.store.load_shapes_graph()

            if shapes_graph is None:
                raise RuntimeError(
                    "Failed to load the SHACL shapes graph from Fuseki. "
                    "Validation cannot continue without the shapes graph."
                )

            if not isinstance(shapes_graph, Graph):
                raise TypeError(
                    "FusekiStore.load_shapes_graph() must return an "
                    f"rdflib.Graph, not {type(shapes_graph).__name__}."
                )

            self._shapes_cache = shapes_graph

        return self._shapes_cache

    def _property_datatype_from_shapes(
        self,
        shapes_graph: Graph,
        prop_uri: str,
    ) -> Optional[str]:
        """Resolve a property's datatype from SHACL, then ontology ranges."""
        datatype_uris = {
            str(datatype)
            for property_shape in shapes_graph.subjects(
                SH.path,
                URIRef(prop_uri),
            )
            for datatype in shapes_graph.objects(
                property_shape,
                SH.datatype,
            )
        }

        if len(datatype_uris) > 1:
            raise HTTPException(
                500,
                f"Conflicting SHACL datatype constraints for {prop_uri}.",
            )

        if datatype_uris:
            return next(iter(datatype_uris))

        # Preserve the ontology's declared range when the profile has
        # not explicitly set a datatype constraint.
        if _get_property_type(prop_uri) == "datatype":
            ranges = get_property_ranges(prop_uri)
            if ranges:
                return ranges[0]

        return None

    async def get_property_datatype(
        self,
        prop_uri: str,
    ) -> Optional[str]:
        """Return the effective datatype for a metadata property."""
        shapes_graph = await self._get_shapes_graph()
        return self._property_datatype_from_shapes(
            shapes_graph,
            prop_uri,
        )

    def invalidate_shapes_cache(self):
        self._shapes_cache = None

    async def _set_default_constraints(self, prop_uri: str, class_uri: Optional[str] = None):
        shape_uri = shape_uri_for_entity(prop_uri, "property", state["prefix_map"])
        active_datatypes = set(await self.get_active_datatypes())
        ptype = _get_property_type(prop_uri, active_datatypes)
        ranges = get_property_ranges(prop_uri)
        card = get_property_cardinality(class_uri, prop_uri) if class_uri else None

        constraints = {}

        known_datatype_ranges = [
            range_uri
            for range_uri in ranges
            if _is_datatype_uri(
                range_uri,
                state["combined_onto_graph"],
                active_datatypes,
            )
        ]

        specific_datatype_ranges = [
            range_uri
            for range_uri in known_datatype_ranges
        ]

        if (
            ptype == "object"
            and ranges
            and _is_specific_range(ranges[0])
        ):
            constraints[str(SH["class"])] = ranges[0]

        elif ptype == "datatype":
            if specific_datatype_ranges:
                constraints[str(SH.datatype)] = (
                    specific_datatype_ranges[0]
                )

            elif ranges:
                # An explicitly declared owl:DatatypeProperty can have a
                # custom range that is not separately registered as rdfs:Datatype.
                selected_range = ranges[0]
                constraints[str(SH.datatype)] = selected_range

        if card:
            minc = card.get("minCardinality")
            maxc = card.get("maxCardinality")
            if minc is not None:
                constraints[str(SH.minCount)] = minc
            if maxc is not None:
                constraints[str(SH.maxCount)] = maxc

        for pred, val in constraints.items():
            val_triple = _format_constraint_value(pred, val)
            await self.store.update(f"""
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
        await self.store.update(f"""
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
        await self.store.update(f"""
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
        await self.store.update(f"DELETE WHERE {{ GRAPH <{SHAPES_GRAPH}> {{ <{shape_uri}> ?p ?o }} }}")
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
        await self.store.update(f"DELETE WHERE {{ GRAPH <{SHAPES_GRAPH}> {{ <{shape_uri}> ?p ?o }} }}")
        self._changed()

    async def add_property_global(self, prop_uri: str):
        shape_uri = shape_uri_for_entity(prop_uri, "property", state["prefix_map"])
        await self.store.update(f"""
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
        await self.store.update(f"DELETE WHERE {{ GRAPH <{SHAPES_GRAPH}> {{ <{shape_uri}> ?p ?o }} }}")
        self._changed()

    async def get_active_classes(self) -> List[str]:
        rows = await self.store.query(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            SELECT DISTINCT ?class WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    ?shape a sh:NodeShape ; sh:targetClass ?class .
                }}
            }}
        """)
        return [r["class"] for r in rows]

    async def get_active_properties(self) -> List[str]:
        rows = await self.store.query(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            SELECT DISTINCT ?prop WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    ?shape sh:path ?prop .
                }}
            }}
        """)
        return [r["prop"] for r in rows]

    async def get_active_datatypes(self) -> List[str]:
        rows = await self.store.query(f"""
            PREFIX sh: <{SH}>

            SELECT DISTINCT ?uri WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    ?shape a sh:NodeShape ;
                           sh:targetNode ?uri .

                    FILTER(
                        STRSTARTS(
                            STR(?shape),
                            "urn:shape:datatype:"
                        )
                    )
                }}
            }}
        """)

        return [row["uri"] for row in rows]

    async def get_active_individuals(self) -> List[str]:
        rows = await self.store.query(f"""
            PREFIX sh: <{SH}>

            SELECT DISTINCT ?uri WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    ?shape a sh:NodeShape ;
                           sh:targetNode ?uri .

                    FILTER(
                        STRSTARTS(
                            STR(?shape),
                            "urn:shape:individual:"
                        )
                    )
                }}
            }}
        """)

        return [row["uri"] for row in rows]

    async def extract_metadata_vocabulary_entities(
        self,
        graph_uris: List[str],
    ) -> Dict[str, Set[str]]:
        """Extract vocabulary entities by URI and semantic role."""
        entities: Dict[str, Set[str]] = {
            "class": set(),
            "property": set(),
            "datatype": set(),
            "individual": set(),
        }

        if not graph_uris:
            return entities

        known_individual_uris = [
            entity["uri"]
            for ontology in state["ontologies"]
            for entity in ontology["entities"]
            if entity["type"] == "individual"
        ]

        rows = await self.store.query(
            _metadata_vocabulary_query(
                graph_uris,
                known_individual_uris,
            )
        )

        for row in rows:
            uri = row.get("term", "")
            role = row.get("role", "")

            if (
                role in entities
                and is_valid_uri(uri)
                and not uri.startswith("urn:bnid:")
            ):
                entities[role].add(uri)

        return entities

    async def integrate_metadata_graphs(
        self,
        graph_uris: List[str],
        source: str = "Metadata",
    ) -> Dict[str, Set[str]]:
        """Integrate vocabulary extracted from the specified metadata graphs."""
        graph_uris = sorted({
            uri for uri in graph_uris if uri
        })

        if not graph_uris:
            raise HTTPException(
                400,
                "No metadata graphs provided.",
            )

        entities = await self.extract_metadata_vocabulary_entities(
            graph_uris
        )

        class_uris = entities["class"]
        property_uris = entities["property"]
        datatype_uris = entities["datatype"]
        individual_uris = entities["individual"]

        if not any((
            class_uris,
            property_uris,
            datatype_uris,
            individual_uris,
        )):
            raise HTTPException(
                400,
                "No vocabulary entities found in metadata files.",
            )

        graph_values = _metadata_graph_values(graph_uris)

        pair_rows = await self.store.query(f"""
            PREFIX rdf: <{RDF}>

            SELECT DISTINCT ?class ?prop WHERE {{
                VALUES ?graph {{ {graph_values} }}

                GRAPH ?graph {{
                    ?instance rdf:type ?class .
                    ?instance ?prop ?value .
                    FILTER(?prop != rdf:type)
                }}
            }}
        """)

        pairs = defaultdict(set)

        for row in pair_rows:
            class_uri = row.get("class")
            prop_uri = row.get("prop")

            if (
                class_uri in class_uris
                and prop_uri in property_uris
            ):
                pairs[class_uri].add(prop_uri)

        shape_triples = []

        for class_uri in sorted(class_uris):
            class_shape_uri = _sparql_iri(
                shape_uri_for_entity(
                    class_uri,
                    "class",
                    state["prefix_map"],
                ),
                "class shape URI",
            )

            shape_triples.append(
                f"{class_shape_uri} a sh:NodeShape ; "
                f"sh:targetClass "
                f"{_sparql_iri(class_uri, 'class URI')} ."
            )

        for prop_uri in sorted(property_uris):
            property_shape_uri = _sparql_iri(
                shape_uri_for_entity(
                    prop_uri,
                    "property",
                    state["prefix_map"],
                ),
                "property shape URI",
            )

            shape_triples.append(
                f"{property_shape_uri} a sh:PropertyShape ; "
                f"sh:path "
                f"{_sparql_iri(prop_uri, 'property URI')} ."
            )

        for datatype_uri in sorted(datatype_uris):
            datatype_shape_uri = _sparql_iri(
                shape_uri_for_entity(
                    datatype_uri,
                    "datatype",
                    state["prefix_map"],
                ),
                "datatype shape URI",
            )

            shape_triples.append(
                f"{datatype_shape_uri} a sh:NodeShape ; "
                f"sh:targetNode "
                f"{_sparql_iri(datatype_uri, 'datatype URI')} ."
            )

        for individual_uri in sorted(individual_uris):
            individual_shape_uri = _sparql_iri(
                shape_uri_for_entity(
                    individual_uri,
                    "individual",
                    state["prefix_map"],
                ),
                "individual shape URI",
            )

            shape_triples.append(
                f"{individual_shape_uri} a sh:NodeShape ; "
                f"sh:targetNode "
                f"{_sparql_iri(individual_uri, 'individual URI')} ."
            )

        # Profile generation is additive. Do not call _sync_entity_links()
        # here because its class-editing behavior replaces the complete
        # property-link set.
        for class_uri, props in pairs.items():
            for prop_uri in sorted(props):
                domains = get_property_domains(prop_uri)

                if domains and not any(
                    is_subclass(class_uri, [domain])
                    or class_uri == domain
                    for domain in domains
                ):
                    continue

                class_shape_uri = _sparql_iri(
                    shape_uri_for_entity(
                        class_uri,
                        "class",
                        state["prefix_map"],
                    ),
                    "class shape URI",
                )

                property_shape_uri = _sparql_iri(
                    shape_uri_for_entity(
                        prop_uri,
                        "property",
                        state["prefix_map"],
                    ),
                    "property shape URI",
                )

                shape_triples.append(
                    f"{class_shape_uri} sh:property "
                    f"{property_shape_uri} ."
                )

        if shape_triples:
            await self.store.update(f"""
                PREFIX sh: <{SH}>

                INSERT DATA {{
                    GRAPH <{SHAPES_GRAPH}> {{
                        {" ".join(shape_triples)}
                    }}
                }}
            """)

        # Add default constraints only where they do not already exist.
        for prop_uri in sorted(property_uris):
            await self._set_default_constraints(prop_uri)

        # Preserve existing property order. Restore the default order only
        # when the property shape does not already have an order.
        order_map = await get_global_property_order()
        order_values = []

        for prop_uri in sorted(property_uris):
            if prop_uri not in order_map:
                continue

            property_shape_uri = _sparql_iri(
                shape_uri_for_entity(
                    prop_uri,
                    "property",
                    state["prefix_map"],
                ),
                "property shape URI",
            )

            order_value = _format_constraint_value(
                str(SH.order),
                order_map[prop_uri],
            )

            order_values.append(
                f"({property_shape_uri} {order_value})"
            )

        if order_values:
            await self.store.update(f"""
                PREFIX sh: <{SH}>

                INSERT {{
                    GRAPH <{SHAPES_GRAPH}> {{
                        ?shape sh:order ?ord
                    }}
                }}
                WHERE {{
                    VALUES (?shape ?ord) {{
                        {" ".join(order_values)}
                    }}

                    FILTER NOT EXISTS {{
                        GRAPH <{SHAPES_GRAPH}> {{
                            ?shape sh:order ?existing
                        }}
                    }}
                }}
            """)

        integrated_uris = set().union(
            *entities.values()
        )

        for uri in integrated_uris:
            current_source = state["metadata_only_sources"].get(uri)

            if (
                current_source is None
                or (
                    current_source == "Metadata"
                    and source != "Metadata"
                )
            ):
                state["metadata_only_sources"][uri] = source

            state["non_integrated_uris"].discard(uri)

        self._changed()
        return entities

    async def generate_from_metadata(self):
        """Generate the profile from all registered metadata files."""
        graph_uris = sorted({
            item["graph_uri"]
            for item in state["metadata_files"]
            if item.get("graph_uri")
        })

        if not graph_uris:
            raise HTTPException(
                400,
                "No metadata files found.",
            )

        await self.integrate_metadata_graphs(
            graph_uris,
            source="Metadata",
        )

    async def validate_instance(self, class_uris: List[str], properties: Dict[str, List[str]]):
        explicit_shapes = await self._get_shapes_graph()

        data_g = Graph()
        inst_uri = URIRef("urn:temp:instance")

        for cls in class_uris:
            data_g.add((inst_uri, RDF.type, URIRef(cls)))

        for pred, vals in properties.items():
            if not isinstance(vals, list):
                vals = [vals]

            datatype_uri = self._property_datatype_from_shapes(
                explicit_shapes,
                pred,
            )

            for val in vals:
                if datatype_uri is not None:
                    literal = _metadata_literal(
                        val,
                        pred,
                        datatype_uri,
                    )
                    data_g.add((inst_uri, URIRef(pred), literal))
                elif _is_iri_value(val):
                    data_g.add(
                        (inst_uri, URIRef(pred), URIRef(val))
                    )
                else:
                    data_g.add(
                        (inst_uri, URIRef(pred), Literal(str(val)))
                    )

        explicit_shapes = await self._get_shapes_graph()

        if len(explicit_shapes) == 0:
            for class_uri in class_uris:
                for prop_uri, values in properties.items():
                    card = get_property_cardinality(class_uri, prop_uri)
                    if (minc := card["minCardinality"]) is not None and len(values) < minc:
                        raise HTTPException(400, f"{prop_uri} requires at least {minc} value(s)")
                    if (maxc := card["maxCardinality"]) is not None and len(values) > maxc:
                        raise HTTPException(400, f"{prop_uri} allows at most {maxc} value(s)")
            return True


        # Load descriptions of referenced resources into the temporary
        # data graph so SHACL can check their existing RDF types.
        reference_uris = set()

        for pred, vals in properties.items():
            if not isinstance(vals, list):
                vals = [vals]

            datatype_uri = self._property_datatype_from_shapes(
                explicit_shapes,
                pred,
            )

            # A value with an explicit literal datatype is not a resource,
            # even if its lexical value looks like a URL.
            if datatype_uri is None:
                reference_uris.update(
                    val for val in vals if _is_iri_value(val)
                )

        if reference_uris:
            reference_terms = " ".join(
                _sparql_iri(uri, "referenced resource URI")
                for uri in sorted(reference_uris)
            )

            referenced_turtle = await self.store.construct(f"""
                CONSTRUCT {{ ?ref ?p ?o }}
                WHERE {{
                    VALUES ?ref {{ {reference_terms} }}
                    {{
                        ?ref ?p ?o .
                    }}
                    UNION
                    {{
                        GRAPH ?g {{ ?ref ?p ?o . }}
                        FILTER(?g != <{SHAPES_GRAPH}>)
                    }}
                }}
            """)

            if referenced_turtle.strip():
                referenced_graph = Graph()
                referenced_graph.parse(
                    data=referenced_turtle,
                    format="turtle",
                )
                data_g += referenced_graph

        conforms, raw_graph, _ = pyshacl.validate(
            data_g,
            shacl_graph=explicit_shapes,
            ont_graph=validation_ontology_graph,
            do_owl_imports=False,
            inference="rdfs",
            abort_on_first=False,
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
    property_types = (
        "object_property",
        "datatype_property",
        "annotation_property",
    )

    if etype not in property_types and etype != "class":
        return

    if not isinstance(linked_uris, list):
        raise HTTPException(400, "Linked entities must be a list")

    entity_ref = _sparql_iri(entity_uri, "entity URI")
    linked_refs = {
        uri: _sparql_iri(uri, "linked entity URI")
        for uri in linked_uris
    }

    if etype in property_types:
        prop_shape_uri = shape_uri_for_entity(
            entity_uri, "property", state["prefix_map"]
        )
        prop_shape_ref = _sparql_iri(
            prop_shape_uri, "property shape URI"
        )
        desired_classes = set(linked_refs)

        cur_rows = await store.query(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            SELECT ?class WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    ?classShape sh:targetClass ?class ;
                                sh:property {prop_shape_ref} .
                }}
            }}
        """)
        current_classes = {r["class"] for r in cur_rows}

        additions = desired_classes - current_classes
        removals = current_classes - desired_classes

        # Validate all additions before mutating the profile.
        domains = get_property_domains(entity_uri)
        for cls in additions:
            if domains and not any(
                is_subclass(cls, [domain]) or cls == domain
                for domain in domains
            ):
                raise HTTPException(
                    400,
                    f"Class {cls} is not in the domain of property {entity_uri}",
                )

        operations = []

        if removals:
            triples = []
            for cls in sorted(removals):
                class_shape_uri = shape_uri_for_entity(
                    cls, "class", state["prefix_map"]
                )
                class_shape_ref = _sparql_iri(
                    class_shape_uri, "class shape URI"
                )
                triples.append(
                    f"{class_shape_ref} sh:property {prop_shape_ref} ."
                )

            operations.append(f"""
                DELETE DATA {{
                    GRAPH <{SHAPES_GRAPH}> {{
                        {" ".join(triples)}
                    }}
                }}
            """)

        if additions:
            triples = []
            for cls in sorted(additions):
                class_shape_uri = shape_uri_for_entity(
                    cls, "class", state["prefix_map"]
                )
                class_shape_ref = _sparql_iri(
                    class_shape_uri, "class shape URI"
                )
                triples.append(
                    f"{class_shape_ref} a sh:NodeShape ; "
                    f"sh:targetClass {linked_refs[cls]} ; "
                    f"sh:property {prop_shape_ref} ."
                )

            operations.append(f"""
                INSERT DATA {{
                    GRAPH <{SHAPES_GRAPH}> {{
                        {" ".join(triples)}
                    }}
                }}
            """)

        if operations:
            await store.update(
                "PREFIX sh: <http://www.w3.org/ns/shacl#>\n"
                + ";\n".join(operations)
            )

    elif etype == "class":
        class_shape_uri = shape_uri_for_entity(
            entity_uri, "class", state["prefix_map"]
        )
        class_shape_ref = _sparql_iri(
            class_shape_uri, "class shape URI"
        )
        desired_props = set(linked_refs)

        # Validate every desired property before deleting any links.
        for prop_uri in sorted(desired_props):
            domains = get_property_domains(prop_uri)
            if domains and not any(
                is_subclass(entity_uri, [domain])
                or entity_uri == domain
                for domain in domains
            ):
                raise HTTPException(
                    400,
                    f"Property {prop_uri} does not have class {entity_uri} in its domain",
                )

        operations = [f"""
            DELETE WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{
                    {class_shape_ref} sh:property ?ps
                }}
            }}
        """]

        if desired_props:
            triples = [
                f"{class_shape_ref} a sh:NodeShape ; "
                f"sh:targetClass {entity_ref} ."
            ]

            for prop_uri in sorted(desired_props):
                prop_shape_uri = shape_uri_for_entity(
                    prop_uri, "property", state["prefix_map"]
                )
                prop_shape_ref = _sparql_iri(
                    prop_shape_uri, "property shape URI"
                )

                triples.append(
                    f"{prop_shape_ref} a sh:PropertyShape ; "
                    f"sh:path {linked_refs[prop_uri]} ."
                )
                triples.append(
                    f"{class_shape_ref} sh:property {prop_shape_ref} ."
                )

            operations.append(f"""
                INSERT DATA {{
                    GRAPH <{SHAPES_GRAPH}> {{
                        {" ".join(triples)}
                    }}
                }}
            """)

        await store.update(
            "PREFIX sh: <http://www.w3.org/ns/shacl#>\n"
            + ";\n".join(operations)
        )

# ---------------------------------------------------------------------------
#  Plugin & Theme Helpers
# ---------------------------------------------------------------------------
def load_plugins_config():
    if not os.path.exists(PLUGINS_CONFIG_FILE):
        return {}
    with open(PLUGINS_CONFIG_FILE) as f:
        return json.load(f)

def save_plugins_config(config):
    atomic_write_json(
        PLUGINS_CONFIG_FILE,
        config,
    )

def list_plugins():
    if not os.path.isdir(PLUGINS_DIR):
        return []
    config = load_plugins_config()
    plugins = []
    for entry in os.listdir(PLUGINS_DIR):
        plugin_path = plugin_dir(entry)
        if not plugin_path.is_dir():
            continue
        meta_file = plugin_manifest_path(entry)
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
        plugin_path = plugin_dir(entry)
        if not os.path.isdir(plugin_path):
            continue
        if not config.get(entry, {}).get("enabled", False):
            continue
        backend_init = plugin_path / "backend" / "__init__.py"
        if not backend_init.is_file():
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
            logger.exception("Failed to load plugin %s", entry)

def load_themes_config():
    if not os.path.exists(THEMES_CONFIG_FILE):
        return {}
    with open(THEMES_CONFIG_FILE) as f:
        return json.load(f)

def save_themes_config(config):
    atomic_write_json(
        THEMES_CONFIG_FILE,
        config,
    )

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
        theme_path = theme_dir(entry)
        if not theme_path.is_dir():
            continue
        meta_file = theme_manifest_path(entry)
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
    atomic_write_json(
        ACTIVE_THEME_FILE,
        {"active_theme": theme_folder},
    )

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

    filename = os.path.basename(original_path)
    cache_path = reasoned_cache_path(filename)
    metadata_path = reasoned_cache_metadata_path(filename)

    source_signature = _file_signature(original_path)
    owl_signature = _file_signature(OWL_FILE)

    cache_valid = False

    if os.path.exists(cache_path) and os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)

            cache_valid = (
                metadata.get("cache_version") == REASONED_CACHE_VERSION
                and metadata.get("source_signature") == source_signature
                and metadata.get("owl_vocabulary_signature") == owl_signature
            )
        except Exception:
            cache_valid = False

    if cache_valid:
        g = Graph()
        g.parse(cache_path, format="turtle")

        with open(original_path, "rb") as fh:
            content = fh.read()

        unreasoned = parse_ontology(content, fmt)
        return unreasoned, g

    with open(original_path, "rb") as fh:
        content = fh.read()

    unreasoned = parse_ontology(content, fmt)

    g = Graph()
    for t in unreasoned:
        g.add(t)

    apply_reasoning(g)

    g.serialize(destination=cache_path, format="turtle")

    metadata = {
        "cache_version": REASONED_CACHE_VERSION,
        "source_signature": source_signature,
        "owl_vocabulary_signature": owl_signature,
    }

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return unreasoned, g

def load_saved_ontologies():
    if not os.path.isdir(ONTOLOGY_DIR):
        refresh_display_prefix_map()
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
            meta = _load_ontology_metadata(f, unreasoned_g)
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
            logger.warning("Could not load ontology %s: %s", f, e, exc_info=True)

    refresh_display_prefix_map()

async def ensure_metadata_named_graphs():
    """
    Ensure every persisted metadata file has a corresponding Fuseki
    named graph.

    Existing files from pre-P5.2 installations are migrated using the
    streaming RDF ingestion foundation.
    """
    for filename in list_saved_metadata_files():
        source_path = Path(
            METADATA_DIR,
            filename,
        )

        graph_uri = metadata_graph_uri(
            filename
        )

        if await store.graph_exists(
            graph_uri
        ):
            continue

        ext = (
            filename
            .rsplit(".", 1)[-1]
            .lower()
            if "." in filename
            else ""
        )

        fmt = RDF_FORMAT_MAP.get(ext)

        if not fmt:
            logger.warning(
                "Skipping metadata migration for unsupported file: %s",
                filename,
            )
            continue

        progress["phase"] = (
            f"Migrating metadata: {filename}…"
        )

        temporary_nt = Path(
            tempfile.mkdtemp(
                prefix="semantta-metadata-migration-"
            )
        ) / f"{filename}.nt"

        try:
            await asyncio.to_thread(
                stream_rdf_to_ntriples,
                source_path,
                fmt,
                temporary_nt,
            )

            if not temporary_nt.exists():
                raise RuntimeError(
                    "Metadata conversion did not produce "
                    f"an N-Triples file: {temporary_nt}"
                )

            await store.bulk_load_nt_file(
                temporary_nt,
                graph_uri,
            )

            # Keep the rest of your EXISTING successful
            # migration code here unchanged.

        except Exception:
            logger.exception(
                "Failed to migrate metadata file %s; "
                "skipping this file and continuing startup.",
                filename,
            )

            # A failed upload can leave a partially populated
            # named graph. Remove it before continuing.
            try:
                await store.update(
                    f"DROP GRAPH <{graph_uri}>"
                )
            except Exception:
                logger.exception(
                    "Failed to remove partially migrated "
                    "metadata graph %s.",
                    graph_uri,
                )

            continue

        finally:
            if temporary_nt.exists():
                try:
                    temporary_nt.unlink()
                except OSError:
                    logger.warning(
                        "Could not remove temporary metadata "
                        "file: %s",
                        temporary_nt,
                        exc_info=True,
                    )

    progress["phase"] = ""

def load_saved_metadata():
    """Load metadata manifests without persisted integration status."""
    state["metadata_files"].clear()

    if not os.path.isdir(METADATA_DIR):
        return

    for filename in list_saved_metadata_files():
        metadata_path = os.path.join(
            METADATA_DIR,
            filename,
        )

        ext = (
            filename.rsplit(".", 1)[-1].lower()
            if "." in filename
            else ""
        )

        if ext not in RDF_FORMAT_MAP:
            logger.warning(
                "Skipping saved metadata for unsupported file format: %s",
                filename,
            )
            continue

        # Remove obsolete sidecars written by the former status system.
        sidecar_path = metadata_path + ".meta.json"

        try:
            if os.path.exists(sidecar_path):
                os.remove(sidecar_path)
        except OSError:
            logger.warning(
                "Could not remove obsolete metadata sidecar: %s",
                sidecar_path,
                exc_info=True,
            )

        state["metadata_files"].append({
            "filename": filename,
            "graph_uri": metadata_graph_uri(filename),
        })

# Create global service instances (after all class definitions)
store: RDFStore = FusekiStore(
    config=FUSEKI_CONFIG,
    label_properties=LABEL_PROPERTIES,
)
ap = ApplicationProfile(store)
shacl = SHACLProfile(store, on_change=invalidate_profile)

@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_data_dirs()

    try:
        logger.info("Starting Semantta backend")

        add_default_prefixes()

        progress["phase"] = "Loading ontologies…"
        load_saved_ontologies()

        progress["phase"] = "Building indexes…"
        rebuild_precomputed()

        store.set_label_properties(
            LABEL_PROPERTIES
        )

        progress["phase"] = (
            "Migrating SHACL shape identifiers…"
        )

        await ensure_metadata_named_graphs()

        progress["phase"] = (
            "Loading metadata…"
        )

        load_saved_metadata()

        # Load starred instances
        if os.path.exists(STARS_FILE):
            with open(STARS_FILE) as f:
                state["starred_instance_uris"] = set(json.load(f))

        # Load created-instance provenance
        if os.path.exists(CREATED_INSTANCES_FILE):
            try:
                with open(
                    CREATED_INSTANCES_FILE,
                    encoding="utf-8",
                ) as f:
                    created_uris = json.load(f)

                if isinstance(created_uris, list):
                    state["created_instances"] = {
                        uri
                        for uri in created_uris
                        if isinstance(uri, str)
                        and is_valid_uri(uri)
                    }

            except Exception:
                logger.warning(
                    "Could not load created-instance provenance file: %s",
                    CREATED_INSTANCES_FILE,
                    exc_info=True,
                )

        if state["created_instances"]:
            values = " ".join(f"<{u}>" for u in state["created_instances"])
            query = (
                f"CONSTRUCT {{ ?s ?p ?o }} "
                f"WHERE {{ VALUES ?s {{ {values} }} . ?s ?p ?o . }}"
            )
            turtle = await store.construct(query)
            state["created_instances_graph"].parse(
                data=turtle,
                format="turtle",
            )

        await rebuild_default_data_graph()
        await rebuild_used_uris()

        load_plugins()

        state["display_format"] = load_preferences().get(
            "display_format",
            "iri",
        )
        state["public_display_blank_nodes"] = load_preferences().get(
            "public_display_blank_nodes",
            False,
        )

        settings = load_settings()
        state["site_title"] = settings.get("site_title", "Semantta")
        state["base_iri"] = settings.get("base_iri", "")
        state["applied_base_iri"] = settings.get(
            "applied_base_iri",
            settings.get("base_iri", ""),
        )

        active_theme = settings.get("active_theme", "default")
        set_active_theme(active_theme)

        await seed_core_active_entities()

        progress["phase"] = ""
        logger.info("Semantta backend is ready")

        yield

    finally:
        progress["phase"] = "Shutting down…"
        logger.info("Shutting down Semantta backend")

        await store.close()

        logger.info("Semantta backend stopped")
        progress["phase"] = ""

def _origin_from_referer(referer: str | None) -> str | None:
    """Extract a normalized origin from a Referer URL."""
    if not referer:
        return None

    try:
        parsed = urlsplit(referer)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None

    scheme = parsed.scheme.lower()

    if not scheme or not hostname:
        return None

    hostname = hostname.lower()

    # Restore brackets when reconstructing an IPv6 authority.
    if ":" in hostname:
        hostname = f"[{hostname}]"

    # Normalize explicit default ports to their origin representation.
    if (
        (scheme == "http" and port == 80)
        or (scheme == "https" and port == 443)
    ):
        port = None

    authority = (
        hostname
        if port is None
        else f"{hostname}:{port}"
    )

    return f"{scheme}://{authority}"


def _request_source_origin(request: Request) -> str | None:
    """Determine the request origin, falling back to Referer."""
    origin = request.headers.get("origin")

    if origin is not None:
        return origin.strip()

    return _origin_from_referer(
        request.headers.get("referer")
    )

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=TRUSTED_HOSTS,
)

@app.middleware("http")
async def enforce_local_api_security(
    request: Request,
    call_next,
):
    # Preserve the existing loopback-client restriction.
    client = request.client

    if client is None or not is_loopback_host(client.host):
        return JSONResponse(
            status_code=403,
            content={
                "detail": (
                    "Remote access is disabled. "
                    "Semantta accepts requests from localhost only."
                )
            },
        )

    # Validate the origin of every state-changing request.
    if request.method.upper() in UNSAFE_HTTP_METHODS:
        source_origin = _request_source_origin(request)

        if source_origin not in TRUSTED_REQUEST_ORIGINS:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        "The request origin is missing or not allowed "
                        "for state-changing requests."
                    )
                },
            )

    return await call_next(request)

@app.exception_handler(Exception)
async def internal_error_handler(
    request: Request,
    exc: Exception,
):
    logger.exception(
        "Unhandled API error: %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error.",
        },
    )

@app.get("/api/health")
async def health_check():
    """
    Return application readiness and RDF datastore availability.

    A 200 response means the backend is running and Fuseki is reachable.
    A 503 response means the backend is running but its RDF datastore is
    unavailable.
    """
    try:
        await store.healthcheck()
    except Exception:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "backend": "ok",
                "fuseki": "unavailable",
            },
        )

    return {
        "status": "ok",
        "backend": "ok",
        "fuseki": "ok",
    }

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
        stats = await get_cached_metadata_graph_stats(
            mf["graph_uri"]
        )

        vocab_ns = set()

        for term in stats.get("terms", []):
            ns = safe_namespace(term)

            if ns:
                vocab_ns.add(ns)

        meta_files.append(
            MetadataFileInfo(
                filename=mf["filename"],
                primary_iri=stats.get(
                    "primary_iri"
                ),
                namespaces=sorted(vocab_ns),
                instances_count=stats.get(
                    "instances_count",
                    0,
                ),
                triples_count=stats.get(
                    "triples_count",
                    0,
                ),
            )
        )

    public_display_blank_nodes = load_preferences().get(
        "public_display_blank_nodes",
        False,
    )

    instance_count = await get_cached_instance_count(
        include_blank_nodes=public_display_blank_nodes,
    )

    return StateResponse(
        ontologies=ontos,
        metadata_files=meta_files,
        profile_entities=profile_entities,
        instances=[],
        instance_count=instance_count,
        display_format=state["display_format"],
        prefix_map=state["display_prefix_map"],
        public_display_blank_nodes=public_display_blank_nodes,
        ontology_namespaces=sorted(
            state["all_ontology_namespaces"]
        ),
        site_title=state.get(
            "site_title",
            "Semantta",
        ),
        base_iri=state.get(
            "base_iri",
            "",
        ),
    )

@app.post("/api/ontology/upload")
async def upload_ontology(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "No file selected")
    filename = _require_safe_path_component(file.filename, "filename")

    if any(o["filename"] == filename for o in state["ontologies"]):
        raise HTTPException(400, f"Ontology '{filename}' is already imported.")

    contents = await _read_upload_with_limit(
        file,
        MAX_ONTOLOGY_UPLOAD_BYTES,
    )
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
        meta = extract_ontology_metadata(unreasoned)
        progress["phase"] = "Saving to disk…"
        os.makedirs(ONTOLOGY_DIR, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)

        ontology_path = _path_within_directory(
            ONTOLOGY_DIR,
            filename,
        )

        with ontology_path.open("wb") as file_handle:
            file_handle.write(contents)

        cache_path = _path_within_directory(
            CACHE_DIR,
            f"{filename}.reasoned.ttl",
        )
        metadata_path = _path_within_directory(
            CACHE_DIR,
            f"{filename}.reasoned.meta.json",
        )

        g.serialize(
            destination=cache_path,
            format="turtle",
        )

        with metadata_path.open("w", encoding="utf-8") as metadata_file:
            json.dump(
                {
                    "cache_version": REASONED_CACHE_VERSION,
                    "source_signature": _file_signature(ontology_path),
                    "owl_vocabulary_signature": _file_signature(OWL_FILE),
                },
                metadata_file,
                indent=2,
            )
        return unreasoned, g, entities, meta

    try:
        unreasoned_g, g, entities, meta = await asyncio.to_thread(do_import)
    except Exception as e:
        logger.exception(
            "Ontology import failed for %s",
            filename,
        )
        raise HTTPException(
            400,
            detail=(
                "Ontology import failed. "
                "Verify that the file is valid and matches its extension."
            ),
        ) from e
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
    refresh_display_prefix_map()
    for e in entities:
        await ap.resolve_entity_with_ontology(e["uri"])
    invalidate_caches()
    ap.invalidate()
    return {"status": "ok", "filename": filename}

@app.delete("/api/ontology/{filename}")
async def delete_ontology(filename: str):
    requested_filename = _require_safe_path_component(
        filename,
        "filename",
    )

    ontology = next(
        (
            item
            for item in state["ontologies"]
            if item.get("filename") == requested_filename
        ),
        None,
    )

    if ontology is None:
        raise HTTPException(404, "Ontology not found")

    # Use the registered filename for every filesystem operation.
    filename = _require_safe_path_component(
        ontology["filename"],
        "filename",
    )

    filepath = _path_within_directory(
        ONTOLOGY_DIR,
        filename,
    )
    cache_path = _path_within_directory(
        CACHE_DIR,
        f"{filename}.reasoned.ttl",
    )
    metadata_path = _path_within_directory(
        CACHE_DIR,
        f"{filename}.reasoned.meta.json",
    )

    # Validate all paths before changing application state or removing files.
    state["ontologies"].remove(ontology)

    for path in (filepath, cache_path, metadata_path):
        if path.is_file():
            path.unlink()

    if os.path.exists(cache_path):
        os.remove(cache_path)

    if os.path.exists(metadata_path):
        os.remove(metadata_path)

    state["combined_onto_graph"] = Graph()
    state["prefix_map"].clear()
    for o in state["ontologies"]:
        for t in o["graph"]: state["combined_onto_graph"].add(t)
        update_prefix_map(o["graph"], state["prefix_map"])
    refresh_display_prefix_map()
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
):
    if not state["ontologies"]:
        raise HTTPException(
            400,
            "Upload an ontology first.",
        )

    if not file.filename:
        raise HTTPException(
            400,
            "No file selected.",
        )

    filename = _require_safe_path_component(
        file.filename,
        "filename",
    )

    ext = (
        filename.rsplit(".", 1)[-1].lower()
        if "." in filename
        else ""
    )

    fmt = RDF_FORMAT_MAP.get(ext)

    if not fmt:
        raise HTTPException(
            400,
            f"Unsupported extension: .{ext}",
        )

    destination = _path_within_directory(
        METADATA_DIR,
        filename,
    )

    graph_uri = metadata_graph_uri(filename)

    meta_path = _path_within_directory(
        METADATA_DIR,
        f"{filename}.meta.json",
    )

    old_metadata_files = list(
        state["metadata_files"]
    )

    old_metadata_only_sources = dict(
        state["metadata_only_sources"]
    )

    candidate_files = _metadata_files_after_upload(
        filename,
        graph_uri,
    )

    staged_graph_uri = (
        _metadata_staging_graph_uri("source")
    )

    progress["phase"] = "Saving metadata…"

    work_dir = Path(
        tempfile.mkdtemp(
            prefix="semantta-metadata-",
            dir=METADATA_DIR,
        )
    )

    staged_source = _path_within_directory(
        work_dir,
        filename,
    )

    destination_backup = _path_within_directory(
        work_dir,
        f"{filename}.backup",
    )

    nt_path = _path_within_directory(
        work_dir,
        f"{filename}.nt",
    )

    default_stage_uri = None

    destination_existed = False

    destination_backup_ready = False

    fuseki_committed = False
    preserve_rollback_artifacts = False

    rollback_graph_uris = {graph_uri}

    graph_backups: Dict[str, str] = {}

    default_backup_uri = (
        _metadata_staging_graph_uri(
            "rollback-default"
        )
    )

    async def rollback_upload() -> None:
        nonlocal fuseki_committed
        nonlocal preserve_rollback_artifacts

        rollback_failed = False

        # Restore the Fuseki graphs if the new graph
        # transaction has already committed.
        if fuseki_committed:
            rollback_operations = [
                "CLEAR DEFAULT",
                "ADD SILENT GRAPH "
                f"<{default_backup_uri}> TO DEFAULT",
            ]

            for rollback_graph_uri in sorted(
                rollback_graph_uris
            ):
                backup_uri = graph_backups.get(
                    rollback_graph_uri
                )

                if backup_uri:
                    rollback_operations.append(
                        "COPY GRAPH "
                        f"<{backup_uri}> "
                        "TO GRAPH "
                        f"<{rollback_graph_uri}>"
                    )
                else:
                    rollback_operations.append(
                        "DROP SILENT GRAPH "
                        f"<{rollback_graph_uri}>"
                    )

            try:
                await store.update(
                    ";\n".join(
                        rollback_operations
                    )
                )

                fuseki_committed = False

            except Exception:
                rollback_failed = True

                logger.exception(
                    "Failed to restore Fuseki state "
                    "after metadata upload failure."
                )

        # Restore the original source file if its
        # backup was prepared successfully.
        if destination_backup_ready:
            try:
                _restore_file(
                    destination,
                    destination_backup,
                    destination_existed,
                )
            except Exception:
                rollback_failed = True

                logger.exception(
                    "Failed to restore metadata file %s",
                    destination,
                )

        # Restore the application state.
        state["metadata_files"] = (
            old_metadata_files
        )

        state["metadata_only_sources"] = (
            old_metadata_only_sources
        )

        clear_metadata_graph_stats()
        invalidate_instance_count()

        try:
            invalidate_caches()
            ap.invalidate()
        except Exception:
            logger.exception(
                "Failed to invalidate caches after "
                "metadata upload rollback."
            )

        if not fuseki_committed:
            await rebuild_used_uris()

        # Preserve database and filesystem recovery
        # artifacts if any restoration step failed.
        if rollback_failed:
            preserve_rollback_artifacts = True

            logger.error(
                "Metadata upload rollback was incomplete. "
                "Recovery artifacts retained at %s",
                work_dir,
            )

    try:
        destination_existed = (
            _backup_existing_file(
                destination,
                destination_backup,
            )
        )

        destination_backup_ready = True

        # ---------------------------------------------------------------
        # 1. Save to a temporary source file.
        #
        # The existing metadata file is untouched.
        # ---------------------------------------------------------------
        await _save_upload_to_file(
            file,
            staged_source,
            MAX_METADATA_UPLOAD_BYTES,
        )

        # ---------------------------------------------------------------
        # 2. Parse into a temporary N-Triples file.
        #
        # The existing Fuseki graph is untouched.
        # ---------------------------------------------------------------
        progress["phase"] = (
            "Parsing metadata…"
        )

        triple_count = await asyncio.to_thread(
            stream_rdf_to_ntriples,
            staged_source,
            fmt,
            nt_path,
        )

        if triple_count <= 0:
            raise HTTPException(
                400,
                "The metadata file contains no RDF triples.",
            )

        # ---------------------------------------------------------------
        # 3. Load the new metadata into a temporary Fuseki graph.
        #
        # The current metadata graph is untouched.
        # ---------------------------------------------------------------
        progress["phase"] = (
            "Staging metadata in Fuseki…"
        )

        await store.bulk_load_nt_file(
            file_path=nt_path,
            graph_uri=staged_graph_uri,
        )

        # ---------------------------------------------------------------
        # 4. Build the replacement DEFAULT graph in a temporary graph.
        # ---------------------------------------------------------------
        progress["phase"] = (
            "Preparing metadata graph…"
        )

        default_stage_uri = (
            await _stage_metadata_default_graph(
                candidate_files,
                filename,
                staged_graph_uri,
                work_dir,
            )
        )

        # ---------------------------------------------------------------
        # 5. Prepare the metadata source file and sidecar.
        #
        # This happens before the Fuseki commit so failures can be
        # rolled back to the previous files.
        # ---------------------------------------------------------------

        # Preserve the current RDF graphs before any
        # destructive changes are committed.
        backup_operations = [
            "COPY DEFAULT TO GRAPH "
            f"<{default_backup_uri}>"
        ]

        for old_graph_uri in sorted(
            rollback_graph_uris
        ):
            if await store.graph_exists(
                old_graph_uri
            ):
                backup_uri = (
                    _metadata_staging_graph_uri(
                        "rollback-source"
                    )
                )

                graph_backups[
                    old_graph_uri
                ] = backup_uri

                backup_operations.append(
                    "COPY GRAPH "
                    f"<{old_graph_uri}> "
                    "TO GRAPH "
                    f"<{backup_uri}>"
                )

        await store.update(
            ";\n".join(
                backup_operations
            )
        )

        # ---------------------------------------------------------------
        # 6. ONE Fuseki transaction.
        #
        # All destructive graph changes happen together.
        # ---------------------------------------------------------------
        progress["phase"] = (
            "Committing metadata…"
        )

        operations = []

        # Replace the target metadata graph.
        operations.append(
            "MOVE GRAPH "
            f"<{staged_graph_uri}> "
            "TO GRAPH "
            f"<{graph_uri}>"
        )

        # Rebuild the default graph atomically within
        # the same Fuseki transaction.
        operations.append(
            "CLEAR DEFAULT"
        )

        if default_stage_uri:
            operations.append(
                "ADD GRAPH "
                f"<{default_stage_uri}> "
                "TO DEFAULT"
            )

            operations.append(
                "DROP GRAPH "
                f"<{default_stage_uri}>"
            )

        await store.update(
            ";\n".join(operations)
        )

        fuseki_committed = True

        os.replace(
            staged_source,
            destination,
        )

        # ---------------------------------------------------------------
        # 7. Update application state.
        # ---------------------------------------------------------------
        state["metadata_files"] = (
            candidate_files
        )

        new_sources = {
            uri: source
            for uri, source
            in old_metadata_only_sources.items()
            if source != filename
        }

        state["metadata_only_sources"] = (
            new_sources
        )

        clear_metadata_graph_stats()

        invalidate_instance_count()

        await rebuild_used_uris()

        invalidate_caches()
        ap.invalidate()

        metadata_file = next(
            item
            for item in state["metadata_files"]
            if item["filename"] == filename
        )

        if integrate_vocab:
            progress["phase"] = (
                "Integrating metadata vocabulary…"
            )

            try:
                await shacl.integrate_metadata_graphs(
                    [graph_uri],
                    source=filename,
                )
            except Exception:
                # The metadata upload has already committed.
                # Its status will be assessed on demand.
                logger.exception(
                    "Vocabulary integration failed for %s",
                    filename,
                )
                invalidate_profile()

        try:
            meta_path.unlink(missing_ok=True)
        except OSError:
            logger.warning(
                "Could not remove obsolete metadata sidecar: %s",
                meta_path,
                exc_info=True,
            )

        progress["phase"] = ""

        return {
            "status": "ok",
            "filename": filename,
        }

    except HTTPException:
        await rollback_upload()
        raise

    except Exception as exc:
        logger.exception(
            "Metadata import failed for %s",
            filename,
        )

        await rollback_upload()

        if isinstance(exc, RelativeIRIWithoutBaseError):
            raise HTTPException(
                400,
                detail=str(exc),
            ) from exc

        raise HTTPException(
            400,
            detail=(
                "Metadata import failed. "
                "Verify that the file is valid "
                "and matches its extension."
            ),
        ) from exc

    finally:
        progress["phase"] = ""

        # Remove temporary staging graphs when the
        # transaction did not remain committed.
        if not fuseki_committed:
            try:
                await store.update(
                    "DROP SILENT GRAPH "
                    f"<{staged_graph_uri}>"
                )
            except Exception:
                logger.exception(
                    "Failed to remove staged metadata graph %s",
                    staged_graph_uri,
                )

            if default_stage_uri:
                try:
                    await store.update(
                        "DROP SILENT GRAPH "
                        f"<{default_stage_uri}>"
                    )
                except Exception:
                    logger.exception(
                        "Failed to remove staged default graph %s",
                        default_stage_uri,
                    )

        if not preserve_rollback_artifacts:
            backup_graph_uris = list(
                graph_backups.values()
            )

            backup_graph_uris.append(
                default_backup_uri
            )

            for backup_uri in backup_graph_uris:
                try:
                    await store.update(
                        "DROP SILENT GRAPH "
                        f"<{backup_uri}>"
                    )
                except Exception:
                    logger.exception(
                        "Failed to remove metadata rollback "
                        "graph %s",
                        backup_uri,
                    )

            shutil.rmtree(
                work_dir,
                ignore_errors=True,
            )

        else:
            logger.error(
                "Metadata upload recovery artifacts retained at %s",
                work_dir,
            )

@app.post("/api/metadata/validate")
async def validate_metadata(data: dict):
    """Validate a metadata draft without persisting it."""
    class_uris = data.get("class_uris", [])
    stage = data.get("stage", "metadata")
    properties = data.get("properties", {})

    if (
        not isinstance(class_uris, list)
        or not class_uris
        or any(
            not isinstance(uri, str) or not uri.strip()
            for uri in class_uris
        )
    ):
        raise HTTPException(
            400,
            "At least one valid class URI is required",
        )

    class_uris = [uri.strip() for uri in class_uris]

    for class_uri in class_uris:
        _sparql_iri(class_uri, "class URI")

    if stage not in ("selection", "metadata"):
        raise HTTPException(
            400,
            "Invalid validation stage",
        )

    if not isinstance(properties, dict):
        raise HTTPException(
            400,
            "properties must be an object",
        )

    normalized_properties: dict[str, list[str]] = {}

    if stage == "metadata":
        for prop_uri, raw_values in properties.items():
            if not isinstance(prop_uri, str) or not prop_uri:
                raise HTTPException(
                    400,
                    "Invalid property URI",
                )

            if isinstance(raw_values, str):
                values = [raw_values]
            elif isinstance(raw_values, list):
                values = raw_values
            else:
                raise HTTPException(
                    400,
                    f"Values for {prop_uri} must be strings",
                )

            if any(not isinstance(value, str) for value in values):
                raise HTTPException(
                    400,
                    f"Values for {prop_uri} must be strings",
                )

            normalized_properties[prop_uri] = values
    else:
        # Class-selection checks must not fail merely because required
        # metadata fields have not yet been completed.
        normalized_properties = {}

    await check_disjoint_classes(class_uris)

    await _validate_metadata_profile_membership(
        class_uris,
        normalized_properties,
    )

    if stage == "metadata":
        await shacl.validate_instance(
            class_uris,
            normalized_properties,
        )

    return {"valid": True}

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
    if instance_uri is not None:
        if not isinstance(instance_uri, str):
            raise HTTPException(
                400,
                "Invalid instance URI.",
            )

        _sparql_iri(
            instance_uri,
            "instance URI",
        )
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
                candidate_ref = _sparql_iri(
                    candidate,
                    "instance URI",
                )

                rows = await store.query(
                    "SELECT ?p WHERE { "
                    f"{candidate_ref} ?p ?o "
                    "} LIMIT 1"
                )
                if not rows:
                    instance_uri = candidate
                    break

    properties = data.get("properties", {})

    await _validate_metadata_profile_membership(
        class_uris,
        properties,
    )

    await shacl.validate_instance(
        class_uris,
        properties,
    )

    instance_ref = _sparql_iri(
        instance_uri,
        "instance URI",
    )

    lines = [
        f"{instance_ref} a {_sparql_iri(c, 'class URI')} ."
        for c in class_uris
    ]
    for pred, vals in properties.items():
        pred_ref = _sparql_iri(
            pred,
            "property URI",
        )

        if not isinstance(vals, list):
            vals = [vals]

        datatype_uri = await shacl.get_property_datatype(pred)

        for val in vals:
            if datatype_uri is not None:
                literal = _metadata_literal(
                    val,
                    pred,
                    datatype_uri,
                )
                lines.append(
                    f"{instance_ref} {pred_ref} {literal.n3()} ."
                )
            elif _is_iri_value(val):
                value_ref = _sparql_iri(
                    val,
                    "value URI",
                )
                lines.append(
                    f"{instance_ref} {pred_ref} {value_ref} ."
                )
            else:
                literal = Literal(str(val))
                lines.append(
                    f"{instance_ref} {pred_ref} {literal.n3()} ."
                )

    triples = "\n".join(lines)
    await store.update(f"INSERT DATA {{ {triples} }}")
    invalidate_instance_count()
    g = Graph()
    g.parse(data=triples, format="turtle")
    for t in g: state["created_instances_graph"].add(t)

    state["created_instances"].add(
        instance_uri
    )

    save_created_instances()
    invalidate_profile()

    return {"status": "created", "uri": instance_uri}

@app.get(
    "/api/instances",
    response_model=InstanceListResponse,
)
async def list_instances(
    limit: int = Query(50, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    search: str = Query(""),
    type_uri: Optional[str] = Query(None),
    source: str = Query("all"),
    starred: bool = Query(False),
    include_blank_nodes: bool = Query(False),
):
    if source not in {
        "all",
        "imported",
        "created",
    }:
        raise HTTPException(
            400,
            "Invalid source filter.",
        )

    if type_uri and not is_valid_uri(type_uri):
        raise HTTPException(
            400,
            "Invalid type URI.",
        )

    created_uris = [
        uri
        for uri in state.get(
            "created_instances",
            set(),
        )
        if is_valid_uri(uri)
    ]

    starred_uris = [
        uri
        for uri in state.get(
            "starred_instance_uris",
            set(),
        )
        if is_valid_uri(uri)
    ]

    created_set = set(created_uris)
    starred_set = set(starred_uris)

    include_uris = None
    exclude_uris = None

    if source == "created":
        include_uris = created_uris

    elif source == "imported":
        exclude_uris = created_uris

    if starred:
        if not starred_uris:
            return InstanceListResponse(
                instances=[],
                has_more=False,
                limit=limit,
            )

        if include_uris is None:
            include_uris = starred_uris
        else:
            include_uris = [
                uri
                for uri in include_uris
                if uri in starred_set
            ]

    instances, has_more, metadata_uris = await store.list_instances(
        limit=limit,
        cursor=cursor,
        search=search,
        type_uri=type_uri,
        include_blank_nodes=include_blank_nodes,
        include_uris=include_uris,
        exclude_uris=exclude_uris,
    )

    type_uris = sorted({
        type_uri
        for instance in instances
        for type_uri in instance.get('types', [])
    })

    type_labels = await _resolve_display_labels(type_uris)

    for instance in instances:
        instance['type_labels'] = {
            type_uri: type_labels.get(type_uri, get_label(type_uri))
            for type_uri in instance.get('types', [])
        }

    next_cursor = (
        instances[-1]["uri"]
        if has_more and instances
        else None
    )

    starred_set = set(starred_uris)
    created_set = set(created_uris)

    for instance in instances:
        uri = instance["uri"]
        in_metadata = uri in metadata_uris
        created = uri in created_set

        if created and in_metadata:
            instance["source"] = "both"
        elif created:
            instance["source"] = "created"
        else:
            instance["source"] = "imported"

        instance["starred"] = (
            uri in starred_set
        )

    return InstanceListResponse(
        instances=[Instance(**instance) for instance in instances],
        has_more=has_more,
        next_cursor=next_cursor,
        limit=limit,
        cursor=cursor,
    )

@app.get("/api/instances/count")
async def get_instance_count(
    include_blank_nodes: bool = Query(False),
):
    count = await get_cached_instance_count(
        include_blank_nodes=include_blank_nodes,
    )

    return {"count": count}

@app.get("/api/instances/types")
async def list_instance_types():
    types = await store.get_instance_types()

    return {
        "types": types,
        "labels_by_uri": await _resolve_display_labels(types),
    }

@app.post("/api/instances/types-by-uri")
async def list_instance_types_by_uri(
    data: Dict[str, List[str]],
):
    """Return RDF types for a batch of graph-node URIs."""
    raw_uris = data.get("uris")

    if raw_uris is None:
        raise HTTPException(
            400,
            "The request must contain a list of URIs.",
        )

    if len(raw_uris) > 5000:
        raise HTTPException(
            400,
            "A maximum of 5000 URIs may be queried at once.",
        )

    uris = list(dict.fromkeys(raw_uris))

    for uri in uris:
        if not is_valid_uri(uri):
            raise HTTPException(
                400,
                f"Invalid instance URI: {uri}",
            )

    types_by_uri: Dict[str, List[str]] = {
        uri: [] for uri in uris
    }

    # Keep each SPARQL VALUES clause reasonably small.
    for offset in range(0, len(uris), 250):
        batch = uris[offset:offset + 250]
        values = " ".join(
            _sparql_iri(uri, "instance URI")
            for uri in batch
        )

        rows = await store.query(f"""
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

            SELECT DISTINCT ?instance ?type
            WHERE {{
                VALUES ?instance {{ {values} }}
                ?instance rdf:type ?type .
                FILTER(ISIRI(?type))
            }}
        """)

        for row in rows:
            instance_uri = row.get("instance")
            type_uri = row.get("type")

            if (
                instance_uri in types_by_uri
                and type_uri
                and type_uri not in types_by_uri[instance_uri]
            ):
                types_by_uri[instance_uri].append(type_uri)

    for types in types_by_uri.values():
        types.sort()

    type_uris = sorted({
        type_uri
        for types in types_by_uri.values()
        for type_uri in types
    })

    return {
        "types_by_uri": types_by_uri,
        "labels_by_uri": await _resolve_display_labels(type_uris),
    }

@app.get("/api/instances/{uri:path}/syntax")
async def get_instance_syntax(uri: str, format: str = "turtle"):
    uri_ref = _sparql_iri(
        uri,
        "instance URI",
    )
    mime_map = {
        "turtle": "text/turtle",
        "nt": "application/n-triples",
        "xml": "application/rdf+xml",
        "jsonld": "application/ld+json",
        "json-ld": "application/ld+json",
        "trig": "application/trig",
    }
    accept = mime_map.get(format, "text/turtle")
    query = f"""
        CONSTRUCT {{ {uri_ref} ?p ?o . ?s ?p {uri_ref} . }}
        WHERE {{ {{ {uri_ref} ?p ?o . }} UNION {{ ?s ?p {uri_ref} . }} }}
    """
    rdf_data = await store.construct(
        query,
        accept=accept,
    )

    return Response(
        content=rdf_data,
        media_type=accept,
    )

@app.post("/api/instances/{uri:path}/star")
async def toggle_star(uri: str):
    starred = state.setdefault("starred_instance_uris", set())
    if uri in starred:
        starred.discard(uri)
    else:
        starred.add(uri)

    # Persist to disk
    atomic_write_json(
        STARS_FILE,
        list(starred),
    )

    return {
        "status": "ok",
        "starred": uri in starred,
    }

@app.get("/api/instances/{uri:path}")
async def get_instance(uri: str):
    if uri == "undefined":
        raise HTTPException(
            400,
            "Invalid instance URI",
        )

    uri_ref = _sparql_iri(
        uri,
        "instance URI",
    )

    rows = await store.query(f"""
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?type ?prop ?value WHERE {{
            {uri_ref} a ?type .
            OPTIONAL {{ {uri_ref} ?prop ?value . FILTER(?prop != rdf:type) }}
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

    # Expand blank-node descriptions recursively. Semantta represents blank
    # nodes as urn:bnid: IRIs, so each batch can reveal another level of nodes.
    bnodes: Dict[str, dict] = {}
    blank_node_uris = {
        value
        for values in props.values()
        for value in values
        if value.startswith("urn:bnid:")
    }
    pending_bnodes = set(blank_node_uris)
    visited_bnodes: Set[str] = set()

    while pending_bnodes:
        current_batch = sorted(pending_bnodes - visited_bnodes)
        if not current_batch:
            break

        visited_bnodes.update(current_batch)
        next_bnodes: Set[str] = set()

        for offset in range(0, len(current_batch), 250):
            batch = current_batch[offset:offset + 250]
            values = " ".join(
                _sparql_iri(bnode_uri, "blank-node URI")
                for bnode_uri in batch
            )
            bnode_rows = await store.query(f"""
                PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                SELECT ?bnode ?type ?prop ?value WHERE {{
                    VALUES ?bnode {{ {values} }}
                    OPTIONAL {{ ?bnode a ?type . }}
                    OPTIONAL {{ ?bnode ?prop ?value . FILTER(?prop != rdf:type) }}
                }}
            """)

            for row in bnode_rows:
                bnode_uri = row["bnode"]
                if bnode_uri not in bnodes:
                    bnodes[bnode_uri] = {
                        "types": [],
                        "properties": {},
                        "label": None,
                    }

                type_uri = row.get("type")
                if type_uri and type_uri not in bnodes[bnode_uri]["types"]:
                    bnodes[bnode_uri]["types"].append(type_uri)

                predicate = row.get("prop")
                value = row.get("value")
                if predicate and value:
                    bnodes[bnode_uri]["properties"].setdefault(
                        predicate, []
                    ).append(value)

                    if (
                        value.startswith("urn:bnid:")
                        and value not in visited_bnodes
                    ):
                        next_bnodes.add(value)

        pending_bnodes = next_bnodes

    for bnode in bnodes.values():
        bnode["types"].sort()
        for predicate, values in bnode["properties"].items():
            bnode["properties"][predicate] = sorted(set(values))

        label_values = bnode["properties"].get(str(RDFS.label), [])
        if label_values:
            bnode["label"] = label_values[0]

    # Identify typed resource values without relying on the frontend's
    # paginated instance list.
    lookup_subjects = sorted({uri, *bnodes.keys()})
    linked_instance_uris_set: Set[str] = set()

    for offset in range(0, len(lookup_subjects), 250):
        subjects = lookup_subjects[offset:offset + 250]
        subject_values = " ".join(
            _sparql_iri(subject, "instance URI")
            for subject in subjects
        )
        linked_rows = await store.query(f"""
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT DISTINCT ?value WHERE {{
                VALUES ?source {{ {subject_values} }}
                ?source ?property ?value .
                FILTER(?property != rdf:type && isIRI(?value))
                ?value a ?valueType .
            }}
        """)

        linked_instance_uris_set.update(
            row["value"]
            for row in linked_rows
            if row.get("value")
            and is_valid_uri(row["value"])
            and not row["value"].startswith("urn:bnid:")
        )

    linked_instance_uris = sorted(linked_instance_uris_set)

    nested_bnode_uris = {
        value
        for bnode in bnodes.values()
        for values in bnode["properties"].values()
        for value in values
        if value.startswith("urn:bnid:")
    }
    label_uris = sorted({
        uri,
        *linked_instance_uris,
        *bnodes.keys(),
        *nested_bnode_uris,
    })

    value_labels: Dict[str, str] = {}
    for offset in range(0, len(label_uris), 250):
        value_labels.update(
            await store.get_instance_labels(
                label_uris[offset:offset + 250]
            )
        )

    for bnode_uri, bnode in bnodes.items():
        preferred_label = value_labels.get(bnode_uri)
        if preferred_label:
            bnode["label"] = preferred_label

    term_uris = set(types) | set(props)

    for bnode in bnodes.values():
        term_uris.update(bnode['types'])
        term_uris.update(bnode['properties'].keys())

    term_labels = await _resolve_display_labels(sorted(term_uris))

    return {
        "uri": uri,
        "types": types,
        "properties": props,
        "bnodes": bnodes,
        "label": value_labels.get(uri),
        "linked_instance_uris": linked_instance_uris,
        "value_labels": value_labels,
        'term_labels': term_labels,
    }

@app.put("/api/instances/{uri:path}")
async def update_instance(uri: str, data: dict):
    uri_ref = _sparql_iri(
        uri,
        "instance URI",
    )

    class_uris = data.get("class_uris", [])

    if not isinstance(class_uris, list):
        raise HTTPException(
            400,
            "class_uris must be a list",
        )

    class_uris = [
        cls
        for cls in class_uris
        if cls
    ]

    if not class_uris:
        raise HTTPException(
            400,
            "At least one valid class URI is required",
        )

    for cls in class_uris:
        _sparql_iri(
            cls,
            "class URI",
        )

    await check_disjoint_classes(
        class_uris
    )

    properties = data.get(
        "properties",
        {},
    )

    if not isinstance(properties, dict):
        raise HTTPException(
            400,
            "properties must be an object",
        )

    await _validate_metadata_profile_membership(
        class_uris,
        properties,
    )

    editable_property_uris = data.get(
        "editable_property_uris",
        list(properties.keys()),
    )
    if not isinstance(editable_property_uris, list) or any(
        not isinstance(prop, str) for prop in editable_property_uris
    ):
        raise HTTPException(
            400,
            "editable_property_uris must be a list of property URIs",
        )

    editable_property_uris = sorted(set(editable_property_uris))
    for prop in editable_property_uris:
        _sparql_iri(prop, "editable property URI")

    active_property_uris = set(
        await shacl.get_active_properties()
    )
    inactive_editable_properties = [
        prop
        for prop in editable_property_uris
        if prop not in active_property_uris
    ]
    if inactive_editable_properties:
        raise HTTPException(
            400,
            "Only active Application Profile properties can be edited: "
            + ", ".join(inactive_editable_properties),
        )

    if not set(properties).issubset(set(editable_property_uris)):
        raise HTTPException(
            400,
            "Submitted values include properties not present in the edit form",
        )

    # Validate the complete replacement before
    # modifying persistent RDF data.
    await shacl.validate_instance(
        class_uris,
        properties,
    )

    # Construct the complete replacement RDF before
    # modifying persistent RDF data.
    triples = "\n".join(
        f"{uri_ref} a {_sparql_iri(c, 'class URI')} ."
        for c in class_uris
    )

    for pred, vals in properties.items():
        pred_ref = _sparql_iri(
            pred,
            "property URI",
        )

        if not isinstance(vals, list):
            vals = [vals]

        datatype_uri = await shacl.get_property_datatype(pred)

        for val in vals:
            if datatype_uri is not None:
                literal = _metadata_literal(
                    val,
                    pred,
                    datatype_uri,
                )
                triples += (
                    f"\n{uri_ref} {pred_ref} {literal.n3()} ."
                )
            elif _is_iri_value(val):
                value_ref = _sparql_iri(
                    val,
                    "value URI",
                )
                triples += (
                    f"\n{uri_ref} {pred_ref} {value_ref} ."
                )
            else:
                literal = Literal(str(val))
                triples += (
                    f"\n{uri_ref} {pred_ref} {literal.n3()} ."
                )

    # Prepare the in-memory representation before touching
    # persistent storage.
    updated_graph = None

    if uri in state["created_instances"]:
        updated_graph = Graph()
        updated_graph.parse(
            data=triples,
            format="turtle",
        )

    # Replace the instance in one SPARQL Update request.
    update_operations = [
        f"DELETE WHERE {{ {uri_ref} <{RDF.type}> ?oldType }}"
    ]

    for pred in editable_property_uris:
        pred_ref = _sparql_iri(pred, "editable property URI")
        update_operations.append(
            f"DELETE WHERE {{ {uri_ref} {pred_ref} ?oldValue }}"
        )

    update_operations.append(
        f"INSERT DATA {{ {triples} }}"
    )

    # Fuseki executes the update request transactionally on TDB2.
    await store.update(";\n".join(update_operations))

    # Update local state only after persistent storage
    # has been successfully replaced.
    if updated_graph is not None:
        subject_uri = URIRef(uri)
        editable_property_set = set(editable_property_uris)

        for triple in list(
            state["created_instances_graph"].triples(
                (subject_uri, None, None)
            )
        ):
            predicate_uri = str(triple[1])
            if triple[1] == RDF.type or predicate_uri in editable_property_set:
                state["created_instances_graph"].remove(triple)

        for triple in updated_graph:
            state["created_instances_graph"].add(triple)

    invalidate_profile()

    return {"status": "ok"}

@app.delete("/api/instances/{uri:path}")
async def delete_instance(uri: str):
    uri_ref = _sparql_iri(
        uri,
        "instance URI",
    )
    
    await store.update(f"DELETE WHERE {{ {uri_ref} ?p ?o }}")

    invalidate_instance_count()

    was_created = (
        uri in state["created_instances"]
    )

    state["created_instances"].discard(uri)

    if was_created:
        save_created_instances()

    subject_uri = URIRef(uri)

    for triple in list(
        state["created_instances_graph"].triples(
            (subject_uri, None, None)
        )
    ):
        state["created_instances_graph"].remove(
            triple
        )
    
    invalidate_profile()
    return {"status": "ok"}

@app.get("/api/metadata/integration-status")
async def get_metadata_integration_status():
    """Calculate metadata integration status on demand."""
    metadata_files = state["metadata_files"]

    if not metadata_files:
        return {"statuses": {}}

    known_individual_uris = sorted({
        entity["uri"]
        for ontology in state["ontologies"]
        for entity in ontology.get("entities", [])
        if (
            entity.get("type") == "individual"
            and isinstance(entity.get("uri"), str)
            and is_valid_uri(entity["uri"])
        )
    })

    # Cached vocabulary extraction depends on which ontology
    # individuals are currently available.
    individual_signature = tuple(
        known_individual_uris
    )

    stats_by_graph = {}
    graphs_to_extract = set()

    for metadata_file in metadata_files:
        graph_uri = metadata_file.get("graph_uri")

        if not graph_uri:
            continue

        stats = await get_cached_metadata_graph_stats(
            graph_uri
        )
        stats_by_graph[graph_uri] = stats

        cached_entities = stats.get(
            "vocabulary_entities"
        )

        if (
            not isinstance(cached_entities, dict)
            or stats.get(
                "vocabulary_individuals_signature"
            ) != individual_signature
        ):
            graphs_to_extract.add(graph_uri)

    # Extract all uncached file summaries in a single query.
    if graphs_to_extract:
        graphs = sorted(graphs_to_extract)

        extracted = {
            graph_uri: {
                "class": set(),
                "property": set(),
                "datatype": set(),
                "individual": set(),
            }
            for graph_uri in graphs
        }

        rows = await store.query(
            _metadata_vocabulary_query(
                graphs,
                known_individual_uris,
                include_graph=True,
            )
        )

        for row in rows:
            graph_uri = str(
                row.get("graph", "")
            )
            term_uri = str(
                row.get("term", "")
            )
            role = row.get("role", "")

            if (
                graph_uri in extracted
                and role in extracted[graph_uri]
                and is_valid_uri(term_uri)
            ):
                extracted[graph_uri][role].add(
                    term_uri
                )

        # Reuse the existing per-graph statistics cache.
        # No separate cache or invalidation mechanism is needed.
        for graph_uri, entities in extracted.items():
            stats_by_graph[graph_uri][
                "vocabulary_entities"
            ] = {
                role: sorted(uris)
                for role, uris in entities.items()
            }
            stats_by_graph[graph_uri][
                "vocabulary_individuals_signature"
            ] = individual_signature

    # Read the current profile once per status request.
    active_rows = await store.query(f"""
        PREFIX sh: <{SH}>

        SELECT DISTINCT ?uri ?role WHERE {{
            GRAPH <{SHAPES_GRAPH}> {{
                {{
                    ?shape a sh:NodeShape ;
                           sh:targetClass ?uri .
                    BIND("class" AS ?role)
                }}
                UNION
                {{
                    ?shape sh:path ?uri .
                    BIND("property" AS ?role)
                }}
                UNION
                {{
                    ?shape a sh:NodeShape ;
                           sh:targetNode ?uri .
                    FILTER(
                        STRSTARTS(
                            STR(?shape),
                            "urn:shape:datatype:"
                        )
                    )
                    BIND("datatype" AS ?role)
                }}
                UNION
                {{
                    ?shape a sh:NodeShape ;
                           sh:targetNode ?uri .
                    FILTER(
                        STRSTARTS(
                            STR(?shape),
                            "urn:shape:individual:"
                        )
                    )
                    BIND("individual" AS ?role)
                }}
            }}

            FILTER(isIRI(?uri))
        }}
    """)

    active_entities = {
        role: set()
        for role in (
            "class",
            "property",
            "datatype",
            "individual",
        )
    }

    for row in active_rows:
        role = row.get("role")
        uri = row.get("uri")

        if (
            role in active_entities
            and isinstance(uri, str)
            and is_valid_uri(uri)
        ):
            active_entities[role].add(uri)

    statuses = {}

    for metadata_file in metadata_files:
        filename = metadata_file["filename"]
        graph_uri = metadata_file.get("graph_uri")

        stats = stats_by_graph.get(
            graph_uri,
            {},
        )

        required_entities = stats.get(
            "vocabulary_entities",
            {},
        )

        statuses[filename] = (
            _summarize_metadata_integration_status(
                required_entities,
                active_entities,
            )
        )

    return {"statuses": statuses}

@app.post("/api/metadata/file/{filename}/integrate-vocab")
async def integrate_file_vocab(filename: str):
    metadata_file = next(
        (
            item
            for item in state["metadata_files"]
            if item["filename"] == filename
        ),
        None,
    )

    if not metadata_file:
        raise HTTPException(
            404,
            "Metadata file not found",
        )

    try:
        entities = await shacl.integrate_metadata_graphs(
            [metadata_file["graph_uri"]],
            source=filename,
        )
    except Exception:
        logger.exception(
            "Vocabulary integration failed for %s",
            filename,
        )
        invalidate_profile()
        raise

    integrated_uris = set().union(
        *entities.values()
    )

    return {
        "status": "ok",
        "entities_integrated": len(integrated_uris),
    }

@app.get("/api/metadata/raw/{filename}")
async def get_raw_metadata(filename: str):
    requested_filename = _require_safe_path_component(
        filename,
        "filename",
    )

    # Only serve a metadata file registered by Semantta.
    metadata_file = next(
        (
            item
            for item in state["metadata_files"]
            if item.get("filename") == requested_filename
        ),
        None,
    )

    if metadata_file is None:
        raise HTTPException(
            404,
            "Metadata file not found",
        )

    # Construct the path from the registered filename, not the request.
    managed_filename = _require_safe_path_component(
        metadata_file["filename"],
        "filename",
    )

    filepath = _path_within_directory(
        METADATA_DIR,
        managed_filename,
    )

    if not filepath.is_file():
        raise HTTPException(
            404,
            "Metadata file not found",
        )

    return FileResponse(filepath)

@app.delete("/api/metadata/{filename}")
async def delete_metadata(
    filename: str,
):
    filename = _require_safe_path_component(
        filename,
        "filename",
    )

    mf = next(
        (
            f
            for f in state["metadata_files"]
            if f["filename"] == filename
        ),
        None,
    )

    if not mf:
        raise HTTPException(
            404,
            "Metadata file not found",
        )

    # Use the filename from the registered metadata record.
    filename = _require_safe_path_component(
        mf["filename"],
        "filename",
    )

    filepath = _path_within_directory(
        METADATA_DIR,
        filename,
    )
    meta_path = _path_within_directory(
        METADATA_DIR,
        f"{filename}.meta.json",
    )

    # Resolve and validate paths before changing graph/state data.
    state["metadata_files"].remove(mf)

    await store.update(
        f"DROP GRAPH <{mf['graph_uri']}>"
    )

    invalidate_metadata_graph_stats(
        mf["graph_uri"]
    )

    if filepath.is_file():
        filepath.unlink()

    if meta_path.is_file():
        meta_path.unlink()

    await rebuild_default_data_graph()
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
        rows = await store.query(f"""
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
        domain_rows = await store.query(f"""
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
        rows = await store.query(f"""
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

        prop_shape_rows = await store.query(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            SELECT ?propShape WHERE {{
                GRAPH <{SHAPES_GRAPH}> {{ <{class_shape_uri}> sh:property ?propShape . }}
            }}
        """)
        if prop_shape_rows:
            prop_shape_uris = [r["propShape"] for r in prop_shape_rows]
            values = " ".join(f"<{u}>" for u in prop_shape_uris)
            prop_uri_rows = await store.query(f"""
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
        rows = await store.query(f"""
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
        logger.exception(
            "Profile generation failed",
        )
        raise HTTPException(
            500,
            detail="Profile generation failed.",
        ) from e

@app.post("/api/profile/update-order")
async def update_profile_order(data: dict):
    items = data.get("items", [])
    for item in items:
        uri = item["uri"]
        order_val = item["order"]
        shape_uri = shape_uri_for_entity(uri, "property", state["prefix_map"])

        await store.update(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            DELETE {{ GRAPH <{SHAPES_GRAPH}> {{ <{shape_uri}> sh:order ?old }} }}
            WHERE  {{ GRAPH <{SHAPES_GRAPH}> {{ <{shape_uri}> sh:order ?old }} }}
        """)

        ord_triple = _format_constraint_value(str(SH.order), order_val)
        await store.update(f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            INSERT DATA {{ GRAPH <{SHAPES_GRAPH}> {{ <{shape_uri}> sh:order {ord_triple} }} }}
        """)

    invalidate_profile()
    return {"status": "ok"}

@app.post("/api/instances/exists")
async def check_instances_exist(data: dict):
    uris = data.get("uris", [])
    if not uris: return {"existing": []}
    safe = [
        _sparql_iri(
            uri,
            "instance URI",
        )
        for uri in uris
    ]
    if not safe: return {"existing": []}
    values = " ".join(safe)
    query = f"SELECT ?uri WHERE {{ VALUES ?uri {{ {values} }} {{ ?uri ?p ?o . }} UNION {{ ?s ?p ?uri . }} }}"
    rows = await store.query(query)
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
    settings = load_settings()

    if "site_title" in data:
        title = data["site_title"].strip()
        if title:
            state["site_title"] = title
            changed = True

    if "base_iri" in data:
        state["base_iri"] = data["base_iri"].strip()
        changed = True

    if changed:
        settings.update({
            "site_title": state["site_title"],
            "base_iri": state["base_iri"],
            "applied_base_iri": state.get(
                "applied_base_iri",
                settings.get("applied_base_iri", settings.get("base_iri", "")),
            ),
        })
        save_settings(settings)

    return {"status": "ok"}

@app.post("/api/settings/apply-base-iri")
async def apply_base_iri(data: dict):
    requested_base_iri = data.get("base_iri")

    if not isinstance(requested_base_iri, str):
        raise HTTPException(400, "Base IRI is required.")

    base_iri = requested_base_iri.strip()

    if not base_iri:
        raise HTTPException(400, "Base IRI is not set.")

    if not base_iri.endswith("/"):
        base_iri += "/"

    _sparql_iri(base_iri, "Base IRI")

    applied_base_iri = (
        state.get("applied_base_iri")
        or state.get("base_iri", "")
    ).strip()

    mapping = _build_base_iri_mapping(
        state["created_instances"],
        applied_base_iri,
        base_iri,
    )

    for old_uri, new_uri in mapping.items():
        _sparql_iri(old_uri, "Old instance URI")
        _sparql_iri(new_uri, "New instance URI")

    if mapping:
        target_values = " ".join(
            _sparql_iri(uri, "New instance URI")
            for uri in mapping.values()
        )

        collisions = await store.query(f"""
            SELECT DISTINCT ?uri WHERE {{
                VALUES ?uri {{ {target_values} }}
                {{
                    ?uri ?p ?o .
                }}
                UNION
                {{
                    GRAPH ?g {{ ?uri ?p ?o . }}
                }}
            }}
        """)

        if collisions:
            raise HTTPException(
                409,
                "Cannot apply Base IRI because a target URI already exists: "
                f"{collisions[0]['uri']}",
            )

        graph_uris = [
            item["graph_uri"]
            for item in state["metadata_files"]
            if item.get("graph_uri")
        ]

        update = _build_uri_rewrite_update(
            mapping,
            graph_uris,
        )

        # Persistent RDF changes must succeed before state is changed.
        await store.update(update)

        rdf_mapping = {
            URIRef(old): URIRef(new)
            for old, new in mapping.items()
        }

        rewrite_uris_in_graph(
            state["created_instances_graph"],
            rdf_mapping,
        )

        state["created_instances"] = {
            mapping.get(uri, uri)
            for uri in state["created_instances"]
        }

        state["starred_instance_uris"] = {
            mapping.get(uri, uri)
            for uri in state["starred_instance_uris"]
        }

        state["non_integrated_uris"] = {
            mapping.get(uri, uri)
            for uri in state["non_integrated_uris"]
        }

        state["metadata_only_sources"] = {
            mapping.get(uri, uri): source
            for uri, source in state["metadata_only_sources"].items()
        }

        save_created_instances()

        atomic_write_json(
            STARS_FILE,
            sorted(
                uri
                for uri in state["starred_instance_uris"]
                if uri is not None
            ),
        )

    # Save the requested Base IRI even when no instances need rewriting.
    state["base_iri"] = base_iri
    state["applied_base_iri"] = base_iri

    settings = load_settings()
    settings["base_iri"] = base_iri
    settings["applied_base_iri"] = base_iri
    save_settings(settings)

    if mapping:
        clear_metadata_graph_stats()
        invalidate_instance_count()
        invalidate_profile()
        await rebuild_used_uris()

    return {
        "status": "ok",
        "updated": len(mapping),
        "base_iri": base_iri,
    }

@app.get("/api/ontology/raw/{filename}")
async def get_raw_ontology(filename: str):
    requested_filename = _require_safe_path_component(
        filename,
        "filename",
    )

    # Only serve an ontology registered by Semantta.
    ontology = next(
        (
            item
            for item in state["ontologies"]
            if item.get("filename") == requested_filename
        ),
        None,
    )

    if ontology is None:
        raise HTTPException(
            404,
            "Ontology file not found",
        )

    # Construct the path from the registered filename, not the request.
    managed_filename = _require_safe_path_component(
        ontology["filename"],
        "filename",
    )

    filepath = _path_within_directory(
        ONTOLOGY_DIR,
        managed_filename,
    )

    if not filepath.is_file():
        raise HTTPException(
            404,
            "Ontology file not found",
        )

    return FileResponse(filepath)

@app.post("/api/admin/cache/clear")
async def clear_all_caches():
    """Clear persistent cache files and invalidate derived in-memory caches."""
    try:
        if CACHE_DIR.exists():
            for entry in CACHE_DIR.iterdir():
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()

        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        clear_metadata_graph_stats()
        invalidate_instance_count()
        invalidate_everything()

        logger.info("Application caches cleared successfully")

        return {
            "status": "ok",
            "message": (
                "Cache files cleared and derived ontology indexes rebuilt."
            ),
        }

    except Exception as exc:
        logger.exception("Failed to clear application caches")
        raise HTTPException(
            status_code=500,
            detail="Failed to clear caches.",
        ) from exc

@app.post("/api/admin/purge")
async def purge_all_data():
    try: await store.update("CLEAR ALL")
    except Exception:
        try:
            await store.update("CLEAR DEFAULT")
            await store.update("CLEAR GRAPH <urn:profile:shapes>")
            await store.update("CLEAR GRAPH <urn:profile:constraints>")
        except Exception: raise HTTPException(500, "Could not clear Fuseki store.")

    for directory in [ONTOLOGY_DIR, METADATA_DIR, CACHE_DIR]:
        if os.path.exists(directory):
            shutil.rmtree(directory)
            os.makedirs(directory, exist_ok=True)

    state["ontologies"].clear()
    state["combined_onto_graph"] = Graph()
    state["prefix_map"].clear()
    state["metadata_files"].clear()
    clear_metadata_graph_stats()
    state["instances"].clear()
    state["created_instances"].clear()
    state["created_instances_graph"] = Graph()
    state["non_integrated_uris"].clear()
    state["metadata_only_sources"].clear()
    state["all_ontology_namespaces"].clear()
    invalidate_instance_count()
    invalidate_everything()
    if os.path.exists(PREFERENCES_FILE): os.remove(PREFERENCES_FILE)
    if os.path.exists(SETTINGS_FILE): os.remove(SETTINGS_FILE)
    if os.path.exists(CREATED_INSTANCES_FILE): os.remove(CREATED_INSTANCES_FILE)
    state["display_format"] = "iri"
    state["site_title"] = "Semantta"
    state["base_iri"] = ""
    await rebuild_used_uris()
    add_default_prefixes()
    refresh_display_prefix_map()
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
        contents = await _read_upload_with_limit(
            file,
            MAX_PLUGIN_UPLOAD_BYTES,
        )
        with zipfile.ZipFile(io.BytesIO(contents)) as zf:
            _safe_extract_zip(
                zf,
                Path(tmp_dir),
            )
        entries = os.listdir(tmp_dir)
        if len(entries) != 1:
            raise HTTPException(
                400,
                "Invalid plugin structure: must contain a single folder with plugin.json",
            )
        plugin_folder = _require_safe_path_component(
            entries[0],
            "plugin folder name",
        )
        src = _path_within_directory(
            Path(tmp_dir),
            plugin_folder,
        )
        if not src.is_dir():
            raise HTTPException(
                400,
                "Invalid plugin structure: must contain a single folder with plugin.json",
            )
        plugin_manifest = _path_within_directory(src, "plugin.json")
        if not plugin_manifest.is_file():
            raise HTTPException(400, "Missing plugin.json")
        dest = _path_within_directory(
            PLUGINS_DIR,
            plugin_folder,
        )
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
    name = _require_safe_path_component(data.get("name"), "plugin name")
    enabled = data.get("enabled", True)
    config = load_plugins_config()
    if name not in config: raise HTTPException(404, "Plugin not found")
    config[name]["enabled"] = enabled
    save_plugins_config(config)
    return {"status": "ok", "message": f"Plugin {'enabled' if enabled else 'disabled'}. Restart server to apply changes."}

@app.delete("/api/plugins/{name}")
async def delete_plugin(name: str):
    name = _require_safe_path_component(name, "plugin name")
    config = load_plugins_config()
    if name not in config: raise HTTPException(404, "Plugin not found")
    plugin_path = _path_within_directory(
        PLUGINS_DIR,
        name,
    )
    if plugin_path.is_dir():
        shutil.rmtree(plugin_path)
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
        contents = await _read_upload_with_limit(
            file,
            MAX_THEME_UPLOAD_BYTES,
        )
        with zipfile.ZipFile(io.BytesIO(contents)) as zf:
            _safe_extract_zip(
                zf,
                Path(tmp_dir),
            )
        entries = os.listdir(tmp_dir)
        if len(entries) != 1:
            raise HTTPException(
                400,
                "Invalid theme structure: must contain a single folder with theme.json",
            )
        theme_folder = _require_safe_path_component(
            entries[0],
            "theme folder name",
        )
        src = _path_within_directory(
            Path(tmp_dir),
            theme_folder,
        )
        if not src.is_dir():
            raise HTTPException(
                400,
                "Invalid theme structure: must contain a single folder with theme.json",
            )
        theme_manifest = _path_within_directory(src, "theme.json")
        if not theme_manifest.is_file():
            raise HTTPException(400, "Missing theme.json")
        dest = _path_within_directory(
            THEMES_DIR,
            theme_folder,
        )
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
    name = _require_safe_path_component(data.get("name"), "theme name")
    enabled = data.get("enabled", True)
    if name == "default": raise HTTPException(400, "The default theme cannot be disabled.")
    config = load_themes_config()
    if name not in config: raise HTTPException(404, "Theme not found")
    config[name]["enabled"] = enabled
    save_themes_config(config)
    return {"status": "ok", "message": f"Theme {'enabled' if enabled else 'disabled'}. Restart frontend to apply changes."}

@app.delete("/api/themes/{name}")
async def delete_theme(name: str):
    name = _require_safe_path_component(name, "theme name")
    if name == "default": raise HTTPException(400, "The default theme cannot be deleted.")
    config = load_themes_config()
    if name not in config: raise HTTPException(404, "Theme not found")
    theme_path = _path_within_directory(
        THEMES_DIR,
        name,
    )
    if theme_path.is_dir():
        shutil.rmtree(theme_path)
    del config[name]
    save_themes_config(config)
    return {"status": "ok"}

@app.post("/api/themes/set-active")
async def set_active_theme_endpoint(data: dict):
    theme = data.get("theme", "default")

    if not isinstance(theme, str):
        raise HTTPException(
            400,
            "Theme name must be a string.",
        )

    if theme == "default":
        pass
    else:
        theme = _require_safe_path_component(
            theme,
            "theme name",
        )

        theme_path = _path_within_directory(
            THEMES_DIR,
            theme,
        )

        if not theme_path.is_dir():
            raise HTTPException(
                404,
                "Theme not found",
            )

    set_active_theme(theme)

    settings = load_settings()
    settings["active_theme"] = theme
    save_settings(settings)

    return {
        "status": "ok",
        "theme": theme,
        "requires_frontend_restart": True,
        "requires_frontend_rebuild": theme != "default",
        "message": (
            f"Active theme set to '{theme}'. "
            "The frontend must be rebuilt and restarted to apply the theme."
        ),
    }

@app.get("/api/progress")
async def get_progress():
    return progress