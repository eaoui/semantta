"""
URI helpers for Semantta.
Provides functions to convert ontology entity URIs into consistent,
human-readable SHACL shape URIs.
"""

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from rdflib import Graph, Namespace, URIRef


def prefix_for_uri(entity_uri: str, prefix_map: dict) -> str:
    """
    Find the best prefix for an entity URI from the global prefix map.
    Prefers the longest matching namespace. Falls back to a 6‑character
    MD5 hash if no prefix matches or the prefix contains non‑alphanumeric
    characters.
    """
    # Sort by namespace length descending so longer (more specific) matches win
    for ns_uri in sorted(prefix_map.keys(), key=lambda x: -len(x)):
        if entity_uri.startswith(ns_uri):
            prefix = prefix_map[ns_uri]
            # Ensure the prefix is safe for use in URIs
            if prefix and re.match(r'^[A-Za-z0-9_-]+$', prefix):
                return prefix
    # Fallback: return a short hash of the full URI
    return hashlib.md5(entity_uri.encode()).hexdigest()[:6]


def shape_uri_for_entity(
    entity_uri: str,
    entity_type: str,
    prefix_map: dict,
) -> str:
    """Build a stable, collision-resistant SHACL shape URI."""
    digest = hashlib.sha256(
        entity_uri.encode("utf-8")
    ).hexdigest()

    return f"urn:shape:{entity_type}:{digest}"

_SH = Namespace("http://www.w3.org/ns/shacl#")

_SHAPE_IDENTITY_PREDICATES = {
    "class": _SH.targetClass,
    "property": _SH.path,
    "datatype": _SH.targetNode,
    "individual": _SH.targetNode,
}


def migrate_shape_graph(
    graph: Graph,
) -> tuple[Graph, int, int]:
    """Migrate legacy generated shape URIs without losing constraints."""
    mappings = {}
    target_shapes = {}
    identity_predicates = {}

    for shape in set(graph.subjects()):
        if not isinstance(shape, URIRef):
            continue

        parts = str(shape).split(":", 3)
        if (
            len(parts) != 4
            or parts[:2] != ["urn", "shape"]
        ):
            continue

        entity_type = parts[2]
        identity_predicate = (
            _SHAPE_IDENTITY_PREDICATES.get(entity_type)
        )

        if identity_predicate is None:
            continue

        targets = sorted(
            set(graph.objects(shape, identity_predicate)),
            key=str,
        )

        # Preserve shapes whose identities cannot safely be inferred.
        if (
            not targets
            or not all(
                isinstance(target, URIRef)
                for target in targets
            )
        ):
            continue

        per_target = {
            target: URIRef(
                shape_uri_for_entity(
                    str(target),
                    entity_type,
                    {},
                )
            )
            for target in targets
        }

        new_shapes = list(
            dict.fromkeys(per_target.values())
        )

        # Already migrated: leave the shape untouched.
        if len(targets) == 1 and new_shapes[0] == shape:
            continue

        mappings[shape] = new_shapes
        target_shapes[shape] = per_target
        identity_predicates[shape] = identity_predicate

    if not mappings:
        return graph, 0, 0

    migrated = Graph()

    for prefix, namespace in graph.namespaces():
        migrated.bind(prefix, namespace)

    for subject, predicate, obj in graph:
        if subject in mappings:
            if predicate == identity_predicates[subject]:
                new_subject = target_shapes[subject].get(obj)

                if new_subject is not None:
                    migrated.add(
                        (new_subject, predicate, obj)
                    )

                continue

            new_subjects = mappings[subject]
        else:
            new_subjects = [subject]

        # Rewrite references to old shape identifiers, including
        # sh:property links from class shapes.
        new_objects = mappings.get(obj, [obj])

        for new_subject in new_subjects:
            for new_object in new_objects:
                migrated.add(
                    (new_subject, predicate, new_object)
                )

    ambiguous_count = sum(
        1
        for shapes in mappings.values()
        if len(shapes) > 1
    )

    return migrated, len(mappings), ambiguous_count

def property_shape_uri(prop_uri: str, prefix_map: dict) -> str:
    """
    Convenience wrapper that builds a SHACL shape URI for a property.
    """
    return shape_uri_for_entity(prop_uri, "property", prefix_map)

def atomic_write_json(
    path: str | Path,
    data,
    *,
    indent: int = 2,
) -> None:
    target = Path(path)
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
        text=True,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=indent,
            )
            f.flush()
            os.fsync(f.fileno())

        os.replace(
            temp_name,
            target,
        )
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass

        raise