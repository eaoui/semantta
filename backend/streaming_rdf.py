"""
Memory-bounded RDF ingestion helpers.

RDFLib parses RDF through its Store interface. This module uses a
non-retaining Store so parsed triples are forwarded directly to disk
instead of accumulating in a Graph.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import hashlib
import json
import os
import sqlite3
import tempfile

from urllib.parse import urlsplit
from uuid import uuid4

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.plugins.stores.memory import Memory


TripleCallback = Callable[[tuple[Any, Any, Any]], None]


class StreamingStore(Memory):
    """
    RDFLib-compatible store that forwards triples to a callback without
    retaining them in the in-memory store.
    """

    def __init__(
        self,
        callback: TripleCallback,
    ) -> None:
        super().__init__()
        self._callback = callback

    def add(
        self,
        triple,
        context,
        quoted: bool = False,
    ) -> None:
        self._callback(triple)

def _literal_to_ntriples(
    term: Literal,
) -> str:
    """
    Serialize an RDF literal using N-Triples lexical escaping.

    Unlike Literal.n3(), this never uses triple-quoted strings.
    """
    lexical = (
        str(term)
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace('"', '\\"')
        .replace("\r", "\\r")
    )

    encoded = f'"{lexical}"'

    if term.language:
        return f"{encoded}@{term.language}"

    if term.datatype:
        return f"{encoded}^^<{term.datatype}>"

    return encoded

def _term_to_ntriples(
    term,
    bnode_map: dict[BNode, URIRef],
) -> str:
    """
    Serialize one RDF term as an N-Triples-compatible term.

    Blank nodes are rewritten to Semantta's existing urn:bnid: form.
    """
    if isinstance(term, BNode):
        if term not in bnode_map:
            bnode_map[term] = URIRef(
                f"urn:bnid:{term}"
            )

        return bnode_map[term].n3()

    if isinstance(term, Literal):
        return _literal_to_ntriples(term)

    return term.n3()

def _blank_node_fingerprints(
    connection: sqlite3.Connection,
    node_uris: set[str],
) -> dict[str, str | None]:
    """Fingerprint complete, acyclic blank-node structures from disk."""
    fingerprints: dict[str, str | None] = {}
    visiting: set[str] = set()

    def fingerprint(node_uri: str) -> str | None:
        if node_uri in fingerprints:
            return fingerprints[node_uri]
        if node_uri in visiting:
            return None

        statements = connection.execute(
            """
            SELECT predicate, object_kind, object_value, datatype, language
            FROM bnode_triples
            WHERE subject = ?
            """,
            (node_uri,),
        ).fetchall()

        # Empty nodes contain no evidence on which to base a safe merge.
        if not statements:
            fingerprints[node_uri] = None
            return None

        visiting.add(node_uri)
        try:
            signature = []

            for predicate, object_kind, object_value, datatype, language in statements:
                if object_kind == "blank-node":
                    child_fingerprint = fingerprint(object_value)
                    if child_fingerprint is None:
                        raise ValueError("Unfingerprintable child blank node")

                    object_signature = ["blank-node", child_fingerprint]

                elif object_kind == "iri":
                    object_signature = ["iri", object_value]

                else:
                    object_signature = [
                        "literal",
                        object_value,
                        datatype,
                        language,
                    ]

                signature.append([predicate, object_signature])

            signature.sort(
                key=lambda item: json.dumps(
                    item,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            encoded = json.dumps(
                signature,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")

            value = hashlib.sha256(encoded).hexdigest()
            fingerprints[node_uri] = value
            return value

        except (ValueError, RecursionError):
            fingerprints[node_uri] = None
            return None

        finally:
            visiting.discard(node_uri)

    for node_uri in node_uris:
        try:
            fingerprint(node_uri)
        except RecursionError:
            fingerprints[node_uri] = None

    return fingerprints

def _blank_node_context_fingerprints(
    connection: sqlite3.Connection,
    structural_fingerprints: dict[str, str | None],
) -> dict[str, str | None]:
    """Fingerprint incoming relationships, anchored to named resources."""
    context_fingerprints: dict[str, str | None] = {}
    visiting: set[str] = set()

    def encode(value: object) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def fingerprint(node_uri: str) -> str | None:
        if node_uri in context_fingerprints:
            return context_fingerprints[node_uri]

        if node_uri in visiting:
            return None

        visiting.add(node_uri)
        try:
            incoming = connection.execute(
                """
                SELECT subject_kind, subject_value, predicate
                FROM bnode_incoming
                WHERE object_value = ?
                """,
                (node_uri,),
            ).fetchall()

            if not incoming:
                context_fingerprints[node_uri] = None
                return None

            signatures = []

            for subject_kind, subject_value, predicate in incoming:
                if subject_kind == "iri":
                    signatures.append(
                        ["iri", subject_value, predicate]
                    )
                    continue

                parent_structure = structural_fingerprints.get(
                    subject_value
                )
                parent_context = fingerprint(subject_value)

                if (
                    parent_structure is None
                    or parent_context is None
                ):
                    context_fingerprints[node_uri] = None
                    return None

                signatures.append(
                    [
                        "blank-node",
                        parent_structure,
                        parent_context,
                        predicate,
                    ]
                )

            signatures.sort(key=encode)
            encoded = encode(signatures).encode("utf-8")

            result = hashlib.sha256(encoded).hexdigest()
            context_fingerprints[node_uri] = result
            return result

        finally:
            visiting.discard(node_uri)

    for node_uri in structural_fingerprints:
        fingerprint(node_uri)

    return context_fingerprints

def _rewrite_blank_node_iris(
    line: str,
    replacements: dict[str, str],
) -> str:
    """Replace generated IRI tokens without touching literal lexical values."""
    if not replacements:
        return line

    output: list[str] = []
    index = 0
    in_literal = False
    escaped = False

    while index < len(line):
        char = line[index]

        if in_literal:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_literal = False
            index += 1
            continue

        if char == '"':
            in_literal = True
            output.append(char)
            index += 1
            continue

        if char == "<":
            end = line.find(">", index + 1)
            if end < 0:
                output.append(line[index:])
                break

            iri = line[index + 1:end]
            preceding = "".join(output[-2:])
            replacement = (
                iri
                if preceding.endswith("^^")
                else replacements.get(iri, iri)
            )
            output.append(f"<{replacement}>")
            index = end + 1
            continue

        output.append(char)
        index += 1

    return "".join(output)

class RelativeIRIWithoutBaseError(ValueError):
    """Raised when relative IRIs have no explicit absolute base."""

def stream_rdf_to_ntriples(
    source_path: str | Path,
    fmt: str,
    target_path: str | Path,
) -> int:
    """
    Parse an RDF document without retaining the complete RDF graph.

    Parsed triples are written incrementally to an N-Triples file.

    Returns the number of triples written.
    """
    source_path = Path(source_path)
    target_path = Path(target_path)

    fallback_host = f"{uuid4().hex}.semantta.invalid"
    fallback_base = f"https://{fallback_host}/"

    if not source_path.is_file():
        raise FileNotFoundError(
            f"RDF source file not found: {source_path}"
        )

    target_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, database_name = tempfile.mkstemp(
        prefix="semantta-bnode-index-",
        suffix=".sqlite",
        dir=target_path.parent,
    )
    os.close(fd)

    database_path = Path(database_name)
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE bnode_triples (
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object_kind TEXT NOT NULL,
            object_value TEXT NOT NULL,
            datatype TEXT NOT NULL,
            language TEXT NOT NULL,
            PRIMARY KEY (
                subject, predicate, object_kind, object_value, datatype, language
            )
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE bnode_incoming (
            object_value TEXT NOT NULL,
            subject_kind TEXT NOT NULL,
            subject_value TEXT NOT NULL,
            predicate TEXT NOT NULL,
            PRIMARY KEY (
                object_value,
                subject_kind,
                subject_value,
                predicate
            )
        )
        """
    )

    triple_count = 0
    bnode_map: dict[BNode, URIRef] = {}

    with target_path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as output:

        def handle_triple(
            triple,
        ) -> None:
            nonlocal triple_count

            subject, predicate, object_ = triple

            def uses_fallback_base(term) -> bool:
                if isinstance(term, URIRef):
                    return urlsplit(str(term)).hostname == fallback_host

                if isinstance(term, Literal) and term.datatype:
                    return (
                        urlsplit(str(term.datatype)).hostname
                        == fallback_host
                    )

                return False


            if any(
                uses_fallback_base(term)
                for term in triple
            ):
                raise RelativeIRIWithoutBaseError(
                    "The metadata contains relative IRIs without "
                    "an explicit absolute base URI. Add an absolute "
                    "base declaration or replace those IRIs with "
                    "absolute IRIs. No metadata was imported."
                )

            subject_nt = _term_to_ntriples(subject, bnode_map)
            predicate_nt = _term_to_ntriples(predicate, bnode_map)
            object_nt = _term_to_ntriples(object_, bnode_map)

            output.write(
                f"{subject_nt} {predicate_nt} {object_nt} .\n"
            )

            if isinstance(subject, BNode):
                subject_uri = str(bnode_map[subject])

                if isinstance(object_, BNode):
                    object_kind = "blank-node"
                    object_value = str(bnode_map[object_])
                    datatype = ""
                    language = ""

                elif isinstance(object_, URIRef):
                    object_kind = "iri"
                    object_value = str(object_)
                    datatype = ""
                    language = ""

                elif isinstance(object_, Literal):
                    object_kind = "literal"
                    object_value = str(object_)
                    datatype = str(object_.datatype or "")
                    language = object_.language or ""

                else:
                    object_kind = "iri"
                    object_value = str(object_)
                    datatype = ""
                    language = ""

                connection.execute(
                    """
                    INSERT OR IGNORE INTO bnode_triples
                        (subject, predicate, object_kind, object_value, datatype, language)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        subject_uri,
                        str(predicate),
                        object_kind,
                        object_value,
                        datatype,
                        language,
                    ),
                )

            if isinstance(object_, BNode):
                object_uri = str(bnode_map[object_])

                if isinstance(subject, URIRef):
                    subject_kind = "iri"
                    subject_value = str(subject)
                elif isinstance(subject, BNode):
                    subject_kind = "blank-node"
                    subject_value = str(bnode_map[subject])
                else:
                    subject_kind = None
                    subject_value = None

                if subject_kind is not None:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO bnode_incoming (
                            object_value,
                            subject_kind,
                            subject_value,
                            predicate
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            object_uri,
                            subject_kind,
                            subject_value,
                            str(predicate),
                        ),
                    )

            triple_count += 1

        graph = Graph(
            store=StreamingStore(
                handle_triple,
            ),
        )

        graph.parse(
            source=str(source_path),
            format=fmt,
            publicID=fallback_base,
        )

    connection.commit()

    try:
        node_uris = {
            str(uri)
            for uri in bnode_map.values()
        }

        structural_fingerprints = _blank_node_fingerprints(
            connection,
            node_uris,
        )

        context_fingerprints = _blank_node_context_fingerprints(
            connection,
            structural_fingerprints,
        )

        replacements: dict[str, str] = {}

        for node_uri, structural_fingerprint in (
            structural_fingerprints.items()
        ):
            context_fingerprint = context_fingerprints.get(node_uri)

            # Do not merge nodes without reliable evidence.
            if (
                structural_fingerprint is None
                or context_fingerprint is None
            ):
                continue

            identity = hashlib.sha256(
                json.dumps(
                    [
                        structural_fingerprint,
                        context_fingerprint,
                    ],
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()

            replacements[node_uri] = f"urn:bnid:{identity}"

        if replacements:
            rewritten_path = target_path.with_suffix(
                target_path.suffix + ".rewritten"
            )

            with target_path.open("r", encoding="utf-8") as source, rewritten_path.open(
                "w", encoding="utf-8", newline="\n"
            ) as output:
                for line in source:
                    output.write(_rewrite_blank_node_iris(line, replacements))

            os.replace(rewritten_path, target_path)
    finally:
        connection.close()
        database_path.unlink(missing_ok=True)

    return triple_count