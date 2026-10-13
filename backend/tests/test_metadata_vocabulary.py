import sys
from pathlib import Path
from unittest.mock import AsyncMock
from collections.abc import Iterable
from typing import cast
from types import SimpleNamespace
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

SH = Namespace("http://www.w3.org/ns/shacl#")


class DatasetBackedStore:
    """Minimal RDF store backed by an RDFLib Dataset."""

    def __init__(self, dataset: Dataset):
        self.dataset = dataset
        self.update_calls: list[str] = []

    async def query(self, sparql: str) -> list[dict[str, str]]:
        result = self.dataset.query(sparql)

        assert isinstance(result, Result)

        variables = [
            str(variable)
            for variable in (result.vars or [])
        ]
        rows = cast(
            Iterable[tuple[object, ...]],
            result,
        )

        return [
            {
                name: str(value)
                for name, value in zip(variables, row)
                if value is not None
            }
            for row in rows
        ]

    async def update(self, sparql: str) -> None:
        self.update_calls.append(sparql)
        self.dataset.update(sparql)

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

    graph_result = dataset.query(
        main._metadata_vocabulary_query(
            [GRAPH_ONE, GRAPH_TWO],
            include_graph=True,
        )
    )

    assert isinstance(graph_result, Result)

    graph_rows = cast(
        Iterable[tuple[object, object, object]],
        graph_result,
    )

    graph_terms = {
        (str(graph), str(term), str(role))
        for graph, term, role in graph_rows
    }

    assert (
        GRAPH_ONE,
        str(EX.Book),
        "class",
    ) in graph_terms

    assert (
        GRAPH_TWO,
        str(EX2.Article),
        "class",
    ) in graph_terms


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
                "graph_uri": graph_uri
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

    assert not (
        tmp_path / f"{filename}.meta.json"
    ).exists()

@pytest.mark.asyncio
async def test_integration_status_is_batched_and_live(
    monkeypatch,
):
    graph_catalog = main.metadata_graph_uri(
        "catalog.ttl"
    )
    graph_inventory = main.metadata_graph_uri(
        "inventory.ttl"
    )
    graph_empty = main.metadata_graph_uri(
        "empty.ttl"
    )

    metadata_files = [
        {
            "filename": "catalog.ttl",
            "graph_uri": graph_catalog,
        },
        {
            "filename": "inventory.ttl",
            "graph_uri": graph_inventory,
        },
        {
            "filename": "empty.ttl",
            "graph_uri": graph_empty,
        },
    ]

    graph_stats = {
        graph_catalog: {},
        graph_inventory: {},
        graph_empty: {},
    }

    monkeypatch.setitem(
        main.state,
        "metadata_files",
        metadata_files,
    )
    monkeypatch.setitem(
        main.state,
        "metadata_graph_stats",
        graph_stats,
    )
    monkeypatch.setitem(
        main.state,
        "ontologies",
        [],
    )

    vocabulary_rows = [
        {
            "graph": graph_catalog,
            "term": str(EX.Book),
            "role": "class",
        },
        {
            "graph": graph_catalog,
            "term": str(EX.title),
            "role": "property",
        },
        {
            "graph": graph_inventory,
            "term": str(EX2.Article),
            "role": "class",
        },
    ]

    active_rows_initial = [
        {"uri": str(EX.Book), "role": "class"},
        {"uri": str(EX.title), "role": "property"},
        {"uri": str(EX2.Article), "role": "class"},
    ]

    # Simulate removal of the title property from the active profile.
    active_rows_after_change = [
        {"uri": str(EX.Book), "role": "class"},
        {"uri": str(EX2.Article), "role": "class"},
    ]

    fake_store = SimpleNamespace(
        query=AsyncMock(
            side_effect=[
                vocabulary_rows,
                active_rows_initial,
                active_rows_after_change,
            ]
        )
    )

    monkeypatch.setattr(
        main,
        "store",
        fake_store,
    )

    first_result = (
        await main.get_metadata_integration_status()
    )

    first_statuses = first_result["statuses"]

    assert (
        first_statuses["catalog.ttl"]["status"]
        == "integrated"
    )
    assert (
        first_statuses["inventory.ttl"]["status"]
        == "integrated"
    )
    assert (
        first_statuses["empty.ttl"]["status"]
        == "no_vocabulary"
    )

    # The second request reuses extracted metadata summaries,
    # but queries the current active profile again.
    second_result = (
        await main.get_metadata_integration_status()
    )

    second_statuses = second_result["statuses"]

    assert (
        second_statuses["catalog.ttl"]["status"]
        == "not_integrated"
    )
    assert (
        second_statuses["catalog.ttl"]["missing_count"]
        == 1
    )
    assert (
        second_statuses["inventory.ttl"]["status"]
        == "integrated"
    )

    # One batched vocabulary query, followed by one active-profile
    # query per status request.
    assert fake_store.query.await_count == 3

    # Summaries have been retained in the existing graph-stat cache.
    assert (
        "vocabulary_entities"
        in graph_stats[graph_catalog]
    )

@pytest.mark.asyncio
async def test_metadata_integration_is_idempotent_and_preserves_custom_constraints(
    monkeypatch,
):
    dataset = Dataset()
    metadata_graph = dataset.graph(URIRef(GRAPH_ONE))
    shapes_graph = dataset.graph(
        URIRef(main.SHAPES_GRAPH)
    )

    # Metadata uses a class and property.
    metadata_graph.add((
        EX.book1,
        RDF.type,
        EX.Book,
    ))
    metadata_graph.add((
        EX.book1,
        EX.title,
        Literal("Example book"),
    ))
    metadata_graph.add((
        EX.Book,
        RDF.type,
        OWL.Class,
    ))
    metadata_graph.add((
        EX.title,
        RDF.type,
        OWL.DatatypeProperty,
    ))

    class_shape = URIRef(
        main.shape_uri_for_entity(
            str(EX.Book),
            "class",
            {},
        )
    )
    manual_property_shape = URIRef(
        "urn:test:manual-property-shape"
    )

    # Existing manual constraints that integration must preserve.
    shapes_graph.add((
        class_shape,
        SH.closed,
        Literal(True),
    ))
    shapes_graph.add((
        class_shape,
        SH.property,
        manual_property_shape,
    ))
    shapes_graph.add((
        manual_property_shape,
        RDF.type,
        SH.PropertyShape,
    ))
    shapes_graph.add((
        manual_property_shape,
        SH.path,
        EX.manualProperty,
    ))

    store = DatasetBackedStore(dataset)
    profile = main.SHACLProfile(
        cast(main.RDFStore, store)
    )

    monkeypatch.setitem(
        main.state,
        "ontologies",
        [],
    )
    monkeypatch.setitem(
        main.state,
        "prefix_map",
        {},
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
        "get_property_domains",
        lambda _uri: [],
    )
    monkeypatch.setattr(
        main,
        "get_global_property_order",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        profile,
        "_set_default_constraints",
        AsyncMock(),
    )

    expected_entities = {
        "class": {str(EX.Book)},
        "property": {str(EX.title)},
    }

    first_result = await profile.integrate_metadata_graphs(
        [GRAPH_ONE],
        source="catalog.ttl",
    )
    first_snapshot = set(shapes_graph)

    second_result = await profile.integrate_metadata_graphs(
        [GRAPH_ONE],
        source="catalog.ttl",
    )
    second_snapshot = set(shapes_graph)

    assert first_result["class"] == expected_entities["class"]
    assert first_result["property"] == expected_entities["property"]
    assert second_result == first_result

    # Repeating integration must not change the RDF graph.
    assert second_snapshot == first_snapshot

    # Manually configured constraints and links survive.
    assert (
        class_shape,
        SH.closed,
        Literal(True),
    ) in shapes_graph
    assert (
        class_shape,
        SH.property,
        manual_property_shape,
    ) in shapes_graph
    assert (
        manual_property_shape,
        SH.path,
        EX.manualProperty,
    ) in shapes_graph

    # Integration adds the expected class-property link.
    generated_property_shape = URIRef(
        main.shape_uri_for_entity(
            str(EX.title),
            "property",
            {},
        )
    )
    assert (
        class_shape,
        SH.property,
        generated_property_shape,
    ) in shapes_graph

    # Both runs issue the same additive update.
    assert len(store.update_calls) == 2
    assert store.update_calls[0] == store.update_calls[1]
    assert all(
        "DELETE" not in update.upper()
        for update in store.update_calls
    )