from __future__ import annotations

import sys
from unittest.mock import AsyncMock
from collections.abc import Iterable
from pathlib import Path
from typing import cast

import pytest
from fastapi import HTTPException
from rdflib import Dataset, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS
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


@pytest.mark.asyncio
async def test_xsd_datatypes_are_not_misclassified_as_classes_during_ordering(
    dataset_store,
    monkeypatch,
):
    dataset, store = dataset_store
    shapes_graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    string_uri = "http://www.w3.org/2001/XMLSchema#string"
    datetime_uri = "http://www.w3.org/2001/XMLSchema#dateTime"

    # Simulate ontology reasoning that also identifies these datatype
    # resources as rdfs:Class.
    ontology_graph = Graph()

    for uri in (string_uri, datetime_uri):
        ontology_graph.add((
            URIRef(uri),
            RDF.type,
            RDFS.Class,
        ))

    ontology_entities = main.process_ontology(
        ontology_graph,
        "xsd-types.ttl",
    )

    extracted_types = {
        entity["uri"]: entity["type"]
        for entity in ontology_entities
    }

    assert extracted_types == {
        string_uri: "datatype",
        datetime_uri: "datatype",
    }

    add_node_shape(
        shapes_graph,
        "datatype",
        string_uri,
        1,
    )
    add_node_shape(
        shapes_graph,
        "datatype",
        datetime_uri,
        2,
    )

    monkeypatch.setattr(main.shacl, "store", store)
    monkeypatch.setitem(
        main.state,
        "ontologies",
        [{
            "filename": "xsd-types.ttl",
            "entities": ontology_entities,
            "graph": ontology_graph,
        }],
    )
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
    entities_by_uri = {
        entity.uri: entity
        for entity in entities
    }

    for uri, expected_order in (
        (string_uri, 1),
        (datetime_uri, 2),
    ):
        entity = entities_by_uri[uri]

        assert entity.type == "datatype"
        assert entity.active is True
        assert entity.order == expected_order

    # The complete datatype order submitted by the editor must be accepted.
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "invalidate_profile", lambda: None)

    result = await main.update_profile_order({
        "entity_type": "datatype",
        "items": [
            {"uri": datetime_uri, "order": 1},
            {"uri": string_uri, "order": 2},
        ],
    })

    assert result == {"status": "ok"}

    order_map = await main.shacl.get_active_node_order_map("datatype")

    assert order_map[string_uri] == 2
    assert order_map[datetime_uri] == 1


@pytest.mark.asyncio
async def test_ontology_entities_are_not_implicitly_activated_in_profile(
    dataset_store,
    monkeypatch,
):
    dataset, store = dataset_store
    shapes_graph = dataset.graph(URIRef(main.SHAPES_GRAPH))
    ontology_graph = Graph()

    entities_by_type = {
        "class": (str(EX.ActiveClass), str(EX.OntologyOnlyClass)),
        "datatype": (
            str(EX.ActiveDatatype),
            str(EX.OntologyOnlyDatatype),
        ),
        "individual": (
            str(EX.ActiveIndividual),
            str(EX.OntologyOnlyIndividual),
        ),
        "object_property": (
            str(EX.activeObjectProperty),
            str(EX.ontologyOnlyObjectProperty),
        ),
        "datatype_property": (
            str(EX.activeDatatypeProperty),
            str(EX.ontologyOnlyDatatypeProperty),
        ),
        "annotation_property": (
            str(EX.activeAnnotationProperty),
            str(EX.ontologyOnlyAnnotationProperty),
        ),
    }

    ontology_declarations = {
        "class": OWL.Class,
        "datatype": RDFS.Datatype,
        "individual": OWL.NamedIndividual,
        "object_property": OWL.ObjectProperty,
        "datatype_property": OWL.DatatypeProperty,
        "annotation_property": OWL.AnnotationProperty,
    }

    ontology_entities = []

    for entity_type, uris in entities_by_type.items():
        for uri in uris:
            ontology_entities.append({
                "uri": uri,
                "type": entity_type,
            })
            ontology_graph.add((
                URIRef(uri),
                RDF.type,
                ontology_declarations[entity_type],
            ))

    # Each already-activated node entity has an active NodeShape.
    for entity_type in ("class", "datatype", "individual"):
        active_uri, _ = entities_by_type[entity_type]
        add_node_shape(
            shapes_graph,
            entity_type,
            active_uri,
            1,
        )

    # Each already-activated property has a PropertyShape in its
    # corresponding property group.
    property_groups = {
        "object_property": main.PROPERTY_GROUP_OBJECT,
        "datatype_property": main.PROPERTY_GROUP_DATATYPE,
        "annotation_property": main.PROPERTY_GROUP_ANNOTATION,
    }

    for group_uri, _, group_order in main.PROPERTY_GROUP_DEFINITIONS:
        shapes_graph.add((group_uri, RDF.type, SH.PropertyGroup))
        shapes_graph.add((group_uri, SH.order, Literal(group_order)))

    for entity_type, group_uri in property_groups.items():
        active_uri, _ = entities_by_type[entity_type]
        shape_uri = URIRef(
            main.shape_uri_for_entity(active_uri, "property", {})
        )

        shapes_graph.add((shape_uri, RDF.type, SH.PropertyShape))
        shapes_graph.add((shape_uri, SH.path, URIRef(active_uri)))
        shapes_graph.add((shape_uri, SH.group, group_uri))
        shapes_graph.add((shape_uri, SH.order, Literal(1)))

    monkeypatch.setitem(
        main.state,
        "ontologies",
        [{
            "filename": "profile-membership-test.ttl",
            "entities": ontology_entities,
            "graph": ontology_graph,
        }],
    )
    monkeypatch.setitem(
        main.state,
        "combined_onto_graph",
        ontology_graph,
    )
    monkeypatch.setitem(main.state, "metadata_only_sources", {})
    monkeypatch.setitem(main.state, "metadata_property_type_map", {})

    monkeypatch.setattr(main.shacl, "store", store)
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

    shapes_before = set(shapes_graph)

    profile_entities = await profile.build_profile_entities()

    entities_by_uri = {
        entity.uri: entity
        for entity in profile_entities
    }

    for entity_type, (active_uri, ontology_only_uri) in entities_by_type.items():
        # Explicitly activated ontology entities are active.
        assert entities_by_uri[active_uri].type == entity_type
        assert entities_by_uri[active_uri].active is True

        # Ontology-only entities remain available but inactive.
        assert entities_by_uri[ontology_only_uri].type == entity_type
        assert entities_by_uri[ontology_only_uri].active is False

        shape_role = (
            "property"
            if entity_type in property_groups
            else entity_type
        )

        ontology_only_shape = URIRef(
            main.shape_uri_for_entity(
                ontology_only_uri,
                shape_role,
                {},
            )
        )

        # No SHACL shape is materialized for an entity that was
        # never activated in the Application Profile.
        assert not list(
            shapes_graph.triples((
                ontology_only_shape,
                None,
                None,
            ))
        )

    # Building the profile entity list must not mutate the shapes graph.
    assert set(shapes_graph) == shapes_before