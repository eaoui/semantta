
from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from rdflib import Dataset, Literal, Namespace, URIRef
from rdflib.namespace import RDF
from rdflib.query import Result
from types import SimpleNamespace

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


EX = Namespace("http://example.org/")
SH = main.SH

BOOK = str(EX.Book)
ARTICLE = str(EX.Article)
RESOURCE = str(EX.Resource)
PERSON = str(EX.Person)

TITLE = str(EX.title)
AUTHOR = str(EX.author)


class DatasetBackedStore:
    """RDFLib-backed store for profile-domain regression tests."""

    def __init__(self, dataset: Dataset):
        self.dataset = dataset
        self.update_calls: list[str] = []

    async def query(self, sparql: str) -> list[dict[str, str]]:
        result = self.dataset.query(sparql)
        assert isinstance(result, Result)

        variables = [str(variable) for variable in (result.vars or [])]
        rows = cast(Iterable[tuple[object, ...]], result)

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


@pytest.fixture
def domain_store(monkeypatch):
    dataset = Dataset()
    store = DatasetBackedStore(dataset)

    monkeypatch.setitem(main.state, "prefix_map", {})

    return dataset, store


def add_class_shape(
    graph,
    class_uri: str,
    *,
    deactivated: bool = False,
) -> URIRef:
    shape_uri = URIRef(
        main.shape_uri_for_entity(class_uri, "class", {})
    )

    graph.add((shape_uri, RDF.type, SH.NodeShape))
    graph.add((shape_uri, SH.targetClass, URIRef(class_uri)))
    graph.add((shape_uri, SH.closed, Literal(True)))

    if deactivated:
        graph.add((shape_uri, SH.deactivated, Literal(True)))

    return shape_uri


def add_property_shape(
    graph,
    prop_uri: str,
    *,
    deactivated: bool = False,
) -> URIRef:
    shape_uri = URIRef(
        main.shape_uri_for_entity(prop_uri, "property", {})
    )

    graph.add((shape_uri, RDF.type, SH.PropertyShape))
    graph.add((shape_uri, SH.path, URIRef(prop_uri)))
    graph.add((shape_uri, SH.minCount, Literal(1)))

    if deactivated:
        graph.add((shape_uri, SH.deactivated, Literal(True)))

    return shape_uri


def add_domain_mode(
    dataset: Dataset,
    prop_uri: str,
    mode: str,
) -> URIRef:
    graph = dataset.graph(
        URIRef(main.PROFILE_FIELD_STATE_GRAPH)
    )

    field_uri = "urn:domainClasses"
    record = main._profile_field_state_uri(
        prop_uri,
        field_uri,
    )
    vocab = main.PROFILE_FIELD_STATE_VOCAB

    graph.add((record, vocab.entity, URIRef(prop_uri)))
    graph.add((record, vocab.field, URIRef(field_uri)))
    graph.add((record, vocab.mode, Literal(mode)))

    return record


def property_domains_in_graph(graph, prop_shape: URIRef) -> set[str]:
    return {
        str(class_uri)
        for class_shape in graph.subjects(
            SH.property,
            prop_shape,
        )
        for class_uri in graph.objects(
            class_shape,
            SH.targetClass,
        )
    }


# ---------------------------------------------------------------------------
# Effective domain resolution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_domain_mode_uses_complete_ontology_defaults(
    domain_store,
    monkeypatch,
):
    dataset, store = domain_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    book_shape = add_class_shape(graph, BOOK)
    article_shape = add_class_shape(
        graph,
        ARTICLE,
        deactivated=True,
    )

    title_shape = add_property_shape(graph, TITLE)

    # Only one of the two ontology domains has a SHACL association.
    graph.add((book_shape, SH.property, title_shape))

    # There is deliberately no stored Domain Classes field-mode record.
    monkeypatch.setattr(
        main,
        "get_property_domains",
        lambda uri: [BOOK, ARTICLE] if uri == TITLE else [],
    )

    profile = main.ApplicationProfile(store)

    domains = await profile._get_shacl_domains()

    assert domains[TITLE] == sorted([BOOK, ARTICLE])

    # The incomplete SHACL association must not be interpreted as
    # an explicit override.
    assert article_shape not in graph.subjects(SH.property, title_shape)


@pytest.mark.asyncio
async def test_explicit_override_uses_associations_to_deactivated_classes(
    domain_store,
    monkeypatch,
):
    dataset, store = domain_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    book_shape = add_class_shape(graph, BOOK)
    article_shape = add_class_shape(
        graph,
        ARTICLE,
        deactivated=True,
    )

    author_shape = add_property_shape(graph, AUTHOR)
    graph.add((article_shape, SH.property, author_shape))

    add_domain_mode(
        dataset,
        AUTHOR,
        main.PROFILE_FIELD_MODE_OVERRIDE,
    )

    monkeypatch.setattr(
        main,
        "get_property_domains",
        lambda uri: [BOOK] if uri == AUTHOR else [],
    )

    profile = main.ApplicationProfile(store)

    domains = await profile._get_shacl_domains()

    assert domains[AUTHOR] == [ARTICLE]
    assert article_shape in graph.subjects(SH.property, author_shape)
    assert book_shape not in graph.subjects(SH.property, author_shape)


@pytest.mark.asyncio
async def test_explicit_empty_domain_override_remains_empty(
    domain_store,
    monkeypatch,
):
    dataset, store = domain_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    property_shape = add_property_shape(graph, TITLE)

    add_domain_mode(
        dataset,
        TITLE,
        main.PROFILE_FIELD_MODE_OVERRIDE,
    )

    monkeypatch.setattr(
        main,
        "get_property_domains",
        lambda uri: [BOOK] if uri == TITLE else [],
    )

    profile = main.ApplicationProfile(store)

    domains = await profile._get_shacl_domains()

    assert domains[TITLE] == []
    assert not list(graph.subjects(SH.property, property_shape))


# ---------------------------------------------------------------------------
# Domain association replacement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_replacing_domains_materializes_missing_classes_as_inactive(
    domain_store,
):
    dataset, store = domain_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    book_shape = add_class_shape(graph, BOOK)
    graph.add((book_shape, SH.closed, Literal(True)))

    title_shape = add_property_shape(graph, TITLE)
    graph.add((book_shape, SH.property, title_shape))

    await main._replace_property_domain_links(
        TITLE,
        [ARTICLE],
        profile_store=store,
    )

    article_shape = URIRef(
        main.shape_uri_for_entity(ARTICLE, "class", {})
    )

    assert (article_shape, RDF.type, SH.NodeShape) in graph
    assert (article_shape, SH.targetClass, URIRef(ARTICLE)) in graph
    assert (article_shape, SH.deactivated, Literal(True)) in graph
    assert (article_shape, SH.property, title_shape) in graph

    # The previous direct association is replaced.
    assert (book_shape, SH.property, title_shape) not in graph

    # The existing class shape and its unrelated configuration survive.
    assert (book_shape, SH.targetClass, URIRef(BOOK)) in graph
    assert (book_shape, SH.closed, Literal(True)) in graph


@pytest.mark.asyncio
async def test_replacing_domains_preserves_existing_inactive_shape_state(
    domain_store,
):
    dataset, store = domain_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    article_shape = add_class_shape(
        graph,
        ARTICLE,
        deactivated=True,
    )
    title_shape = add_property_shape(graph, TITLE)

    await main._replace_property_domain_links(
        TITLE,
        [ARTICLE],
        profile_store=store,
    )

    assert (article_shape, SH.property, title_shape) in graph
    assert (article_shape, SH.deactivated, Literal(True)) in graph


# ---------------------------------------------------------------------------
# Centralized reconciliation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reconciliation_materializes_all_default_domains_and_preserves_overrides(
    domain_store,
    monkeypatch,
):
    dataset, store = domain_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    book_shape = add_class_shape(graph, BOOK)

    default_shape = add_property_shape(graph, TITLE)
    override_shape = add_property_shape(graph, AUTHOR)

    # The default property currently has only one of its two associations.
    graph.add((book_shape, SH.property, default_shape))

    # The override property is explicitly associated with Book.
    graph.add((book_shape, SH.property, override_shape))

    add_domain_mode(
        dataset,
        AUTHOR,
        main.PROFILE_FIELD_MODE_OVERRIDE,
    )

    ontology_domains = {
        TITLE: [BOOK, ARTICLE],
        AUTHOR: [ARTICLE],
    }

    monkeypatch.setattr(
        main,
        "get_property_domains",
        lambda uri: ontology_domains.get(uri, []),
    )

    await main._reconcile_property_domain_links(
        profile_store=store,
    )

    article_shape = URIRef(
        main.shape_uri_for_entity(ARTICLE, "class", {})
    )

    # Complete default domain list is represented in SHACL.
    assert property_domains_in_graph(
        graph,
        default_shape,
    ) == {BOOK, ARTICLE}

    # The missing domain class is materialized but remains inactive.
    assert (article_shape, RDF.type, SH.NodeShape) in graph
    assert (article_shape, SH.targetClass, URIRef(ARTICLE)) in graph
    assert (article_shape, SH.deactivated, Literal(True)) in graph

    # Explicit override remains independent of ontology changes.
    assert property_domains_in_graph(
        graph,
        override_shape,
    ) == {BOOK}

    # Existing Book shape configuration survives.
    assert (book_shape, SH.closed, Literal(True)) in graph

    graph_after_first_run = set(graph)

    # Reconciliation is idempotent.
    await main._reconcile_property_domain_links(
        profile_store=store,
    )

    assert set(graph) == graph_after_first_run


@pytest.mark.asyncio
async def test_targeted_reconciliation_does_not_change_other_properties(
    domain_store,
    monkeypatch,
):
    dataset, store = domain_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    book_shape = add_class_shape(graph, BOOK)
    article_shape = add_class_shape(graph, ARTICLE)

    title_shape = add_property_shape(graph, TITLE)
    author_shape = add_property_shape(graph, AUTHOR)

    graph.add((book_shape, SH.property, title_shape))
    graph.add((article_shape, SH.property, author_shape))

    monkeypatch.setattr(
        main,
        "get_property_domains",
        lambda uri: (
            [ARTICLE] if uri == TITLE else [BOOK]
        ),
    )

    await main._reconcile_property_domain_links(
        profile_store=store,
        property_uris={TITLE},
    )

    assert property_domains_in_graph(graph, title_shape) == {ARTICLE}
    assert property_domains_in_graph(graph, author_shape) == {ARTICLE}


# ---------------------------------------------------------------------------
# Active-domain inheritance
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inactive_domain_class_does_not_enable_inherited_property(
    domain_store,
    monkeypatch,
):
    dataset, store = domain_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    add_class_shape(graph, BOOK)
    resource_shape = add_class_shape(
        graph,
        RESOURCE,
        deactivated=True,
    )

    identifier_shape = add_property_shape(
        graph,
        str(EX.identifier),
    )
    graph.add((resource_shape, SH.property, identifier_shape))

    profile = main.ApplicationProfile(store)

    monkeypatch.setattr(
        profile,
        "_get_shacl_domains",
        AsyncMock(
            return_value={
                str(EX.identifier): [RESOURCE],
            }
        ),
    )

    monkeypatch.setattr(
        main,
        "_subclass_pairs",
        {(BOOK, RESOURCE)},
    )

    # Book is active, but its only property domain is inactive.
    assert await profile._list_active_properties(BOOK) == []

    # Reactivating the domain class restores inherited applicability.
    graph.remove((resource_shape, SH.deactivated, Literal(True)))
    profile.invalidate()

    result = await profile._list_active_properties(BOOK)

    assert [item["uri"] for item in result] == [
        str(EX.identifier),
    ]


@pytest.mark.asyncio
async def test_metadata_membership_rejects_property_from_inactive_parent_domain(
    monkeypatch,
):
    profile = SimpleNamespace(
        store=object(),
        get_active_classes=AsyncMock(return_value=[BOOK]),
        get_active_properties=AsyncMock(
            return_value=[str(EX.identifier)]
        ),
    )

    monkeypatch.setattr(main, "shacl", profile)
    monkeypatch.setattr(
        main.ap,
        "_get_shacl_domains",
        AsyncMock(
            return_value={
                str(EX.identifier): [RESOURCE],
            }
        ),
    )
    monkeypatch.setattr(
        main,
        "_subclass_pairs",
        {(BOOK, RESOURCE)},
    )

    with pytest.raises(HTTPException) as exc_info:
        await main._validate_metadata_profile_membership(
            [BOOK],
            {str(EX.identifier): ["resource-value"]},
        )

    assert exc_info.value.status_code == 400
    assert "not applicable" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Class-side editing and field-mode preservation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_class_edit_preserves_override_when_result_equals_ontology_default(
    domain_store,
    monkeypatch,
):
    dataset, store = domain_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    book_shape = add_class_shape(graph, BOOK)
    article_shape = add_class_shape(graph, ARTICLE)

    title_shape = add_property_shape(graph, TITLE)

    # The current explicit override contains both classes.
    graph.add((book_shape, SH.property, title_shape))
    graph.add((article_shape, SH.property, title_shape))

    # An unrelated deactivated shape must not make active-class
    # discovery return an empty result.
    add_class_shape(
        graph,
        PERSON,
        deactivated=True,
    )

    add_domain_mode(
        dataset,
        TITLE,
        main.PROFILE_FIELD_MODE_OVERRIDE,
    )

    monkeypatch.setattr(
        main,
        "get_property_domains",
        lambda uri: [BOOK] if uri == TITLE else [],
    )

    # The user removes Article through its Class Properties editor.
    # The resulting domain is [Book], equal to the ontology default,
    # but it must remain an explicit override.
    await main._sync_entity_links(
        ARTICLE,
        "class",
        [],
        profile_store=store,
    )

    assert property_domains_in_graph(
        graph,
        title_shape,
    ) == {BOOK}

    modes = await main._load_stored_profile_field_modes(
        TITLE,
        profile_store=store,
    )

    assert modes["urn:domainClasses"] == (
        main.PROFILE_FIELD_MODE_OVERRIDE
    )


@pytest.mark.asyncio
async def test_default_domain_submission_synchronizes_inactive_domains(
    monkeypatch,
):
    store = AsyncMock()
    store.query.return_value = [
        {"ps": "urn:test:title-shape"},
    ]

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(
        main.ap,
        "get_entity_type",
        AsyncMock(return_value="object_property"),
    )
    monkeypatch.setattr(
        main,
        "_validate_profile_field_modes",
        lambda modes, _etype: modes,
    )
    monkeypatch.setattr(
        main,
        "validate_constraints",
        lambda *_: None,
    )
    monkeypatch.setattr(
        main,
        "_validate_profile_range_constraint_compatibility",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        main,
        "_load_stored_profile_field_modes",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        main,
        "get_property_domains",
        lambda uri: [BOOK, ARTICLE] if uri == TITLE else [],
    )

    apply_constraints = AsyncMock()
    sync_links = AsyncMock()
    persist_modes = AsyncMock()

    monkeypatch.setattr(
        main,
        "_apply_constraints",
        apply_constraints,
    )
    monkeypatch.setattr(
        main,
        "_sync_entity_links",
        sync_links,
    )
    monkeypatch.setattr(
        main,
        "_persist_profile_field_modes",
        persist_modes,
    )
    monkeypatch.setattr(
        main,
        "invalidate_profile",
        lambda: None,
    )

    await main.set_entity_constraints(
        TITLE,
        {
            "urn:domainClasses": [BOOK],
            main.PROFILE_FIELD_MODES_KEY: {
                "urn:domainClasses": main.PROFILE_FIELD_MODE_DEFAULT,
            },
        },
    )

    sync_links.assert_awaited_once_with(
        TITLE,
        "object_property",
        sorted([BOOK, ARTICLE]),
        profile_store=store,
    )

    persist_modes.assert_awaited_once_with(
        TITLE,
        {
            "urn:domainClasses": main.PROFILE_FIELD_MODE_DEFAULT,
        },
    )


@pytest.mark.asyncio
async def test_property_constraints_return_stored_domain_override(
    domain_store,
    monkeypatch,
):
    dataset, store = domain_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    book_shape = add_class_shape(graph, BOOK)
    title_shape = add_property_shape(graph, TITLE)

    graph.add((
        book_shape,
        SH.property,
        title_shape,
    ))

    # The ontology default differs from the explicit profile override.
    monkeypatch.setattr(
        main,
        "get_property_domains",
        lambda uri: [ARTICLE] if uri == TITLE else [],
    )

    add_domain_mode(
        dataset,
        TITLE,
        main.PROFILE_FIELD_MODE_OVERRIDE,
    )

    monkeypatch.setattr(
        main,
        "store",
        cast(main.RDFStore, store),
    )
    monkeypatch.setattr(
        main.ap,
        "get_entity_type",
        AsyncMock(return_value="datatype_property"),
    )
    monkeypatch.setattr(
        main,
        "get_original_constraints",
        lambda *_: {},
    )
    monkeypatch.setattr(
        main,
        "_validate_profile_range_constraint_compatibility",
        lambda *args, **kwargs: None,
    )

    result = await main.get_entity_constraints(TITLE)

    assert result["field_modes"]["urn:domainClasses"] == (
        main.PROFILE_FIELD_MODE_OVERRIDE
    )
    assert result["original"]["urn:domainClasses"] == [ARTICLE]
    assert result["overrides"]["urn:domainClasses"] == [BOOK]
    assert result["effective"]["urn:domainClasses"] == [BOOK]