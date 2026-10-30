
from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path
from typing import cast

import pytest
from rdflib import Dataset, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF
from rdflib.query import Result

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")
GRAPH_URI = main.metadata_graph_uri("cleanup-test.ttl")


class DatasetBackedStore:
    """Minimal RDF store backed by RDFLib for cleanup tests."""

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

    async def graph_exists(self, graph_uri: str) -> bool:
        return len(self.dataset.graph(URIRef(graph_uri))) > 0

    async def get_graph_stats(self, graph_uri: str) -> dict:
        graph = self.dataset.graph(URIRef(graph_uri))
        return {
            "triples": len(graph),
            "subjects": len(set(graph.subjects())),
        }


def add_active_shape(shapes_graph, role: str, uri: str) -> URIRef:
    shape_uri = URIRef(
        main.shape_uri_for_entity(uri, role, {})
    )
    entity_uri = URIRef(uri)

    if role == "class":
        shapes_graph.add((shape_uri, RDF.type, SH.NodeShape))
        shapes_graph.add((shape_uri, SH.targetClass, entity_uri))
    elif role == "property":
        shapes_graph.add((shape_uri, RDF.type, SH.PropertyShape))
        shapes_graph.add((shape_uri, SH.path, entity_uri))
    else:
        shapes_graph.add((shape_uri, RDF.type, SH.NodeShape))
        shapes_graph.add((shape_uri, SH.targetNode, entity_uri))

    return shape_uri


@pytest.mark.asyncio
async def test_deactivate_unused_entities_preserves_shapes_and_metadata(
    monkeypatch,
):
    dataset = Dataset()
    shapes_graph = dataset.graph(URIRef(main.SHAPES_GRAPH))
    imported_graph = dataset.graph(URIRef(GRAPH_URI))

    used_class = str(EX.UsedClass)
    created_class = str(EX.CreatedClass)
    unused_class = str(EX.UnusedClass)

    used_property = str(EX.UsedProperty)
    created_property = str(EX.CreatedProperty)
    created_datatype_property = str(EX.CreatedDatatypeProperty)
    unused_property = str(EX.UnusedProperty)

    used_datatype = str(EX.UsedDatatype)
    created_datatype = str(EX.CreatedDatatype)
    unused_datatype = str(EX.UnusedDatatype)

    used_individual = str(EX.UsedIndividual)
    created_individual = str(EX.CreatedIndividual)
    unused_individual = str(EX.UnusedIndividual)

    # Create active class shapes from several sources.
    class_shapes = {
        uri: add_active_shape(shapes_graph, "class", uri)
        for uri in (used_class, created_class, unused_class)
    }

    # Properties all have global property shapes. Their relationships
    # to the used class let the test verify dangling links are removed.
    property_shapes = {}
    for uri in (
        used_property,
        created_property,
        created_datatype_property,
        unused_property,
        *main.CORE_ACTIVE_ANNOTATION_PROPERTIES,
    ):
        shape = add_active_shape(shapes_graph, "property", uri)
        property_shapes[uri] = shape
        shapes_graph.add((
            class_shapes[used_class],
            SH.property,
            shape,
        ))

    for uri in (
        used_datatype,
        created_datatype,
        unused_datatype,
        *main.CORE_ACTIVE_DATATYPES,
    ):
        add_active_shape(shapes_graph, "datatype", uri)

    for uri in (
        used_individual,
        created_individual,
        unused_individual,
    ):
        add_active_shape(shapes_graph, "individual", uri)

    # Imported file: one class, property, datatype, and individual are used.
    imported_graph.add((
        EX.importedRecord,
        RDF.type,
        URIRef(used_class),
    ))
    imported_graph.add((
        EX.importedRecord,
        URIRef(used_property),
        Literal("imported value", datatype=URIRef(used_datatype)),
    ))
    imported_graph.add((
        URIRef(used_individual),
        RDF.type,
        OWL.NamedIndividual,
    ))

    # Semantta-created metadata is tracked in its own in-memory graph.
    # These entities are deliberately absent from the imported-file index.
    created_graph = Graph()
    created_graph.add((
        EX.createdRecord,
        RDF.type,
        URIRef(created_class),
    ))
    created_graph.add((
        EX.createdRecord,
        URIRef(created_property),
        URIRef(created_individual),
    ))
    created_graph.add((
        EX.createdRecord,
        URIRef(created_datatype_property),
        Literal("created value", datatype=URIRef(created_datatype)),
    ))

    field_state_graph = dataset.graph(
        URIRef(main.PROFILE_FIELD_STATE_GRAPH)
    )

    # These records must survive entity deactivation.
    field_state_records = []

    for entity_uri, field_uri in (
        (unused_class, str(main.SH.minCount)),
        (unused_property, "urn:domainClasses"),
    ):
        record_uri = main._profile_field_state_uri(
            entity_uri,
            field_uri,
        )

        vocab = main.PROFILE_FIELD_STATE_VOCAB

        field_state_graph.add((
            record_uri,
            vocab.entity,
            URIRef(entity_uri),
        ))
        field_state_graph.add((
            record_uri,
            vocab.field,
            URIRef(field_uri),
        ))
        field_state_graph.add((
            record_uri,
            vocab.mode,
            Literal(main.PROFILE_FIELD_MODE_OVERRIDE),
        ))

        field_state_records.append(record_uri)

    field_state_before = set(field_state_graph)
    shapes_before = set(shapes_graph)

    imported_before = set(imported_graph)
    created_before = set(created_graph)

    store = DatasetBackedStore(dataset)

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main.shacl, "store", store)
    monkeypatch.setitem(main.state, "ontologies", [])
    monkeypatch.setitem(main.state, "prefix_map", {})
    monkeypatch.setitem(main.state, "metadata_graph_stats", {})
    monkeypatch.setitem(
        main.state,
        "metadata_files",
        [{"filename": "cleanup-test.ttl", "graph_uri": GRAPH_URI}],
    )
    monkeypatch.setitem(
        main.state,
        "created_instances_graph",
        created_graph,
    )

    result = await main.deactivate_unused_entities_endpoint()

    assert result["status"] == "ok"
    assert result["deactivated_count"] == 4
    assert {
        (item["type"], item["uri"])
        for item in result["deactivated"]
    } == {
        ("class", unused_class),
        ("property", unused_property),
        ("datatype", unused_datatype),
        ("individual", unused_individual),
    }

    # The existing per-file vocabulary index was populated and used.
    indexed = main.state["metadata_graph_stats"][GRAPH_URI][
        "vocabulary_entities"
    ]
    assert used_class in indexed["class"]
    assert used_property in indexed["property"]
    assert used_datatype in indexed["datatype"]
    assert used_individual in indexed["individual"]

    # Imported-file entities and Semantta-created entities remain active.
    for uri in (used_class, created_class):
        assert list(shapes_graph.triples((
            class_shapes[uri],
            None,
            None,
        )))

    for uri in (
        used_property,
        created_property,
        created_datatype_property,
    ):
        assert list(shapes_graph.triples((
            property_shapes[uri],
            None,
            None,
        )))

    # All unused shapes remain in the shapes graph and are deactivated.
    unused_shapes = {
        ("class", unused_class),
        ("property", unused_property),
        ("datatype", unused_datatype),
        ("individual", unused_individual),
    }

    for role, uri in unused_shapes:
        shape_uri = URIRef(
            main.shape_uri_for_entity(uri, role, {})
        )

        assert list(shapes_graph.triples((
            shape_uri,
            None,
            None,
        )))

        assert set(shapes_graph.objects(
            shape_uri,
            SH.deactivated,
        )) == {Literal(True)}

    # The unused property's association with the class is retained.
    assert (
        class_shapes[used_class],
        SH.property,
        property_shapes[unused_property],
    ) in shapes_graph

    # No existing SHACL information was deleted or modified.
    # The only permitted changes are deactivation markers.
    assert {
        triple
        for triple in shapes_graph
        if triple[1] != SH.deactivated
    } == {
        triple
        for triple in shapes_before
        if triple[1] != SH.deactivated
    }

    # Field-mode state survives cleanup.
    assert set(field_state_graph) == field_state_before

    # Core defaults remain active even though this test doesn't use them.
    for uri in (
        *main.CORE_ACTIVE_DATATYPES,
        *main.CORE_ACTIVE_ANNOTATION_PROPERTIES,
    ):
        role = (
            "datatype"
            if uri in main.CORE_ACTIVE_DATATYPES
            else "property"
        )
        shape_uri = URIRef(main.shape_uri_for_entity(uri, role, {}))
        assert list(shapes_graph.triples((shape_uri, None, None)))

    # Neither imported metadata nor Semantta-created records were modified.
    assert set(imported_graph) == imported_before
    assert set(created_graph) == created_before

    # All selected entities are deactivated in one atomic update.
    assert len(store.update_calls) == 1
    assert f"GRAPH <{main.SHAPES_GRAPH}>" in store.update_calls[0]

    assert "sh:deactivated" in store.update_calls[0]


@pytest.mark.asyncio
async def test_index_failure_aborts_deactivation_without_mutation(monkeypatch):
    from unittest.mock import AsyncMock

    store = AsyncMock()
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(
        main,
        "get_metadata_integration_status",
        AsyncMock(side_effect=RuntimeError("Index unavailable")),
    )

    with pytest.raises(RuntimeError, match="Index unavailable"):
        await main.deactivate_unused_entities_endpoint()

    store.update.assert_not_awaited()
