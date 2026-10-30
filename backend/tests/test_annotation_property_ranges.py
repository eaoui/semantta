from rdflib import BNode, Graph, URIRef, Literal
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, XSD
from unittest.mock import AsyncMock
import pytest

import main


@pytest.mark.asyncio
async def test_annotation_property_accepts_both_effective_range_kinds(
    monkeypatch,
):
    property_uri = "http://example.org/annotation"
    class_uri = "http://example.org/Person"

    profile = main.ApplicationProfile(
        store=AsyncMock(),
    )

    property_data = {
        "type": "annotation_property",
        "original": {},
        "overrides": {},
        "field_modes": {},
        "effective": {
            str(main.SH["class"]): [class_uri],
            str(main.SH.datatype): [str(XSD.string)],
        },
    }

    monkeypatch.setattr(
        profile,
        "_list_active_properties",
        AsyncMock(
            return_value=[{
                "uri": property_uri,
                "order": 1,
            }]
        ),
    )

    monkeypatch.setattr(
        main.shacl,
        "get_active_datatypes",
        AsyncMock(return_value=set()),
    )

    monkeypatch.setattr(
        main,
        "get_entity_constraints",
        AsyncMock(return_value=property_data),
    )

    monkeypatch.setattr(
        profile,
        "_get_property_constraints",
        AsyncMock(return_value={}),
    )

    monkeypatch.setattr(
        main,
        "get_property_cardinality",
        lambda *_: {
            "minCardinality": None,
            "maxCardinality": None,
        },
    )

    monkeypatch.setattr(
        main,
        "get_instance_suggestions",
        AsyncMock(return_value=[]),
    )

    result = await profile.get_properties_for_class(
        "http://example.org/Book"
    )

    assert len(result) == 1
    assert result[0]["type"] == "mixed"
    assert result[0]["ranges"] == [class_uri]
    assert result[0]["datatype"] == str(XSD.string)


def test_mixed_annotation_ranges_become_shacl_alternatives(
    monkeypatch,
):
    property_uri = URIRef("http://example.org/annotation")
    class_uri = URIRef("http://example.org/Person")
    property_shape = URIRef("urn:test:annotation-shape")
    focus_node = URIRef("urn:test:focus")

    source_shapes = Graph()
    source_shapes.add((
        property_shape,
        main.SH.path,
        property_uri,
    ))
    source_shapes.add((
        property_shape,
        main.SH["class"],
        class_uri,
    ))
    source_shapes.add((
        property_shape,
        main.SH.datatype,
        XSD.string,
    ))

    ontology = Graph()
    ontology.add((
        property_uri,
        RDF.type,
        OWL.AnnotationProperty,
    ))

    monkeypatch.setitem(
        main.state,
        "combined_onto_graph",
        ontology,
    )

    validation_shapes = main._build_instance_validation_shapes(
        source_shapes,
        focus_node,
    )

    # The source graph must remain unchanged.
    assert (
        property_shape,
        main.SH["class"],
        class_uri,
    ) in source_shapes

    assert (
        property_shape,
        main.SH.datatype,
        XSD.string,
    ) in source_shapes

    # The derived graph must replace the conjunction with sh:or.
    assert (
        property_shape,
        main.SH["class"],
        class_uri,
    ) not in validation_shapes

    assert (
        property_shape,
        main.SH.datatype,
        XSD.string,
    ) not in validation_shapes

    or_head = validation_shapes.value(
        property_shape,
        main.SH["or"],
    )

    assert or_head is not None

    alternatives = list(
        Collection(validation_shapes, or_head)
    )

    assert len(alternatives) == 2

    assert any(
        (branch, main.SH["class"], class_uri)
        in validation_shapes
        for branch in alternatives
    )

    assert any(
        (branch, main.SH.datatype, XSD.string)
        in validation_shapes
        for branch in alternatives
    )


@pytest.mark.asyncio
async def test_mixed_annotation_datatype_resolution_depends_on_value(
    monkeypatch,
):
    property_uri = "http://example.org/annotation"
    class_uri = URIRef("http://example.org/Person")

    ontology = Graph()
    ontology.add((
        URIRef(property_uri),
        RDF.type,
        OWL.AnnotationProperty,
    ))

    monkeypatch.setitem(
        main.state,
        "combined_onto_graph",
        ontology,
    )

    shapes_graph = Graph()
    property_shape = URIRef("urn:test:annotation-shape")

    shapes_graph.add((
        property_shape,
        main.SH.path,
        URIRef(property_uri),
    ))
    shapes_graph.add((
        property_shape,
        main.SH["class"],
        class_uri,
    ))
    shapes_graph.add((
        property_shape,
        main.SH.datatype,
        XSD.string,
    ))

    profile = main.SHACLProfile(
        store=AsyncMock(),
    )

    resource_datatype = await profile._property_datatype_from_shapes(
        shapes_graph,
        property_uri,
        value="https://example.org/person/1",
    )

    literal_datatype = await profile._property_datatype_from_shapes(
        shapes_graph,
        property_uri,
        value="A textual annotation",
    )

    assert resource_datatype is None
    assert literal_datatype == str(XSD.string)