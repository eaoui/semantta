"""
Memory-bounded RDF ingestion helpers.

RDFLib parses RDF through its Store interface. This module uses a
non-retaining Store so parsed triples are forwarded directly to disk
instead of accumulating in a Graph.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from rdflib import BNode, Graph, URIRef
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

    return term.n3()


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
        )

    return triple_count