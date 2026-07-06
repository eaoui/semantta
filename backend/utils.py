"""
URI helpers for Semantta.
Provides functions to convert ontology entity URIs into consistent,
human-readable SHACL shape URIs.
"""

import hashlib
import re


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


def shape_uri_for_entity(entity_uri: str, entity_type: str, prefix_map: dict) -> str:
    """
    Build a deterministic SHACL shape URI from an entity URI.
    
    Format: ``urn:shape:<entity_type>:<local_part>~<prefix>``
    
    *entity_type* – one of ``"class"``, ``"property"``, ``"datatype"``, or ``"individual"``.
    """
    # Extract the local name from the URI
    local = entity_uri.rstrip('/#').split('/')[-1].split('#')[-1] or "unknown"
    prefix = prefix_for_uri(entity_uri, prefix_map)
    return f"urn:shape:{entity_type}:{local}~{prefix}"

def property_shape_uri(prop_uri: str, prefix_map: dict) -> str:
    """
    Convenience wrapper that builds a SHACL shape URI for a property.
    """
    return shape_uri_for_entity(prop_uri, "property", prefix_map)