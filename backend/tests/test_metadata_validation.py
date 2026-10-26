
import sys
from pathlib import Path
from typing import cast

import pytest
from fastapi import HTTPException
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from types import SimpleNamespace
from unittest.mock import AsyncMock

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


EX = Namespace("https://example.org/validation-test/")
SH = Namespace("http://www.w3.org/ns/shacl#")
OWL = Namespace("http://www.w3.org/2002/07/owl#")


class StaticShapeStore:
    """Minimal store for exercising SHACL validation without HTTP."""

    def __init__(self, shapes: Graph):
        self.shapes = shapes

    async def load_shapes_graph(self) -> Graph:
        return self.shapes


class ReferencedResourceStore(StaticShapeStore):
    """Static SHACL store with RDF descriptions of linked resources."""

    def __init__(
        self,
        shapes: Graph,
        referenced_graph: Graph,
    ):
        super().__init__(shapes)
        self.referenced_graph = referenced_graph

    async def construct(self, sparql: str) -> str:
        return self.referenced_graph.serialize(format="turtle")

    
def make_property_shape(
    target_class: URIRef,
    property_uri: URIRef,
    constraints: list[tuple],
) -> Graph:
    graph = Graph()
    class_shape = URIRef("urn:test:BookShape")
    property_shape = URIRef("urn:test:PropertyShape")

    graph.add((class_shape, RDF.type, SH.NodeShape))
    graph.add((class_shape, SH.targetClass, target_class))
    graph.add((class_shape, SH.property, property_shape))

    graph.add((property_shape, RDF.type, SH.PropertyShape))
    graph.add((property_shape, SH.path, property_uri))

    for predicate, value in constraints:
        graph.add((property_shape, predicate, value))

    return graph


def make_profile(shapes: Graph) -> main.SHACLProfile:
    store = cast(main.RDFStore, StaticShapeStore(shapes))
    return main.SHACLProfile(store)


def test_validation_ontology_rebuilds_when_index_cache_is_valid(
    monkeypatch,
):
    ontology = Graph()
    ontology.add((EX.Child, RDFS.subClassOf, EX.Parent))

    monkeypatch.setitem(
        main.state,
        "combined_onto_graph",
        ontology,
    )
    monkeypatch.setattr(
        main,
        "validation_ontology_graph",
        Graph(),
    )
    monkeypatch.setattr(
        main,
        "load_indexes",
        lambda: True,
    )

    main.rebuild_precomputed()

    assert (
        EX.Child,
        RDFS.subClassOf,
        EX.Parent,
    ) in main.validation_ontology_graph


@pytest.mark.asyncio
async def test_superclass_constraints_apply_to_subclass_instances(
    monkeypatch,
):
    shapes = make_property_shape(
        EX.Parent,
        EX.title,
        [(SH.minCount, Literal(1))],
    )

    ontology = Graph()
    ontology.add((EX.Child, RDFS.subClassOf, EX.Parent))

    monkeypatch.setattr(
        main,
        "validation_ontology_graph",
        ontology,
    )

    profile = make_profile(shapes)

    # A Child instance must satisfy the constraints targeting Parent.
    with pytest.raises(HTTPException) as exc_info:
        await profile.validate_instance(
            [str(EX.Child)],
            {},
        )

    assert exc_info.value.status_code == 400
    assert "SHACL validation failed" in exc_info.value.detail

    # The same subclass instance passes when the required property is present.
    assert await profile.validate_instance(
        [str(EX.Child)],
        {str(EX.title): ["A valid title"]},
    ) is True


@pytest.mark.asyncio
async def test_form_integer_value_is_validated_as_xsd_integer(
    monkeypatch,
):
    shapes = make_property_shape(
        EX.Book,
        EX.pageCount,
        [(SH.datatype, XSD.integer)],
    )

    monkeypatch.setattr(
        main,
        "validation_ontology_graph",
        Graph(),
    )

    profile = make_profile(shapes)

    # Values submitted by MetadataForm.vue arrive as strings.
    assert await profile.validate_instance(
        [str(EX.Book)],
        {str(EX.pageCount): ["42"]},
    ) is True

    with pytest.raises(HTTPException) as exc_info:
        await profile.validate_instance(
            [str(EX.Book)],
            {str(EX.pageCount): ["not-an-integer"]},
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_uri_looking_string_is_validated_as_literal(
    monkeypatch,
):
    shapes = make_property_shape(
        EX.Book,
        EX.homepage,
        [(SH.datatype, XSD.string)],
    )

    monkeypatch.setattr(
        main,
        "validation_ontology_graph",
        Graph(),
    )

    profile = make_profile(shapes)

    assert await profile.validate_instance(
        [str(EX.Book)],
        {
            str(EX.homepage): [
                "https://example.org/resource"
            ]
        },
    ) is True


@pytest.mark.asyncio
async def test_validation_does_not_validate_nested_resource_shapes(
    monkeypatch,
):
    shapes = Graph()

    work_shape = URIRef("urn:test:WorkShape")
    work_contribution_property = URIRef(
        "urn:test:WorkContributionProperty"
    )

    contribution_shape = URIRef("urn:test:ContributionShape")
    contribution_agent_property = URIRef(
        "urn:test:ContributionAgentProperty"
    )

    # The current form edits a Work instance. Its direct contribution
    # property requires the linked resource to be a Contribution.
    shapes.add((work_shape, RDF.type, SH.NodeShape))
    shapes.add((work_shape, SH.targetClass, EX.Work))
    shapes.add((work_shape, SH.property, work_contribution_property))

    shapes.add((
        work_contribution_property,
        RDF.type,
        SH.PropertyShape,
    ))
    shapes.add((work_contribution_property, SH.path, EX.contribution))
    shapes.add((
        work_contribution_property,
        SH["class"],
        EX.Contribution,
    ))

    # This shape belongs to the linked Contribution instance, not Work.
    # Its agent property is intentionally invalid.
    shapes.add((contribution_shape, RDF.type, SH.NodeShape))
    shapes.add((
        contribution_shape,
        SH.targetClass,
        EX.Contribution,
    ))
    shapes.add((
        contribution_shape,
        SH.property,
        contribution_agent_property,
    ))

    shapes.add((
        contribution_agent_property,
        RDF.type,
        SH.PropertyShape,
    ))
    shapes.add((contribution_agent_property, SH.path, EX.agent))
    shapes.add((
        contribution_agent_property,
        SH["class"],
        EX.Agent,
    ))

    contribution_node = URIRef("urn:bnid:test-contribution")
    agent_node = EX.untypedAgent

    referenced_graph = Graph()
    referenced_graph.add((
        contribution_node,
        RDF.type,
        EX.Contribution,
    ))
    referenced_graph.add((
        contribution_node,
        EX.agent,
        agent_node,
    ))

    store = ReferencedResourceStore(shapes, referenced_graph)
    profile = main.SHACLProfile(cast(main.RDFStore, store))

    monkeypatch.setattr(
        main,
        "validation_ontology_graph",
        Graph(),
    )

    # The direct Work -> Contribution class constraint still passes.
    # The nested Contribution -> Agent constraint must not be evaluated
    # while editing Work.
    assert await profile.validate_instance(
        [str(EX.Work)],
        {
            str(EX.contribution): [str(contribution_node)],
        },
    ) is True


@pytest.mark.asyncio
async def test_direct_object_property_class_constraint_is_still_enforced(
    monkeypatch,
):
    shapes = make_property_shape(
        EX.Work,
        EX.contribution,
        [(SH["class"], EX.Contribution)],
    )

    contribution_node = URIRef("urn:bnid:wrong-type-contribution")

    referenced_graph = Graph()
    referenced_graph.add((
        contribution_node,
        RDF.type,
        EX.Person,
    ))

    store = ReferencedResourceStore(shapes, referenced_graph)
    profile = main.SHACLProfile(cast(main.RDFStore, store))

    monkeypatch.setattr(
        main,
        "validation_ontology_graph",
        Graph(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await profile.validate_instance(
            [str(EX.Work)],
            {
                str(EX.contribution): [str(contribution_node)],
            },
        )

    assert exc_info.value.status_code == 400
    assert "SHACL validation failed" in exc_info.value.detail
    

@pytest.mark.asyncio
async def test_live_metadata_validation_runs_profile_and_shacl_checks(
    monkeypatch,
):
    class_uri = str(EX.Book)
    title_uri = str(EX.title)
    properties = {title_uri: ["A valid title"]}

    disjoint_check = AsyncMock()
    membership_check = AsyncMock()
    shacl_check = AsyncMock(return_value=True)

    monkeypatch.setattr(
        main,
        "check_disjoint_classes",
        disjoint_check,
    )
    monkeypatch.setattr(
        main,
        "_validate_metadata_profile_membership",
        membership_check,
    )
    monkeypatch.setattr(
        main,
        "shacl",
        SimpleNamespace(validate_instance=shacl_check),
    )

    result = await main.validate_metadata({
        "stage": "metadata",
        "class_uris": [class_uri],
        "properties": properties,
    })

    assert result == {"valid": True}
    disjoint_check.assert_awaited_once_with([class_uri])
    membership_check.assert_awaited_once_with(
        [class_uri],
        properties,
    )
    shacl_check.assert_awaited_once_with(
        [class_uri],
        properties,
    )


@pytest.mark.asyncio
async def test_live_class_selection_validation_skips_required_fields(
    monkeypatch,
):
    class_uri = str(EX.Book)

    disjoint_check = AsyncMock()
    membership_check = AsyncMock()
    shacl_check = AsyncMock(return_value=True)

    monkeypatch.setattr(
        main,
        "check_disjoint_classes",
        disjoint_check,
    )
    monkeypatch.setattr(
        main,
        "_validate_metadata_profile_membership",
        membership_check,
    )
    monkeypatch.setattr(
        main,
        "shacl",
        SimpleNamespace(validate_instance=shacl_check),
    )

    result = await main.validate_metadata({
        "stage": "selection",
        "class_uris": [class_uri],
        "properties": {},
    })

    assert result == {"valid": True}
    disjoint_check.assert_awaited_once_with([class_uri])
    membership_check.assert_awaited_once_with(
        [class_uri],
        {},
    )
    shacl_check.assert_not_awaited()


def test_property_type_recognizes_application_profile_datatypes(
    monkeypatch,
):
    ontology = Graph()

    # Generic literal-valued property.
    ontology.add((
        EX.label,
        RDFS.range,
        RDFS.Literal,
    ))

    # Custom datatype declared by the ontology.
    ontology.add((
        EX.ISBN,
        RDF.type,
        RDFS.Datatype,
    ))
    ontology.add((
        EX.isbn,
        RDFS.range,
        EX.ISBN,
    ))

    # Built-in XML Schema datatype.
    ontology.add((
        EX.pageCount,
        RDFS.range,
        XSD.integer,
    ))

    # Explicitly declared object property must remain an object property.
    ontology.add((
        EX.author,
        RDF.type,
        OWL.ObjectProperty,
    ))
    ontology.add((
        EX.author,
        RDFS.range,
        EX.Person,
    ))

    # A datatype known through the Application Profile inventory.
    ontology.add((
        EX.profileValue,
        RDFS.range,
        EX.ProfileDatatype,
    ))

    monkeypatch.setitem(
        main.state,
        "combined_onto_graph",
        ontology,
    )

    active_datatypes = {
        str(EX.ProfileDatatype),
    }

    assert main._get_property_type(str(EX.label)) == "datatype"
    assert main._get_property_type(str(EX.ISBN)) == "object"
    assert main._get_property_type(str(EX.isbn)) == "datatype"
    assert main._get_property_type(str(EX.pageCount)) == "datatype"
    assert main._get_property_type(
        str(EX.profileValue),
        active_datatypes,
    ) == "datatype"
    assert main._get_property_type(str(EX.author)) == "object"


@pytest.mark.asyncio
async def test_shacl_validation_error_identifies_property():
    property_uri = EX.agent
    required_class = EX.Agent

    shapes = make_property_shape(
        EX.Book,
        property_uri,
        [(SH["class"], required_class)],
    )
    profile = make_profile(shapes)

    with pytest.raises(HTTPException) as exc_info:
        await profile.validate_instance(
            [str(EX.Book)],
            {str(property_uri): ["not-a-resource"]},
        )

    assert exc_info.value.status_code == 400
    assert (
        f"The value of property <{property_uri}> "
        f"does not have class <{required_class}>"
    ) in exc_info.value.detail