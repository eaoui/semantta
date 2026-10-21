
import sys
from pathlib import Path
from typing import cast

import pytest
from fastapi import HTTPException
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


EX = Namespace("https://example.org/validation-test/")
SH = Namespace("http://www.w3.org/ns/shacl#")


class StaticShapeStore:
    """Minimal store for exercising SHACL validation without HTTP."""

    def __init__(self, shapes: Graph):
        self.shapes = shapes

    async def load_shapes_graph(self) -> Graph:
        return self.shapes


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
