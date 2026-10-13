import sys
from pathlib import Path
from unittest.mock import AsyncMock
from collections.abc import Iterable
from typing import cast
import json

import pytest
from rdflib import Dataset, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS
from rdflib.query import Result

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


EX = Namespace("http://example.org/")
EX2 = Namespace("https://example.net/")

GRAPH_ONE = main.metadata_graph_uri("catalog.ttl")
GRAPH_TWO = main.metadata_graph_uri("inventory.ttl")


def test_metadata_vocabulary_query_uses_uri_and_role():
    dataset = Dataset()

    catalog = dataset.graph(URIRef(GRAPH_ONE))
    inventory = dataset.graph(URIRef(GRAPH_TWO))

    # Ordinary records and object URIs are not vocabulary entities
    # solely because they occur in metadata triples.
    catalog.add((EX.book1, RDF.type, EX.Book))
    catalog.add((EX.book1, EX.title, Literal("A book")))
    catalog.add((EX.book1, EX.publisher, EX.Acme))

    catalog.add((EX.Book, RDF.type, OWL.Class))
    catalog.add((EX.title, RDF.type, OWL.DatatypeProperty))
    catalog.add((EX.Person, RDF.type, OWL.NamedIndividual))
    catalog.add((EX.ISBN, RDF.type, RDFS.Datatype))
    catalog.add((
        EX.book1,
        EX.isbn,
        Literal("123", datatype=EX.ISBN),
    ))

    # Equal labels must not merge different URIs.
    catalog.add((EX.title, RDFS.label, Literal("title")))
    inventory.add((EX2.article, RDF.type, EX2.Article))
    inventory.add((EX2.article, EX2.title, Literal("Another item")))
    inventory.add((EX2.title, RDFS.label, Literal("title")))

    query_result = dataset.query(
        main._metadata_vocabulary_query(
            [GRAPH_ONE, GRAPH_TWO]
        )
    )

    assert isinstance(query_result, Result)

    rows = cast(
        Iterable[tuple[object, object]],
        query_result,
    )

    roles = {
        (str(term), str(role))
        for term, role in rows
    }

    assert (str(EX.Book), "class") in roles
    assert (str(EX2.Article), "class") in roles
    assert (str(EX.title), "property") in roles
    assert (str(EX2.title), "property") in roles
    assert (str(EX.ISBN), "datatype") in roles
    assert (str(EX.Person), "individual") in roles

    extracted_uris = {uri for uri, _role in roles}

    assert str(EX.book1) not in extracted_uris
    assert str(EX.Acme) not in extracted_uris

    # RDF/OWL declaration types must not be mistaken for domain classes.
    assert str(OWL.Class) not in extracted_uris
    assert str(OWL.DatatypeProperty) not in extracted_uris
    assert str(OWL.NamedIndividual) not in extracted_uris
    assert str(RDFS.Datatype) not in extracted_uris


@pytest.mark.asyncio
async def test_generate_profile_uses_all_metadata_graphs(monkeypatch):
    monkeypatch.setitem(
        main.state,
        "metadata_files",
        [
            {
                "filename": "catalog.ttl",
                "graph_uri": GRAPH_ONE,
                "instances_merged": True,
            },
            {
                "filename": "inventory.ttl",
                "graph_uri": GRAPH_TWO,
                "instances_merged": False,
            },
        ],
    )
    monkeypatch.setitem(
        main.state,
        "prefix_map",
        {}
    )
    monkeypatch.setitem(
        main.state,
        "ontologies",
        []
    )
    monkeypatch.setitem(
        main.state,
        "metadata_only_sources",
        {},
    )
    monkeypatch.setitem(
        main.state,
        "non_integrated_uris",
        set(),
    )

    store = AsyncMock()
    store.query.side_effect = [
        [
            {"term": str(EX.Book), "role": "class"},
            {"term": str(EX.title), "role": "property"},
            {
                "term": "http://www.w3.org/2001/XMLSchema#string",
                "role": "datatype",
            },
        ],
        [{"class": str(EX.Book), "prop": str(EX.title)}],
    ]

    profile = main.SHACLProfile(store)

    monkeypatch.setattr(
        profile,
        "_set_default_constraints",
        AsyncMock(),
    )
    monkeypatch.setattr(
        main,
        "get_global_property_order",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        main,
        "get_property_domains",
        lambda _uri: [],
    )

    await profile.generate_from_metadata()

    queries = [
        call.args[0]
        for call in store.query.call_args_list
    ]

    assert len(queries) == 2

    for query in queries:
        assert GRAPH_ONE in query
        assert GRAPH_TWO in query

    store.update.assert_awaited_once()

    update = store.update.await_args.args[0]

    assert "DELETE" not in update.upper()
    assert "sh:targetClass" in update
    assert "sh:path" in update
    assert "sh:property" in update
    assert "sh:targetNode" in update

@pytest.mark.asyncio
async def test_file_integration_uses_shared_service(
    monkeypatch,
    tmp_path,
):
    filename = "catalog.ttl"
    graph_uri = main.metadata_graph_uri(filename)

    monkeypatch.setitem(
        main.state,
        "metadata_files",
        [
            {
                "filename": filename,
                "graph_uri": graph_uri,
                "vocab_integrated": False,
            }
        ],
    )
    monkeypatch.setitem(
        main.state,
        "metadata_only_sources",
        {},
    )
    monkeypatch.setitem(
        main.state,
        "non_integrated_uris",
        set(),
    )
    monkeypatch.setattr(
        main,
        "METADATA_DIR",
        tmp_path,
    )

    entities = {
        "class": {str(EX.Book)},
        "property": {str(EX.title)},
        "datatype": set(),
        "individual": set(),
    }

    integration = AsyncMock(
        return_value=entities,
    )

    monkeypatch.setattr(
        main.shacl,
        "integrate_metadata_graphs",
        integration,
    )

    result = await main.integrate_file_vocab(
        filename
    )

    integration.assert_awaited_once_with(
        [graph_uri],
        source=filename,
    )

    assert result == {
        "status": "ok",
        "entities_integrated": 2,
    }
    assert (
        main.state["metadata_files"][0]["vocab_integrated"]
        is True
    )

    with open(
        tmp_path / f"{filename}.meta.json",
        encoding="utf-8",
    ) as file:
        sidecar = json.load(file)

    assert sidecar["vocab_integrated"] is True