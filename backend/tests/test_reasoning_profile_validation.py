
import sys
from pathlib import Path
from collections import defaultdict
from unittest.mock import AsyncMock

from typing import cast
from rdf_store import RDFStore

import pytest
from fastapi import HTTPException
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


EX = Namespace("https://example.org/test/")
SH = Namespace("http://www.w3.org/ns/shacl#")


def test_apply_reasoning_infers_superclass_membership():
    graph = Graph()

    graph.add((EX.Book, RDFS.subClassOf, EX.Work))
    graph.add((EX.book1, RDF.type, EX.Book))

    main.apply_reasoning(graph)

    assert (EX.book1, RDF.type, EX.Work) in graph


def test_reasoned_graph_cache_invalidates_when_source_changes(
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "example.ttl"
    cache_dir = tmp_path / "cache"
    owl_file = tmp_path / "owl.ttl"

    # Isolate the cache test from the repository's built-in
    # vocabulary while preserving the production cache workflow.
    owl_file.write_text("", encoding="utf-8")

    monkeypatch.setattr(main, "OWL_FILE", owl_file)
    monkeypatch.setattr(main, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(
        main,
        "reasoned_cache_path",
        lambda filename: cache_dir / f"{filename}.reasoned.ttl",
    )
    monkeypatch.setattr(
        main,
        "reasoned_cache_metadata_path",
        lambda filename: cache_dir / f"{filename}.reasoned.meta.json",
    )

    source_text = """
        @prefix ex: <https://example.org/test/> .
        @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

        ex:Book rdfs:subClassOf ex:Work .
        ex:book1 rdf:type ex:Book .
    """

    source.write_text(source_text, encoding="utf-8")

    unreasoned, reasoned = main.get_reasoned_graph(
        str(source), "turtle"
    )

    assert (EX.book1, RDF.type, EX.Work) in reasoned
    assert (EX.book1, RDF.type, EX.Work) not in unreasoned

    # Verify the saved cache can be reloaded.
    _, cached = main.get_reasoned_graph(str(source), "turtle")
    assert (EX.book1, RDF.type, EX.Work) in cached

    # A source change must invalidate the previous reasoned graph.
    source.write_text(
        source_text + "\nex:Book rdfs:subClassOf ex:Publication .\n",
        encoding="utf-8",
    )

    _, refreshed = main.get_reasoned_graph(str(source), "turtle")

    assert (EX.book1, RDF.type, EX.Publication) in refreshed


class InMemoryShapeStore:
    """Store adapter for testing the real SHACL validation logic."""

    def __init__(self, shapes):
        self.shapes = shapes
        self.updates = []

    async def load_shapes_graph(self):
        return self.shapes

    async def query(self, sparql):
        if "SELECT DISTINCT ?class" in sparql:
            return [{"class": str(EX.Book)}]

        if "SELECT DISTINCT ?prop" in sparql:
            return [{"prop": str(EX.title)}]

        return []

    async def update(self, sparql):
        self.updates.append(sparql)


def make_required_title_shapes():
    graph = Graph()

    class_shape = URIRef("urn:test:BookShape")
    property_shape = URIRef("urn:test:TitleShape")

    graph.add((class_shape, RDF.type, SH.NodeShape))
    graph.add((class_shape, SH.targetClass, EX.Book))
    graph.add((class_shape, SH.property, property_shape))

    graph.add((property_shape, RDF.type, SH.PropertyShape))
    graph.add((property_shape, SH.path, EX.title))
    graph.add((property_shape, SH.minCount, Literal(1)))
    graph.add((property_shape, SH.datatype, XSD.string))

    return graph


@pytest.mark.asyncio
async def test_real_shacl_validation_blocks_invalid_update_before_write(
    monkeypatch,
):
    store = InMemoryShapeStore(make_required_title_shapes())
    # This test double implements the store operations exercised by this test.
    profile = main.SHACLProfile(cast(RDFStore, store))

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "shacl", profile)
    monkeypatch.setattr(main, "validation_ontology_graph", Graph())
    get_domains_mock = AsyncMock(
        return_value={
            str(EX.title): [str(EX.Book)],
        }
    )
    monkeypatch.setattr(
        main.ap,
        "_get_shacl_domains",
        get_domains_mock,
    )
    monkeypatch.setattr(
        main, "check_disjoint_classes", AsyncMock()
    )
    monkeypatch.setattr(main, "invalidate_profile", lambda: None)

    # A complete, conforming instance must pass actual pySHACL validation.
    assert await profile.validate_instance(
        [str(EX.Book)],
        {str(EX.title): ["A valid title"]},
    ) is True

    # The real SHACL constraint must reject an update that omits title.
    with pytest.raises(HTTPException) as exc_info:
        await main.update_instance(
            str(EX.book1),
            {
                "class_uris": [str(EX.Book)],
                "properties": {},
            },
        )

    assert exc_info.value.status_code == 400
    assert "SHACL validation failed" in exc_info.value.detail
    assert store.updates == []
