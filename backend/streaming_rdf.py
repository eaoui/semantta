"""
Memory-bounded RDF ingestion helpers.

RDFLib parses RDF through its Store interface. This module uses a
non-retaining Store so parsed triples are forwarded directly to disk
instead of accumulating in a Graph.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

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

            output.write(
                f"{_term_to_ntriples(subject, bnode_map)} "
                f"{_term_to_ntriples(predicate, bnode_map)} "
                f"{_term_to_ntriples(object_, bnode_map)} .\n"
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

    return triple_count