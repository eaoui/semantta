from __future__ import annotations

import sys
from unittest.mock import AsyncMock
from collections.abc import Iterable
from pathlib import Path
from typing import cast

import pytest
from fastapi import HTTPException
from rdflib import Dataset, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS
from rdflib.query import Result

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")


class DatasetBackedStore:
    def __init__(self, dataset: Dataset):
        self.dataset = dataset

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
        self.dataset.update(sparql)

    async def insert_shapes(self, triples: str) -> None:
        graph = self.dataset.graph(URIRef(main.SHAPES_GRAPH))
        graph.parse(
            data=f"@prefix sh: <{SH}> .\n@prefix rdfs: <{RDFS}> .\n{triples}",
            format="turtle",
        )

    async def graph_exists(self, graph_uri: str) -> bool:
        return len(self.dataset.graph(URIRef(graph_uri))) > 0

    async def get_graph_stats(self, graph_uri: str) -> dict:
        graph = self.dataset.graph(URIRef(graph_uri))
        return {
            "triples": len(graph),
            "subjects": len(set(graph.subjects())),
        }


def add_node_shape(
    graph: Graph,
    entity_type: str,
    uri: str,
    order: int | None = None,
    *,
    deactivated: bool = False,
) -> URIRef:
    shape_uri = URIRef(
        main.shape_uri_for_entity(uri, entity_type, {})
    )
    target_predicate = {
        "class": SH.targetClass,
        "datatype": SH.targetNode,
        "individual": SH.targetNode,
    }[entity_type]

    graph.add((shape_uri, RDF.type, SH.NodeShape))
    graph.add((shape_uri, target_predicate, URIRef(uri)))

    if order is not None:
        graph.add((shape_uri, SH.order, Literal(order)))
    if deactivated:
        graph.add((shape_uri, SH.deactivated, Literal(True)))

    return shape_uri


@pytest.fixture
def dataset_store(monkeypatch):
    dataset = Dataset()
    store = DatasetBackedStore(dataset)
    monkeypatch.setitem(main.state, "prefix_map", {})
    return dataset, store


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entity_type",
    ["class", "datatype", "individual"],
)
async def test_node_shape_activation_and_deactivation_normalize_type_local_order(
    entity_type,
    dataset_store,
):
    dataset, store = dataset_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    first = f"http://example.org/{entity_type}/first"
    second = f"http://example.org/{entity_type}/second"
    third = f"http://example.org/{entity_type}/third"

    first_shape = add_node_shape(graph, entity_type, first, 1)
    second_shape = add_node_shape(graph, entity_type, second, 2)

    profile = main.SHACLProfile(store)

    await profile.deactivate_node_entities(entity_type, {first})

    assert set(graph.objects(first_shape, SH.deactivated)) == {Literal(True)}
    assert not list(graph.objects(first_shape, SH.order))
    assert set(graph.objects(second_shape, SH.order)) == {Literal(1)}

    await profile.activate_node_entities(entity_type, {first})

    assert not list(graph.objects(first_shape, SH.deactivated))
    assert set(graph.objects(first_shape, SH.order)) == {Literal(1)}
    assert set(graph.objects(second_shape, SH.order)) == {Literal(2)}

    await profile.activate_node_entities(entity_type, {third})

    third_shape = URIRef(
        main.shape_uri_for_entity(third, entity_type, {})
    )
    assert set(graph.objects(third_shape, SH.order)) == {Literal(1)}
    assert set(graph.objects(first_shape, SH.order)) == {Literal(2)}
    assert set(graph.objects(second_shape, SH.order)) == {Literal(3)}


@pytest.mark.asyncio
async def test_node_shape_ordering_sequences_are_independent(dataset_store):
    dataset, store = dataset_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    class_uri = str(EX.Book)
    datatype_uri = str(EX.ISBN)
    individual_uri = str(EX.Person)
    property_uri = str(EX.title)

    class_shape = add_node_shape(graph, "class", class_uri)
    datatype_shape = add_node_shape(graph, "datatype", datatype_uri)
    individual_shape = add_node_shape(graph, "individual", individual_uri)

    property_shape = URIRef(
        main.shape_uri_for_entity(property_uri, "property", {})
    )
    graph.add((property_shape, RDF.type, SH.PropertyShape))
    graph.add((property_shape, SH.path, URIRef(property_uri)))
    graph.add((property_shape, SH.group, main.PROPERTY_GROUP_OBJECT))
    graph.add((property_shape, SH.order, Literal(1)))

    profile = main.SHACLProfile(store)

    for entity_type, uri in (
        ("class", class_uri),
        ("datatype", datatype_uri),
        ("individual", individual_uri),
    ):
        await profile.activate_node_entities(entity_type, {uri})

    assert set(graph.objects(class_shape, SH.order)) == {Literal(1)}
    assert set(graph.objects(datatype_shape, SH.order)) == {Literal(1)}
    assert set(graph.objects(individual_shape, SH.order)) == {Literal(1)}
    assert set(graph.objects(property_shape, SH.order)) == {Literal(1)}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entity_type", "first", "second"),
    [
        ("class", str(EX.AClass), str(EX.BClass)),
        ("datatype", str(EX.ADatatype), str(EX.BDatatype)),
        ("individual", str(EX.AIndividual), str(EX.BIndividual)),
    ],
)
async def test_get_active_node_order_map_repairs_missing_orders(
    entity_type,
    first,
    second,
    dataset_store,
):
    dataset, store = dataset_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    first_shape = add_node_shape(graph, entity_type, first)
    second_shape = add_node_shape(graph, entity_type, second)

    profile = main.SHACLProfile(store)
    order_map = await profile.get_active_node_order_map(entity_type)

    assert order_map == {
        first: 1 if first < second else 2,
        second: 1 if second < first else 2,
    }
    assert set(graph.objects(first_shape, SH.order)) == {
        Literal(order_map[first])
    }
    assert set(graph.objects(second_shape, SH.order)) == {
        Literal(order_map[second])
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entity_type", "first", "second"),
    [
        ("class", str(EX.Book), str(EX.Article)),
        ("datatype", str(EX.ISBN), str(EX.ISSN)),
        ("individual", str(EX.Alice), str(EX.Bob)),
    ],
)
async def test_update_profile_order_reorders_one_complete_node_entity_type(
    entity_type,
    first,
    second,
    dataset_store,
    monkeypatch,
):
    dataset, store = dataset_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    first_shape = add_node_shape(graph, entity_type, first, 1)
    second_shape = add_node_shape(graph, entity_type, second, 2)

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main.shacl, "store", store)
    monkeypatch.setattr(main, "invalidate_profile", lambda: None)

    result = await main.update_profile_order({
        "entity_type": entity_type,
        "items": [
            {"uri": second, "order": 1},
            {"uri": first, "order": 2},
        ],
    })

    assert result == {"status": "ok"}
    assert set(graph.objects(second_shape, SH.order)) == {Literal(1)}
    assert set(graph.objects(first_shape, SH.order)) == {Literal(2)}

    ordered_entities = await main.shacl.get_active_node_order_map(
        entity_type
    )
    assert ordered_entities == {second: 1, first: 2}


@pytest.mark.asyncio
async def test_update_profile_order_rejects_incomplete_node_entity_type(
    dataset_store,
    monkeypatch,
):
    dataset, store = dataset_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))
    add_node_shape(graph, "class", str(EX.Book), 1)
    add_node_shape(graph, "class", str(EX.Article), 2)

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main.shacl, "store", store)

    with pytest.raises(HTTPException) as exc_info:
        await main.update_profile_order({
            "entity_type": "class",
            "items": [
                {"uri": str(EX.Book), "order": 1},
            ],
        })

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_application_profile_lists_node_entities_in_shacl_order(
    dataset_store,
    monkeypatch,
):
    dataset, store = dataset_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    class_a = str(EX.AClass)
    class_b = str(EX.BClass)
    datatype_a = str(EX.ADatatype)
    datatype_b = str(EX.BDatatype)
    individual_a = str(EX.AIndividual)
    individual_b = str(EX.BIndividual)

    add_node_shape(graph, "class", class_a, 2)
    add_node_shape(graph, "class", class_b, 1)
    add_node_shape(graph, "datatype", datatype_a, 2)
    add_node_shape(graph, "datatype", datatype_b, 1)
    add_node_shape(graph, "individual", individual_a, 2)
    add_node_shape(graph, "individual", individual_b, 1)

    monkeypatch.setattr(main.shacl, "store", store)
    monkeypatch.setitem(main.state, "ontologies", [])
    monkeypatch.setitem(main.state, "metadata_only_sources", {})
    monkeypatch.setattr(main, "_used_uris_set", set())
    monkeypatch.setattr(main, "rebuild_used_uris", AsyncMock())
    monkeypatch.setattr(main, "get_label", lambda uri: uri)
    monkeypatch.setattr(
        main,
        "_get_stored_labels",
        AsyncMock(return_value={}),
    )

    profile = main.ApplicationProfile(store)
    monkeypatch.setattr(
        profile,
        "_get_shacl_domains",
        AsyncMock(return_value={}),
    )

    entities = await profile.build_profile_entities()

    for entity_type, expected_uris in (
        ("class", [class_b, class_a]),
        ("datatype", [datatype_b, datatype_a]),
        ("individual", [individual_b, individual_a]),
    ):
        ordered_entities = [
            entity
            for entity in entities
            if entity.type == entity_type and entity.active
        ]

        assert [entity.uri for entity in ordered_entities] == expected_uris
        assert [entity.order for entity in ordered_entities] == [1, 2]

    assert await profile.get_active_classes() == [class_b, class_a]