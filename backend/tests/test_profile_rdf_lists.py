from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock
from collections.abc import Iterable
from typing import cast

import pytest
from fastapi import HTTPException
from rdflib import BNode, Dataset, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF
from rdflib.query import Result
from rdflib.term import Node


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


EX = Namespace("https://example.org/rdf-list-test/")
SH = Namespace("http://www.w3.org/ns/shacl#")


class DatasetStore:
    def __init__(self):
        self.dataset = Dataset()
        self.shapes = self.dataset.graph(
            URIRef(main.SHAPES_GRAPH)
        )

    async def query(self, sparql: str) -> list[dict[str, str]]:
        result = self.dataset.query(sparql)
        assert isinstance(result, Result)

        variables = [
            str(variable)
            for variable in (result.vars or [])
        ]

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
        self.dataset.update(sparql)

    async def load_shapes_graph(self) -> Graph:
        graph = Graph()
        graph += self.shapes
        return graph


def add_property_shape(
    graph: Graph,
    shape_uri: URIRef,
    property_uri: URIRef,
) -> None:
    graph.add((shape_uri, RDF.type, SH.PropertyShape))
    graph.add((shape_uri, SH.path, property_uri))


def configure_resolver(
    monkeypatch,
    predicate: str,
    store: DatasetStore,
) -> main.SHACLProfile:
    monkeypatch.setattr(
        main,
        "get_original_constraints",
        lambda *_: {},
    )
    monkeypatch.setattr(
        main,
        "get_property_domains",
        lambda *_: [],
    )
    monkeypatch.setattr(
        main,
        "_load_stored_profile_field_modes",
        AsyncMock(return_value={
            predicate: main.PROFILE_FIELD_MODE_OVERRIDE,
        }),
    )
    monkeypatch.setattr(
        main,
        "_validate_profile_range_constraint_compatibility",
        lambda *args, **kwargs: None,
    )

    return main.SHACLProfile(
        cast(main.RDFStore, store)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entity_type", "predicate", "values"),
    [
        (
            "object_property",
            str(SH["in"]),
            [
                str(EX.Draft),
                str(EX.Review),
                str(EX.Published),
            ],
        ),
        (
            "datatype_property",
            str(SH.languageIn),
            [
                "en",
                "fr-CA",
                "zh-Hant-TW",
            ],
        ),
    ],
)
async def test_rdf_list_constraints_round_trip(
    monkeypatch,
    entity_type,
    predicate,
    values,
):
    store = DatasetStore()

    property_uri = EX.status
    shape_uri = EX.StatusShape

    add_property_shape(
        store.shapes,
        shape_uri,
        property_uri,
    )

    monkeypatch.setattr(main, "store", store)

    # Persist the constraint through the production writer.
    await main._apply_constraints(
        str(shape_uri),
        {predicate: values},
        keep_predicates={
            RDF.type,
            SH.path,
        },
    )

    profile = configure_resolver(
        monkeypatch,
        predicate,
        store,
    )

    result = await profile.get_entity_constraints(
        str(property_uri),
        entity_type,
    )

    # Neither the API override nor effective value may expose a blank node.
    assert result["overrides"][predicate] == values
    assert result["effective"][predicate] == values

    shapes = await store.load_shapes_graph()
    heads = list(
        shapes.objects(shape_uri, URIRef(predicate))
    )

    assert len(heads) == 1
    assert main._read_rdf_list(shapes, heads[0]) == values


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entity_type", "predicate"),
    [
        ("object_property", str(SH["in"])),
        ("datatype_property", str(SH.languageIn)),
    ],
)
async def test_empty_rdf_list_is_preserved_as_empty_override(
    monkeypatch,
    entity_type,
    predicate,
):
    store = DatasetStore()

    property_uri = EX.status
    shape_uri = EX.StatusShape

    add_property_shape(
        store.shapes,
        shape_uri,
        property_uri,
    )

    monkeypatch.setattr(main, "store", store)

    await main._apply_constraints(
        str(shape_uri),
        {predicate: []},
        keep_predicates={
            RDF.type,
            SH.path,
        },
    )

    shapes = await store.load_shapes_graph()

    assert (
        shape_uri,
        URIRef(predicate),
        RDF.nil,
    ) in shapes

    profile = configure_resolver(
        monkeypatch,
        predicate,
        store,
    )

    result = await profile.get_entity_constraints(
        str(property_uri),
        entity_type,
    )

    assert predicate in result["overrides"]
    assert result["overrides"][predicate] == []
    assert result["effective"][predicate] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformation",
    [
        "literal-head",
        "missing-first",
        "missing-rest",
        "multiple-first",
        "multiple-rest",
        "literal-rest",
        "cycle",
    ],
)
async def test_constraint_resolver_rejects_malformed_rdf_lists(
    monkeypatch,
    malformation,
):
    store = DatasetStore()

    property_uri = EX.status
    shape_uri = EX.StatusShape
    head = BNode("listHead")

    add_property_shape(
        store.shapes,
        shape_uri,
        property_uri,
    )

    if malformation == "literal-head":
        store.shapes.add((
            shape_uri,
            SH["in"],
            Literal("not-an-rdf-list"),
        ))

    else:
        store.shapes.add((
            shape_uri,
            SH["in"],
            head,
        ))

        if malformation == "missing-first":
            store.shapes.add((
                head,
                RDF.rest,
                RDF.nil,
            ))

        elif malformation == "missing-rest":
            store.shapes.add((
                head,
                RDF.first,
                EX.Draft,
            ))

        elif malformation == "multiple-first":
            store.shapes.add((
                head,
                RDF.first,
                EX.Draft,
            ))
            store.shapes.add((
                head,
                RDF.first,
                EX.Published,
            ))
            store.shapes.add((
                head,
                RDF.rest,
                RDF.nil,
            ))

        elif malformation == "multiple-rest":
            store.shapes.add((
                head,
                RDF.first,
                EX.Draft,
            ))
            store.shapes.add((
                head,
                RDF.rest,
                RDF.nil,
            ))
            store.shapes.add((
                head,
                RDF.rest,
                BNode("anotherCell"),
            ))

        elif malformation == "literal-rest":
            store.shapes.add((
                head,
                RDF.first,
                EX.Draft,
            ))
            store.shapes.add((
                head,
                RDF.rest,
                Literal("invalid"),
            ))

        elif malformation == "cycle":
            store.shapes.add((
                head,
                RDF.first,
                EX.Draft,
            ))
            store.shapes.add((
                head,
                RDF.rest,
                head,
            ))

    profile = configure_resolver(
        monkeypatch,
        str(SH["in"]),
        store,
    )

    with pytest.raises(HTTPException) as exc_info:
        await profile.get_entity_constraints(
            str(property_uri),
            "object_property",
        )

    assert exc_info.value.status_code == 409
    assert "RDF list" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_constraint_resolver_rejects_conflicting_lists_across_shapes(
    monkeypatch,
):
    store = DatasetStore()

    property_uri = EX.status

    for shape_uri, values in (
        (EX.StatusShape1, [EX.Draft, EX.Published]),
        (EX.StatusShape2, [EX.Draft, EX.Review]),
    ):
        add_property_shape(
            store.shapes,
            shape_uri,
            property_uri,
        )

        head = BNode()

        from rdflib.collection import Collection
        Collection(
            store.shapes,
            head,
            cast(list[Node], list(values)),
        )

        store.shapes.add((
            shape_uri,
            SH["in"],
            head,
        ))

    profile = configure_resolver(
        monkeypatch,
        str(SH["in"]),
        store,
    )

    with pytest.raises(HTTPException) as exc_info:
        await profile.get_entity_constraints(
            str(property_uri),
            "object_property",
        )

    assert exc_info.value.status_code == 409
    assert "Conflicting RDF lists" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_apply_constraints_rejects_scalar_rdf_list_values_before_update(
    monkeypatch,
):
    store = AsyncMock()
    monkeypatch.setattr(main, "store", store)

    with pytest.raises(HTTPException) as exc_info:
        await main._apply_constraints(
            str(EX.StatusShape),
            {
                str(SH["in"]): str(EX.Draft),
            },
            keep_predicates={
                RDF.type,
                SH.path,
            },
        )

    assert exc_info.value.status_code == 400
    store.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_language_in_rejects_invalid_language_tags(
    monkeypatch,
):
    store = AsyncMock()
    monkeypatch.setattr(main, "store", store)

    with pytest.raises(HTTPException) as exc_info:
        await main._apply_constraints(
            str(EX.StatusShape),
            {
                str(SH.languageIn): [
                    "en",
                    "invalid--tag",
                ],
            },
            keep_predicates={
                RDF.type,
                SH.path,
            },
        )

    assert exc_info.value.status_code == 400
    store.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_property_form_preserves_single_and_multiple_list_members():
    profile = main.ApplicationProfile(
        store=AsyncMock(),
    )

    result = await profile._get_property_constraints(
        str(EX.status),
        effective_profile={
            str(SH["in"]): [str(EX.Draft)],
            str(SH.languageIn): [
                "en",
                "fr-CA",
            ],
        },
    )

    assert result["in"] == [str(EX.Draft)]
    assert result["languageIn"] == ["en", "fr-CA"]


@pytest.mark.asyncio
async def test_property_form_preserves_explicitly_empty_in_list():
    profile = main.ApplicationProfile(
        store=AsyncMock(),
    )

    result = await profile._get_property_constraints(
        str(EX.status),
        effective_profile={
            str(SH["in"]): [],
        },
    )

    assert "in" in result
    assert result["in"] == []