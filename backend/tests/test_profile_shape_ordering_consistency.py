from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path
from typing import cast

import pytest
from rdflib import Dataset, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD
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
        source = self.dataset.graph(
            URIRef(main.SHAPES_GRAPH)
        )

        graph = Graph()

        for prefix, namespace in source.namespaces():
            graph.bind(prefix, namespace, replace=True)

        graph += source
        return graph


def add_node_shape(
    graph: Graph,
    entity_type: str,
    entity_uri: str,
    orders: tuple[Literal | int | str, ...] = (),
    *,
    inactive: bool = False,
) -> URIRef:
    shape_uri = URIRef(
        main.shape_uri_for_entity(
            entity_uri,
            entity_type,
            {},
        )
    )

    target_predicate = {
        "class": SH.targetClass,
        "datatype": SH.targetNode,
        "individual": SH.targetNode,
    }[entity_type]

    graph.add((shape_uri, RDF.type, SH.NodeShape))
    graph.add((shape_uri, target_predicate, URIRef(entity_uri)))

    for order in orders:
        value = order if isinstance(order, Literal) else Literal(order)
        graph.add((shape_uri, SH.order, value))

    if inactive:
        graph.add((
            shape_uri,
            SH.deactivated,
            Literal(True),
        ))

    return shape_uri


def add_property_shape(
    graph: Graph,
    property_uri: str,
    group_uri: URIRef,
    orders: tuple[Literal | int | str, ...] = (),
    *,
    inactive: bool = False,
) -> URIRef:
    shape_uri = URIRef(
        main.shape_uri_for_entity(
            property_uri,
            "property",
            {},
        )
    )

    graph.add((shape_uri, RDF.type, SH.PropertyShape))
    graph.add((shape_uri, SH.path, URIRef(property_uri)))
    graph.add((shape_uri, SH.group, group_uri))

    for order in orders:
        value = order if isinstance(order, Literal) else Literal(order)
        graph.add((shape_uri, SH.order, value))

    if inactive:
        graph.add((
            shape_uri,
            SH.deactivated,
            Literal(True),
        ))

    return shape_uri


@pytest.fixture
def dataset_store():
    dataset = Dataset()
    store = DatasetBackedStore(dataset)
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    for group_uri, _, group_order in main.PROPERTY_GROUP_DEFINITIONS:
        graph.add((group_uri, RDF.type, SH.PropertyGroup))
        graph.add((group_uri, SH.order, Literal(group_order)))

    return dataset, store, graph


def assert_shape_order(
    graph: Graph,
    shape_uri: URIRef,
    expected: int,
) -> None:
    orders = set(graph.objects(shape_uri, SH.order))

    assert orders == {Literal(expected)}

    order = next(iter(orders))
    
    assert isinstance(order, Literal)
    assert order.datatype == XSD.integer


@pytest.mark.asyncio
async def test_normalize_shape_ordering_covers_all_shapes_and_scopes(
    dataset_store,
):
    _, store, graph = dataset_store

    # NodeShapes: independent class, datatype, and individual scopes.
    class_first = add_node_shape(
        graph,
        "class",
        str(EX.ClassFirst),
        (2, 6),
    )
    class_second = add_node_shape(
        graph,
        "class",
        str(EX.ClassSecond),
        (1,),
    )
    class_missing = add_node_shape(
        graph,
        "class",
        str(EX.ClassMissing),
        (Literal("invalid", datatype=XSD.string),),
    )
    class_inactive = add_node_shape(
        graph,
        "class",
        str(EX.ClassInactive),
        (9,),
        inactive=True,
    )

    datatype_shape = add_node_shape(
        graph,
        "datatype",
        str(EX.ISBN),
        (5,),
    )
    individual_shape = add_node_shape(
        graph,
        "individual",
        str(EX.Alice),
        (1,),
    )

    # PropertyShapes: independent sequences within each property group.
    object_first = add_property_shape(
        graph,
        str(EX.objectFirst),
        main.PROPERTY_GROUP_OBJECT,
        (2, 6),
    )
    object_second = add_property_shape(
        graph,
        str(EX.objectSecond),
        main.PROPERTY_GROUP_OBJECT,
        (1,),
    )
    object_missing = add_property_shape(
        graph,
        str(EX.objectMissing),
        main.PROPERTY_GROUP_OBJECT,
    )
    object_inactive = add_property_shape(
        graph,
        str(EX.objectInactive),
        main.PROPERTY_GROUP_OBJECT,
        (8,),
        inactive=True,
    )

    datatype_first = add_property_shape(
        graph,
        str(EX.datatypeFirst),
        main.PROPERTY_GROUP_DATATYPE,
        (7,),
    )
    datatype_second = add_property_shape(
        graph,
        str(EX.datatypeSecond),
        main.PROPERTY_GROUP_DATATYPE,
        (3,),
    )
    annotation_shape = add_property_shape(
        graph,
        str(EX.annotationProperty),
        main.PROPERTY_GROUP_ANNOTATION,
        (9,),
    )

    # Ordinary shape configuration and links must remain untouched.
    graph.add((class_first, SH.closed, Literal(True)))
    graph.add((class_first, SH.property, object_first))
    graph.add((object_first, SH.minCount, Literal(1)))

    profile = main.SHACLProfile(store)

    await profile.normalize_shape_ordering()

    assert_shape_order(graph, class_second, 1)
    assert_shape_order(graph, class_first, 2)
    assert_shape_order(graph, class_missing, 3)
    assert not list(graph.objects(class_inactive, SH.order))

    assert_shape_order(graph, datatype_shape, 1)
    assert_shape_order(graph, individual_shape, 1)

    assert_shape_order(graph, object_second, 1)
    assert_shape_order(graph, object_first, 2)
    assert_shape_order(graph, object_missing, 3)
    assert not list(graph.objects(object_inactive, SH.order))

    assert_shape_order(graph, datatype_second, 1)
    assert_shape_order(graph, datatype_first, 2)
    assert_shape_order(graph, annotation_shape, 1)

    # Activation markers, property groups, links, and constraints are preserved.
    assert set(graph.objects(class_inactive, SH.deactivated)) == {
        Literal(True)
    }
    assert set(graph.objects(object_inactive, SH.deactivated)) == {
        Literal(True)
    }

    assert (class_first, SH.closed, Literal(True)) in graph
    assert (class_first, SH.property, object_first) in graph
    assert (object_first, SH.minCount, Literal(1)) in graph

    for group_uri, _, group_order in main.PROPERTY_GROUP_DEFINITIONS:
        assert (
            group_uri,
            SH.order,
            Literal(group_order),
        ) in graph

    # A second reconciliation must not change the graph.
    snapshot = set(graph)

    await profile.normalize_shape_ordering()

    assert set(graph) == snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_shape",
    [
        "unknown-node-role",
        "node-without-target",
        "property-without-group",
        "property-with-unsupported-group",
    ],
)
async def test_normalize_shape_ordering_rejects_unscoped_shapes(
    invalid_shape,
    dataset_store,
):
    _, store, graph = dataset_store

    shape_uri = URIRef("urn:test:invalid-shape")

    if invalid_shape == "unknown-node-role":
        graph.add((shape_uri, RDF.type, SH.NodeShape))
        graph.add((shape_uri, SH.targetClass, EX.Book))

    elif invalid_shape == "node-without-target":
        shape_uri = URIRef("urn:shape:class:invalid")
        graph.add((shape_uri, RDF.type, SH.NodeShape))

    elif invalid_shape == "property-without-group":
        graph.add((shape_uri, RDF.type, SH.PropertyShape))
        graph.add((shape_uri, SH.path, EX.title))

    else:
        graph.add((shape_uri, RDF.type, SH.PropertyShape))
        graph.add((shape_uri, SH.path, EX.title))
        graph.add((
            shape_uri,
            SH.group,
            URIRef("urn:test:unsupported-property-group"),
        ))

    snapshot = set(graph)
    profile = main.SHACLProfile(store)

    with pytest.raises(RuntimeError):
        await profile.normalize_shape_ordering()

    assert set(graph) == snapshot