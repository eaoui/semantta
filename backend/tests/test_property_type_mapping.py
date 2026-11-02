
from unittest.mock import AsyncMock

import pytest
from rdflib import Graph, Namespace
from rdflib.namespace import OWL, RDF, RDFS, XSD

import main


EX = Namespace("http://example.org/")


def make_ontology(graph, filename):
    return {
        "filename": filename,
        "graph": graph,
        "entities": main.process_ontology(
            graph,
            filename,
        ),
    }


def combined_graph(*graphs):
    result = Graph()

    for graph in graphs:
        for triple in graph:
            result.add(triple)

    return result


def set_type_registry_state(
    monkeypatch,
    ontologies,
    graph,
    metadata_types=None,
):
    monkeypatch.setitem(
        main.state,
        "ontologies",
        ontologies,
    )
    monkeypatch.setitem(
        main.state,
        "combined_onto_graph",
        graph,
    )
    monkeypatch.setitem(
        main.state,
        "ontology_property_type_map",
        {},
    )
    monkeypatch.setitem(
        main.state,
        "metadata_property_type_map",
        metadata_types or {},
    )
    monkeypatch.setitem(
        main.state,
        "property_type_map",
        {},
    )
    monkeypatch.setitem(
        main.state,
        "property_type_map_signature",
        None,
    )

    main._refresh_property_type_map()


def test_process_ontology_normalizes_conflicting_property_declarations():
    graph = Graph()

    graph.add((
        EX.conflictingProperty,
        RDF.type,
        OWL.ObjectProperty,
    ))
    graph.add((
        EX.conflictingProperty,
        RDF.type,
        OWL.DatatypeProperty,
    ))

    graph.add((
        EX.annotationConflict,
        RDF.type,
        OWL.AnnotationProperty,
    ))
    graph.add((
        EX.annotationConflict,
        RDF.type,
        OWL.ObjectProperty,
    ))

    graph.add((
        EX.genericProperty,
        RDF.type,
        RDF.Property,
    ))

    entities = main.process_ontology(
        graph,
        "test.ttl",
    )

    property_entities = [
        entity
        for entity in entities
        if entity["type"] in main.PROPERTY_ENTITY_TYPES
    ]

    property_types = {
        entity["uri"]: entity["type"]
        for entity in property_entities
    }

    assert property_types == {
        str(EX.conflictingProperty): "object_property",
        str(EX.annotationConflict): "annotation_property",
        str(EX.genericProperty): "annotation_property",
    }

    assert len(property_entities) == 3


def test_process_ontology_classification_is_independent_of_triple_order():
    triples = [
        (
            EX.property,
            RDF.type,
            OWL.ObjectProperty,
        ),
        (
            EX.property,
            RDF.type,
            OWL.DatatypeProperty,
        ),
        (
            EX.annotation,
            RDF.type,
            OWL.AnnotationProperty,
        ),
        (
            EX.annotation,
            RDF.type,
            OWL.ObjectProperty,
        ),
        (
            EX.generic,
            RDF.type,
            RDF.Property,
        ),
    ]

    first_graph = Graph()
    reversed_graph = Graph()

    for triple in triples:
        first_graph.add(triple)

    for triple in reversed(triples):
        reversed_graph.add(triple)

    first_result = {
        entity["uri"]: entity["type"]
        for entity in main.process_ontology(
            first_graph,
            "first.ttl",
        )
        if entity["type"] in main.PROPERTY_ENTITY_TYPES
    }

    reversed_result = {
        entity["uri"]: entity["type"]
        for entity in main.process_ontology(
            reversed_graph,
            "reversed.ttl",
        )
        if entity["type"] in main.PROPERTY_ENTITY_TYPES
    }

    assert first_result == reversed_result


def test_first_ontology_type_is_used_by_all_property_type_helpers(
    monkeypatch,
):
    first_graph = Graph()
    first_graph.add((
        EX.title,
        RDF.type,
        OWL.ObjectProperty,
    ))

    second_graph = Graph()
    second_graph.add((
        EX.title,
        RDF.type,
        OWL.DatatypeProperty,
    ))

    first_ontology = make_ontology(
        first_graph,
        "first.ttl",
    )
    second_ontology = make_ontology(
        second_graph,
        "second.ttl",
    )

    set_type_registry_state(
        monkeypatch,
        [first_ontology, second_ontology],
        combined_graph(first_graph, second_graph),
    )

    property_uri = str(EX.title)

    assert (
        main._get_property_entity_type(property_uri)
        == "object_property"
    )

    assert main._get_property_type(property_uri) == "object"

    assert not main._is_annotation_property(property_uri)

    assert (
        main._get_property_group_uri(property_uri)
        == main.PROPERTY_GROUP_OBJECT
    )


@pytest.mark.asyncio
async def test_profile_entity_type_uses_canonical_mapping(
    monkeypatch,
):
    first_graph = Graph()
    first_graph.add((
        EX.title,
        RDF.type,
        OWL.ObjectProperty,
    ))

    second_graph = Graph()
    second_graph.add((
        EX.title,
        RDF.type,
        OWL.DatatypeProperty,
    ))

    ontologies = [
        make_ontology(first_graph, "first.ttl"),
        make_ontology(second_graph, "second.ttl"),
    ]

    set_type_registry_state(
        monkeypatch,
        ontologies,
        combined_graph(first_graph, second_graph),
    )

    monkeypatch.setattr(
        main.shacl,
        "get_active_classes",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        main.shacl,
        "get_active_properties",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        main.shacl,
        "get_active_datatypes",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        main.shacl,
        "get_active_individuals",
        AsyncMock(return_value=[]),
    )

    monkeypatch.setattr(
        main,
        "_used_uris_set",
        set(),
    )
    monkeypatch.setattr(
        main,
        "rebuild_used_uris",
        AsyncMock(),
    )
    monkeypatch.setattr(
        main,
        "_get_stored_labels",
        AsyncMock(return_value={}),
    )

    profile = main.ApplicationProfile(
        store=AsyncMock(),
    )

    monkeypatch.setattr(
        profile,
        "_get_shacl_domains",
        AsyncMock(return_value={}),
    )

    entities = await profile.build_profile_entities()

    title = next(
        entity
        for entity in entities
        if entity.uri == str(EX.title)
    )

    assert title.type == "object_property"


def test_metadata_only_property_type_is_registered(
    monkeypatch,
):
    set_type_registry_state(
        monkeypatch,
        [],
        Graph(),
    )

    property_uri = str(EX.metadataProperty)

    main._register_metadata_property_types({
        property_uri: "datatype_property",
    })

    assert (
        main._get_property_entity_type(property_uri)
        == "datatype_property"
    )

    assert (
        main._get_property_type(property_uri)
        == "datatype"
    )

    assert (
        main._get_property_group_uri(property_uri)
        == main.PROPERTY_GROUP_DATATYPE
    )


def test_ontology_type_takes_precedence_over_metadata_type(
    monkeypatch,
):
    ontology_graph = Graph()
    ontology_graph.add((
        EX.property,
        RDF.type,
        OWL.ObjectProperty,
    ))

    ontology = make_ontology(
        ontology_graph,
        "ontology.ttl",
    )

    set_type_registry_state(
        monkeypatch,
        [ontology],
        ontology_graph,
    )

    main._register_metadata_property_types({
        str(EX.property): "datatype_property",
    })

    assert (
        main._get_property_entity_type(str(EX.property))
        == "object_property"
    )

    assert (
        main._get_property_group_uri(str(EX.property))
        == main.PROPERTY_GROUP_OBJECT
    )


def test_active_application_profile_datatype_refines_range_inference(
    monkeypatch,
):
    ontology_graph = Graph()

    ontology_graph.add((
        EX.property,
        RDFS.range,
        EX.CustomDatatype,
    ))

    set_type_registry_state(
        monkeypatch,
        [],
        ontology_graph,
    )

    active_datatypes = {
        str(EX.CustomDatatype),
    }

    assert (
        main._get_property_entity_type(
            str(EX.property),
            active_datatypes,
        )
        == "datatype_property"
    )

    assert (
        main._get_property_type(
            str(EX.property),
            active_datatypes,
        )
        == "datatype"
    )

    assert (
        main._get_property_group_uri(
            str(EX.property),
            active_datatypes,
        )
        == main.PROPERTY_GROUP_DATATYPE
    )


def test_annotation_property_keeps_annotation_group_with_datatype_range(
    monkeypatch,
):
    ontology_graph = Graph()

    ontology_graph.add((
        EX.label,
        RDF.type,
        OWL.AnnotationProperty,
    ))
    ontology_graph.add((
        EX.label,
        RDFS.range,
        XSD.string,
    ))

    ontology = make_ontology(
        ontology_graph,
        "annotation.ttl",
    )

    set_type_registry_state(
        monkeypatch,
        [ontology],
        ontology_graph,
    )

    assert (
        main._get_property_entity_type(str(EX.label))
        == "annotation_property"
    )

    # The value kind and the Application Profile property type remain distinct.
    assert (
        main._get_property_type(str(EX.label))
        == "datatype"
    )

    assert (
        main._get_property_group_uri(str(EX.label))
        == main.PROPERTY_GROUP_ANNOTATION
    )
