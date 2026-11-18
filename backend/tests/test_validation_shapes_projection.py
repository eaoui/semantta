import sys
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import pytest
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import RDF, XSD

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


EX = Namespace("https://example.org/validation-projection-test/")
SH = Namespace("http://www.w3.org/ns/shacl#")

FOCUS_NODE = URIRef("urn:test:focus-node")


class ProjectionStore:
    def __init__(self, shapes: Graph):
        self.shapes = shapes

    async def load_shapes_graph(self) -> Graph:
        return self.shapes


def add_class_shape(
    graph: Graph,
    class_uri: URIRef,
    shape_uri: URIRef,
    *,
    deactivated: bool = False,
    property_shapes: tuple = (),
) -> None:
    graph.add((
        shape_uri,
        RDF.type,
        SH.NodeShape,
    ))
    graph.add((
        shape_uri,
        SH.targetClass,
        class_uri,
    ))

    if deactivated:
        graph.add((
            shape_uri,
            SH.deactivated,
            Literal(True),
        ))

    for property_shape in property_shapes:
        graph.add((
            shape_uri,
            SH.property,
            property_shape,
        ))


def add_property_shape(
    graph: Graph,
    property_uri: URIRef,
    shape_uri: URIRef,
    *,
    deactivated: bool = False,
    constraints: tuple = (),
) -> None:
    graph.add((
        shape_uri,
        RDF.type,
        SH.PropertyShape,
    ))
    graph.add((
        shape_uri,
        SH.path,
        property_uri,
    ))

    if deactivated:
        graph.add((
            shape_uri,
            SH.deactivated,
            Literal(True),
        ))

    for predicate, value in constraints:
        graph.add((
            shape_uri,
            predicate,
            value,
        ))


def make_profile(shapes: Graph) -> main.SHACLProfile:
    return main.SHACLProfile(
        cast(main.RDFStore, ProjectionStore(shapes))
    )


def install_projection_resolvers(
    monkeypatch,
    profile: main.SHACLProfile,
    domains: dict,
    *,
    effective_constraints: dict | None = None,
    field_modes: dict | None = None,
) -> None:
    monkeypatch.setattr(
        main.ap,
        "_get_shacl_domains",
        AsyncMock(return_value=domains),
    )

    monkeypatch.setattr(
        main,
        "_get_property_entity_type",
        lambda _: "object_property",
    )

    async def resolve_constraints(
        entity_uri,
        entity_type,
        **kwargs,
    ):
        return {
            "uri": entity_uri,
            "type": entity_type,
            "original": {},
            "overrides": {},
            "effective": effective_constraints or {},
            "field_modes": field_modes or {},
        }

    monkeypatch.setattr(
        profile,
        "get_entity_constraints",
        AsyncMock(side_effect=resolve_constraints),
    )


@pytest.mark.asyncio
async def test_projection_includes_only_active_applicable_shapes(
    monkeypatch,
):
    shapes = Graph()

    book_shape = URIRef("urn:test:BookShape")
    resource_shape = URIRef("urn:test:ResourceShape")
    person_shape = URIRef("urn:test:PersonShape")
    inactive_shape = URIRef("urn:test:InactiveDomainShape")

    title_shape = URIRef("urn:test:TitleShape")
    identifier_shape = URIRef("urn:test:IdentifierShape")
    person_property_shape = URIRef("urn:test:PersonPropertyShape")
    inactive_domain_shape = URIRef("urn:test:InactiveDomainPropertyShape")
    universal_shape = URIRef("urn:test:UniversalPropertyShape")
    deactivated_shape = URIRef("urn:test:DeactivatedPropertyShape")

    add_class_shape(
        shapes,
        EX.Book,
        book_shape,
        property_shapes=(
            title_shape,
            deactivated_shape,
        ),
    )
    add_class_shape(
        shapes,
        EX.Resource,
        resource_shape,
        property_shapes=(identifier_shape,),
    )
    add_class_shape(
        shapes,
        EX.Person,
        person_shape,
        property_shapes=(person_property_shape,),
    )
    add_class_shape(
        shapes,
        EX.InactiveDomain,
        inactive_shape,
        deactivated=True,
        property_shapes=(inactive_domain_shape,),
    )

    add_property_shape(
        shapes,
        EX.title,
        title_shape,
    )
    add_property_shape(
        shapes,
        EX.identifier,
        identifier_shape,
    )
    add_property_shape(
        shapes,
        EX.personProperty,
        person_property_shape,
    )
    add_property_shape(
        shapes,
        EX.inactiveDomainProperty,
        inactive_domain_shape,
    )
    add_property_shape(
        shapes,
        EX.universalProperty,
        universal_shape,
    )
    add_property_shape(
        shapes,
        EX.deactivatedProperty,
        deactivated_shape,
        deactivated=True,
    )

    original_triples = set(shapes)

    monkeypatch.setattr(
        main,
        "_subclass_pairs",
        {
            (str(EX.Book), str(EX.Resource)),
            (str(EX.Book), str(EX.InactiveDomain)),
        },
    )

    profile = make_profile(shapes)

    install_projection_resolvers(
        monkeypatch,
        profile,
        {
            str(EX.title): [str(EX.Book)],
            str(EX.identifier): [str(EX.Resource)],
            str(EX.personProperty): [str(EX.Person)],
            str(EX.inactiveDomainProperty): [
                str(EX.InactiveDomain)
            ],
            str(EX.universalProperty): [],
            str(EX.deactivatedProperty): [str(EX.Book)],
        },
    )

    resolved_property_profiles = {}

    projection = await profile._build_validation_shapes_projection(
        shapes,
        [str(EX.Book)],
        FOCUS_NODE,
        resolved_property_profiles,
    )

    assert set(resolved_property_profiles) == {
        str(EX.title),
        str(EX.identifier),
        str(EX.universalProperty),
    }

    # The selected class and its active superclass are retained.
    assert (
        book_shape,
        RDF.type,
        SH.NodeShape,
    ) in projection

    assert (
        resource_shape,
        RDF.type,
        SH.NodeShape,
    ) in projection

    # Unrelated and deactivated class shapes are excluded.
    assert (
        person_shape,
        RDF.type,
        SH.NodeShape,
    ) not in projection

    assert (
        inactive_shape,
        RDF.type,
        SH.NodeShape,
    ) not in projection

    # Direct and inherited properties are retained and linked correctly.
    assert (
        title_shape,
        RDF.type,
        SH.PropertyShape,
    ) in projection

    assert (
        identifier_shape,
        RDF.type,
        SH.PropertyShape,
    ) in projection

    assert (
        book_shape,
        SH.property,
        title_shape,
    ) in projection

    assert (
        resource_shape,
        SH.property,
        identifier_shape,
    ) in projection

    # Unrelated, inactive-domain, and deactivated properties are excluded.
    assert (
        person_property_shape,
        RDF.type,
        SH.PropertyShape,
    ) not in projection

    assert (
        inactive_domain_shape,
        RDF.type,
        SH.PropertyShape,
    ) not in projection

    assert (
        deactivated_shape,
        RDF.type,
        SH.PropertyShape,
    ) not in projection

    # The universal property is retained but is not linked to a class shape.
    assert (
        universal_shape,
        RDF.type,
        SH.PropertyShape,
    ) in projection

    assert not list(
        projection.subjects(
            SH.property,
            universal_shape,
        )
    )

    assert (
        universal_shape,
        SH.path,
        EX.universalProperty,
    ) in projection

    # Projection construction must not mutate the source graph.
    assert set(shapes) == original_triples

    # The existing instance builder attaches the universal shape
    # to this instance only.
    validation_shapes = main._build_instance_validation_shapes(
        projection,
        FOCUS_NODE,
    )

    instance_shapes = set(
        validation_shapes.subjects(
            SH.targetNode,
            FOCUS_NODE,
        )
    )

    # The selected class and its active superclass target this instance.
    assert book_shape in instance_shapes
    assert resource_shape in instance_shapes

    # The universal property is attached through one additional
    # instance-targeted NodeShape.
    universal_instance_shapes = {
        shape
        for shape in instance_shapes
        if (
            shape,
            SH.property,
            universal_shape,
        ) in validation_shapes
    }

    assert len(universal_instance_shapes) == 1

    universal_instance_shape = next(
        iter(universal_instance_shapes)
    )

    assert (
        universal_instance_shape,
        SH.targetNode,
        FOCUS_NODE,
    ) in validation_shapes

    assert (
        universal_instance_shape,
        SH.property,
        universal_shape,
    ) in validation_shapes

    assert (
        universal_instance_shape,
        SH.property,
        title_shape,
    ) not in validation_shapes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("list_mode", "expect_empty_list"),
    [
        (main.PROFILE_FIELD_MODE_OVERRIDE, True),
        (main.PROFILE_FIELD_MODE_DEFAULT, False),
    ],
)
async def test_projection_uses_effective_constraints_and_empty_list_mode(
    monkeypatch,
    list_mode,
    expect_empty_list,
):
    shapes = Graph()

    class_shape = URIRef("urn:test:BookShape")
    property_shape = URIRef("urn:test:TitleShape")

    add_class_shape(
        shapes,
        EX.Book,
        class_shape,
        property_shapes=(property_shape,),
    )

    original_list_head = BNode()

    add_property_shape(
        shapes,
        EX.title,
        property_shape,
        constraints=(
            (SH.minCount, Literal(1)),
        ),
    )

    Collection(
        shapes,
        original_list_head,
        [Literal("old")],
    )
    shapes.add((
        property_shape,
        SH["in"],
        original_list_head,
    ))

    original_triples = set(shapes)

    profile = make_profile(shapes)

    install_projection_resolvers(
        monkeypatch,
        profile,
        {
            str(EX.title): [str(EX.Book)],
        },
        effective_constraints={
            str(SH.minCount): "2",
            str(SH["in"]): [],
        },
        field_modes={
            str(SH.minCount): main.PROFILE_FIELD_MODE_OVERRIDE,
            str(SH["in"]): list_mode,
        },
    )

    projection = await profile._build_validation_shapes_projection(
        shapes,
        [str(EX.Book)],
    )

    # The effective minCount replaces the persisted value.
    assert list(
        projection.objects(
            property_shape,
            SH.minCount,
        )
    ) == [
        Literal("2", datatype=XSD.integer),
    ]

    # The persisted list is excluded from the projection.
    projected_list_values = list(
        projection.objects(
            property_shape,
            SH["in"],
        )
    )

    if expect_empty_list:
        assert projected_list_values == [RDF.nil]
    else:
        assert projected_list_values == []

    # The source graph, including its original constraints and RDF list,
    # must remain unchanged.
    assert set(shapes) == original_triples

    assert shapes.value(
        property_shape,
        SH.minCount,
    ) == Literal(1)

    assert list(
        Collection(shapes, original_list_head)
    ) == [Literal("old")]