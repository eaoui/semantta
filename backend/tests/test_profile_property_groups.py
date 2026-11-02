from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS
from rdflib import Literal

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


EX = Namespace("http://example.org/")


@pytest.mark.asyncio
async def test_property_groups_are_created_and_assigned_idempotently(
    fuseki_store,
    monkeypatch,
):
    ontology_graph = Graph()

    ontology_graph.add((
        EX.objectProperty,
        RDF.type,
        OWL.ObjectProperty,
    ))
    ontology_graph.add((
        EX.datatypeProperty,
        RDF.type,
        OWL.DatatypeProperty,
    ))
    ontology_graph.add((
        EX.annotationProperty,
        RDF.type,
        OWL.AnnotationProperty,
    ))

    monkeypatch.setitem(
        main.state,
        "combined_onto_graph",
        ontology_graph,
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

    properties = {
        str(EX.objectProperty),
        str(EX.datatypeProperty),
        str(EX.annotationProperty),
    }

    shapes = {
        prop_uri: URIRef(
            main.shape_uri_for_entity(
                prop_uri,
                "property",
                {},
            )
        )
        for prop_uri in properties
    }

    old_group = URIRef("urn:test:old-property-group")

    triples = []

    for prop_uri, shape_uri in shapes.items():
        triples.append(
            f"{shape_uri.n3()} "
            f"a {main.SH.PropertyShape.n3()} ; "
            f"{main.SH.path.n3()} "
            f"{URIRef(prop_uri).n3()} ."
        )

    # Verify that previous group memberships are replaced.
    triples.append(
        f"{shapes[str(EX.annotationProperty)].n3()} "
        f"{main.SH.group.n3()} {old_group.n3()} ."
    )

    await fuseki_store.insert_shapes(
        "\n".join(triples)
    )

    profile = main.SHACLProfile(fuseki_store)

    first_count = await profile._assign_property_groups(
        properties
    )

    assert first_count == 3

    graph = await fuseki_store.load_shapes_graph()

    expected_groups = {
        str(EX.objectProperty): main.PROPERTY_GROUP_OBJECT,
        str(EX.datatypeProperty): main.PROPERTY_GROUP_DATATYPE,
        str(EX.annotationProperty): main.PROPERTY_GROUP_ANNOTATION,
    }

    for prop_uri, expected_group in expected_groups.items():
        shape_uri = shapes[prop_uri]

        assert set(
            graph.objects(shape_uri, main.SH.group)
        ) == {expected_group}

    group_definitions = (
        (
            main.PROPERTY_GROUP_OBJECT,
            "Object Properties",
            1,
        ),
        (
            main.PROPERTY_GROUP_DATATYPE,
            "Datatype Properties",
            2,
        ),
        (
            main.PROPERTY_GROUP_ANNOTATION,
            "Annotation Properties",
            3,
        ),
    )

    for group_uri, label, order in group_definitions:
        assert (
            group_uri,
            RDF.type,
            main.SH.PropertyGroup,
        ) in graph

        assert (
            group_uri,
            RDFS.label,
            Literal(label, lang="en"),
        ) in graph

        assert (
            group_uri,
            main.SH.order,
            Literal(order),
        ) in graph

    assert (
        shapes[str(EX.annotationProperty)],
        main.SH.group,
        old_group,
    ) not in graph

    first_snapshot = set(graph)

    second_count = await profile._assign_property_groups(
        properties
    )

    assert second_count == 3

    second_graph = await fuseki_store.load_shapes_graph()

    assert set(second_graph) == first_snapshot


@pytest.mark.asyncio
async def test_add_property_global_assigns_ontology_type_group(
    fuseki_store,
    monkeypatch,
):
    property_uri = str(EX.title)

    ontology_graph = Graph()
    ontology_graph.add((
        EX.title,
        RDF.type,
        OWL.DatatypeProperty,
    ))

    monkeypatch.setitem(
        main.state,
        "combined_onto_graph",
        ontology_graph,
    )
    monkeypatch.setitem(
        main.state,
        "prefix_map",
        {},
    )

    profile = main.SHACLProfile(fuseki_store)

    monkeypatch.setattr(
        profile,
        "_set_default_constraints",
        AsyncMock(),
    )
    monkeypatch.setattr(
        main,
        "_reconcile_property_domain_links",
        AsyncMock(),
    )

    await profile.add_property_global(property_uri)

    graph = await fuseki_store.load_shapes_graph()

    shape_uri = URIRef(
        main.shape_uri_for_entity(
            property_uri,
            "property",
            {},
        )
    )

    assert (
        shape_uri,
        main.SH.group,
        main.PROPERTY_GROUP_DATATYPE,
    ) in graph

    assert (
        shape_uri,
        main.SH.order,
        Literal(0),
    ) in graph

    assert (
        shape_uri,
        main.SH.deactivated,
        Literal(True),
    ) not in graph


@pytest.mark.asyncio
async def test_add_property_to_class_assigns_ontology_type_group(
    fuseki_store,
    monkeypatch,
):
    property_uri = str(EX.author)
    class_uri = str(EX.Book)

    ontology_graph = Graph()
    ontology_graph.add((
        EX.author,
        RDF.type,
        OWL.ObjectProperty,
    ))

    monkeypatch.setitem(
        main.state,
        "combined_onto_graph",
        ontology_graph,
    )
    monkeypatch.setitem(
        main.state,
        "prefix_map",
        {},
    )

    profile = main.SHACLProfile(fuseki_store)

    monkeypatch.setattr(
        profile,
        "_set_default_constraints",
        AsyncMock(),
    )
    monkeypatch.setattr(
        main.ap,
        "_get_shacl_domains",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        main,
        "get_property_domains",
        lambda _: [],
    )
    monkeypatch.setattr(
        main,
        "_replace_property_domain_links",
        AsyncMock(),
    )
    monkeypatch.setattr(
        main,
        "_persist_profile_field_modes",
        AsyncMock(),
    )

    await profile.add_property_to_class(
        class_uri,
        property_uri,
    )

    graph = await fuseki_store.load_shapes_graph()

    shape_uri = URIRef(
        main.shape_uri_for_entity(
            property_uri,
            "property",
            {},
        )
    )

    assert (
        shape_uri,
        main.SH.group,
        main.PROPERTY_GROUP_OBJECT,
    ) in graph

    assert (
        shape_uri,
        main.SH.order,
        Literal(0),
    ) in graph