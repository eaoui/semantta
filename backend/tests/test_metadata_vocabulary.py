import sys
import re
from pathlib import Path
from unittest.mock import AsyncMock
from collections.abc import Iterable
from typing import cast
from types import SimpleNamespace

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
        main,
        "_get_active_profile_classes",
        AsyncMock(return_value=set()),
    )

    monkeypatch.setattr(
        main,
        "_load_stored_profile_field_modes",
        AsyncMock(return_value={}),
    )

    persist_modes = AsyncMock()

    monkeypatch.setattr(
        main,
        "_persist_profile_field_modes",
        persist_modes,
    )

    reconciliation = AsyncMock()

    monkeypatch.setattr(
        main,
        "_reconcile_property_domain_links",
        reconciliation,
    )

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

    reconciliation.assert_awaited_once_with(
        profile_store=store,
        property_uris={str(EX.title)},
    )

    queries = [
        call.args[0]
        for call in store.query.call_args_list
    ]

    assert len(queries) == 2

    for query in queries:
        assert GRAPH_ONE in query
        assert GRAPH_TWO in query

    updates = [
        call.args[0]
        for call in store.update.call_args_list
    ]

    assert any(
        "INSERT DATA" in update
        and main.SHAPES_GRAPH in update
        for update in updates
    )

    assert any(
        "sh:deactivated" in update
        for update in updates
    )

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
    field_state_graph = dataset.graph(
        URIRef(main.PROFILE_FIELD_STATE_GRAPH)
    )
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
    first_state_snapshot = set(field_state_graph)

    second_result = await profile.integrate_metadata_graphs(
        [GRAPH_ONE],
        source="catalog.ttl",
    )
    second_snapshot = set(shapes_graph)
    second_state_snapshot = set(field_state_graph)

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

    # Metadata-derived domains become explicit overrides when
    # the ontology provides no domain declarations.
    domain_state_uri = main._profile_field_state_uri(
        str(EX.title),
        "urn:domainClasses",
    )

    vocab = main.PROFILE_FIELD_STATE_VOCAB

    assert (
        domain_state_uri,
        vocab.entity,
        EX.title,
    ) in field_state_graph

    assert (
        domain_state_uri,
        vocab.field,
        URIRef("urn:domainClasses"),
    ) in field_state_graph

    assert (
        domain_state_uri,
        vocab.mode,
        Literal(main.PROFILE_FIELD_MODE_OVERRIDE),
    ) in field_state_graph

    assert second_state_snapshot == first_state_snapshot

    # Both runs issue the same additive update.
    assert store.update_calls

    # Shape insertion and domain reconciliation are performed.
    assert any(
        "INSERT DATA" in update
        and main.SHAPES_GRAPH in update
        for update in store.update_calls
    )

    assert any(
        "DELETE" in update.upper()
        and "sh:property" in update
        for update in store.update_calls
    )

    for update in store.update_calls:
        if "DELETE" not in update.upper():
            continue

        match = re.search(
            r"\bDELETE\s*\{(.*?)\}\s*WHERE\b",
            update,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if match is None:
            continue

        delete_clause = match.group(1)

        if "sh:property" in delete_clause:
            assert "sh:closed" not in delete_clause
            assert "sh:targetClass" not in delete_clause
            assert "sh:path" not in delete_clause

@pytest.mark.asyncio
async def test_batch_entity_roles_skips_unsupported_uris():
    store = AsyncMock()
    store.query.return_value = []

    profile = main.ApplicationProfile(
        cast(main.RDFStore, store)
    )

    invalid_uri = (
        "file:///tmp/semantta-metadata-test/lclang%20"
    )
    valid_uri = str(EX.Book)

    result = await profile._batch_entity_roles([
        invalid_uri,
        valid_uri,
    ])

    assert result == {}
    assert store.query.await_count == 4

    for call in store.query.await_args_list:
        query = call.args[0]
        assert invalid_uri not in query
        assert f"<{valid_uri}>" in query


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("existing_mode", "ontology_domains", "initial_domain"),
    [
        (
            "override",
            [str(EX.Book)],
            str(EX2.Article),
        ),
        (
            "default",
            [str(EX2.Article)],
            str(EX.Book),
        ),
    ],
)
async def test_metadata_integration_preserves_existing_domain_mode(
    monkeypatch,
    existing_mode,
    ontology_domains,
    initial_domain,
):
    dataset = Dataset()
    metadata_graph = dataset.graph(URIRef(GRAPH_ONE))
    shapes_graph = dataset.graph(URIRef(main.SHAPES_GRAPH))
    state_graph = dataset.graph(
        URIRef(main.PROFILE_FIELD_STATE_GRAPH)
    )

    # Metadata observes Book -> title.
    metadata_graph.add((EX.book1, RDF.type, EX.Book))
    metadata_graph.add((EX.book1, EX.title, Literal("Example")))
    metadata_graph.add((EX.Book, RDF.type, OWL.Class))
    metadata_graph.add((EX.title, RDF.type, OWL.DatatypeProperty))

    book_shape = URIRef(
        main.shape_uri_for_entity(str(EX.Book), "class", {})
    )
    article_shape = URIRef(
        main.shape_uri_for_entity(str(EX2.Article), "class", {})
    )
    property_shape = URIRef(
        main.shape_uri_for_entity(str(EX.title), "property", {})
    )

    for shape_uri, class_uri in (
        (book_shape, EX.Book),
        (article_shape, EX2.Article),
    ):
        shapes_graph.add((shape_uri, RDF.type, SH.NodeShape))
        shapes_graph.add((shape_uri, SH.targetClass, class_uri))

    shapes_graph.add((property_shape, RDF.type, SH.PropertyShape))
    shapes_graph.add((property_shape, SH.path, EX.title))

    initial_shape = (
        book_shape
        if initial_domain == str(EX.Book)
        else article_shape
    )
    shapes_graph.add((initial_shape, SH.property, property_shape))

    # Persist the existing user decision.
    record_uri = main._profile_field_state_uri(
        str(EX.title),
        "urn:domainClasses",
    )
    vocab = main.PROFILE_FIELD_STATE_VOCAB

    state_graph.add((record_uri, vocab.entity, EX.title))
    state_graph.add((
        record_uri,
        vocab.field,
        URIRef("urn:domainClasses"),
    ))
    state_graph.add((
        record_uri,
        vocab.mode,
        Literal(existing_mode),
    ))

    store = DatasetBackedStore(dataset)
    profile = main.SHACLProfile(
        cast(main.RDFStore, store)
    )

    for key, value in (
        ("ontologies", []),
        ("prefix_map", {}),
        ("metadata_only_sources", {}),
        ("non_integrated_uris", set()),
    ):
        monkeypatch.setitem(main.state, key, value)

    monkeypatch.setattr(
        main,
        "get_property_domains",
        lambda uri: ontology_domains if uri == str(EX.title) else [],
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

    await profile.integrate_metadata_graphs(
        [GRAPH_ONE],
        source="catalog.ttl",
    )

    effective_domains = await main.ap._get_shacl_domains(
        profile_store=cast(main.RDFStore, store),
    )

    expected_domain = (
        [str(EX2.Article)]
        if existing_mode == "override"
        else sorted(ontology_domains)
    )

    assert effective_domains[str(EX.title)] == expected_domain

    linked_domains = {
        str(class_uri)
        for class_shape in shapes_graph.subjects(
            SH.property,
            property_shape,
        )
        for class_uri in shapes_graph.objects(
            class_shape,
            SH.targetClass,
        )
    }

    assert linked_domains == set(expected_domain)

    # The original field mode must survive integration.
    assert (
        record_uri,
        vocab.mode,
        Literal(existing_mode),
    ) in state_graph
