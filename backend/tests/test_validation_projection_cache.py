import sys
from pathlib import Path
from unittest.mock import AsyncMock
from typing import cast

import pytest
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


EX = Namespace("https://example.org/validation-projection-cache-test/")
SH = Namespace("http://www.w3.org/ns/shacl#")


class StaticShapeStore:
    def __init__(self, shapes: Graph):
        self.shapes = shapes

    async def load_shapes_graph(self) -> Graph:
        return self.shapes

    async def query(self, sparql: str) -> list[dict]:
        return []

    async def construct(
        self,
        sparql: str,
        accept: str = "text/turtle",
    ) -> str:
        return ""


def make_shapes() -> Graph:
    graph = Graph()

    class_properties = {
        EX.Book: EX.title,
        EX.Person: EX.creator,
    }

    for class_uri, property_uri in class_properties.items():
        class_shape = URIRef(
            f"urn:test:{class_uri.split('/')[-1]}Shape"
        )
        property_shape = URIRef(
            f"urn:test:{property_uri.split('/')[-1]}Shape"
        )

        graph.add((class_shape, RDF.type, SH.NodeShape))
        graph.add((class_shape, SH.targetClass, class_uri))
        graph.add((class_shape, SH.property, property_shape))

        graph.add((property_shape, RDF.type, SH.PropertyShape))
        graph.add((property_shape, SH.path, property_uri))
        graph.add((property_shape, SH.datatype, XSD.string))

    return graph


@pytest.mark.asyncio
async def test_validation_projections_are_reused_by_revision_and_context(
    monkeypatch,
):
    shapes = make_shapes()
    profile = main.SHACLProfile(
        cast(main.RDFStore, StaticShapeStore(shapes))
    )

    monkeypatch.setitem(main.state, "ontologies", [])
    monkeypatch.setitem(main.state, "combined_onto_graph", Graph())
    monkeypatch.setitem(main.state, "ontology_revision", 0)
    monkeypatch.setitem(main.state, "profile_version", 0)

    monkeypatch.setitem(main.state, "metadata_property_type_map", {})
    monkeypatch.setitem(main.state, "ontology_property_type_map", {})
    monkeypatch.setitem(main.state, "property_type_map", {})
    monkeypatch.setitem(main.state, "property_type_map_signature", None)

    monkeypatch.setattr(main, "validation_ontology_graph", Graph())
    monkeypatch.setattr(main, "_subclass_pairs", set())

    monkeypatch.setattr(
        main,
        "_get_property_entity_type",
        lambda property_uri: "datatype_property",
    )

    monkeypatch.setattr(
        main.ap,
        "_get_shacl_domains",
        AsyncMock(
            return_value={
                str(EX.title): [str(EX.Book)],
                str(EX.creator): [str(EX.Person)],
            }
        ),
    )

    async def get_entity_constraints(
        entity_uri,
        entity_type,
        **kwargs,
    ):
        return {
            "type": entity_type,
            "original": {
                str(SH.datatype): [str(XSD.string)],
            },
            "effective": {
                str(SH.datatype): [str(XSD.string)],
            },
            "field_modes": {
                str(SH.datatype): main.PROFILE_FIELD_MODE_DEFAULT,
            },
        }

    monkeypatch.setattr(
        profile,
        "get_entity_constraints",
        get_entity_constraints,
    )

    counts = {
        "shapes": 0,
        "ontology": 0,
        "reasoning": 0,
        "validation": 0,
    }

    original_shapes_builder = (
        profile._build_validation_shapes_projection
    )

    async def counted_shapes_builder(*args, **kwargs):
        counts["shapes"] += 1
        return await original_shapes_builder(*args, **kwargs)

    monkeypatch.setattr(
        profile,
        "_build_validation_shapes_projection",
        counted_shapes_builder,
    )

    original_ontology_builder = (
        main._build_validation_ontology_for_instance
    )

    def counted_ontology_builder(*args, **kwargs):
        counts["ontology"] += 1
        return original_ontology_builder(*args, **kwargs)

    monkeypatch.setattr(
        main,
        "_build_validation_ontology_for_instance",
        counted_ontology_builder,
    )

    def counted_reasoning(graph):
        counts["reasoning"] += 1

    monkeypatch.setattr(
        main,
        "apply_reasoning",
        counted_reasoning,
    )

    def fake_validate(data_graph, **kwargs):
        counts["validation"] += 1
        return True, Graph(), "Conforms"

    monkeypatch.setattr(
        main.pyshacl,
        "validate",
        fake_validate,
    )

    main._clear_validation_projection_caches()
    main._SHACL_VALIDATION_SUCCESS_CACHE.clear()

    try:
        # Same class and property context: reuse both projections.
        assert await profile.validate_instance(
            [str(EX.Book)],
            {str(EX.title): ["First title"]},
        ) is True

        assert await profile.validate_instance(
            [str(EX.Book)],
            {str(EX.title): ["Second title"]},
        ) is True

        assert counts == {
            "shapes": 1,
            "ontology": 1,
            "reasoning": 1,
            "validation": 2,
        }

        # Different class and property context: build new projections.
        assert await profile.validate_instance(
            [str(EX.Person)],
            {str(EX.creator): ["First creator"]},
        ) is True

        assert counts == {
            "shapes": 2,
            "ontology": 2,
            "reasoning": 2,
            "validation": 3,
        }

        # A profile revision invalidates both projection caches.
        main.invalidate_profile()

        assert await profile.validate_instance(
            [str(EX.Book)],
            {str(EX.title): ["After profile revision"]},
        ) is True

        assert counts == {
            "shapes": 3,
            "ontology": 3,
            "reasoning": 3,
            "validation": 4,
        }

        # An ontology revision also invalidates both projection caches.
        main._increment_ontology_revision()

        assert await profile.validate_instance(
            [str(EX.Book)],
            {str(EX.title): ["After ontology revision"]},
        ) is True

        assert counts == {
            "shapes": 4,
            "ontology": 4,
            "reasoning": 4,
            "validation": 5,
        }

    finally:
        main._clear_validation_projection_caches()
        main._SHACL_VALIDATION_SUCCESS_CACHE.clear()


def test_projection_cache_keys_include_source_graphs(monkeypatch):
    shapes_one = make_shapes()
    shapes_two = Graph()
    shapes_two += shapes_one

    property_shape = next(
        shapes_two.subjects(SH.path, EX.title)
    )

    shapes_two.remove((
        property_shape,
        SH.datatype,
        XSD.string,
    ))
    shapes_two.add((
        property_shape,
        SH.datatype,
        XSD.integer,
    ))

    monkeypatch.setitem(main.state, "ontology_revision", 0)
    monkeypatch.setitem(main.state, "profile_version", 0)

    shapes_key_one = main._validation_shapes_projection_cache_key(
        shapes_one,
        [str(EX.Book)],
        URIRef("urn:temp:instance"),
    )
    shapes_key_two = main._validation_shapes_projection_cache_key(
        shapes_two,
        [str(EX.Book)],
        URIRef("urn:temp:instance"),
    )

    assert shapes_key_one != shapes_key_two

    data_graph = Graph()
    data_graph.add((
        URIRef("urn:temp:instance"),
        RDF.type,
        EX.Book,
    ))

    ontology = Graph()
    monkeypatch.setattr(
        main,
        "validation_ontology_graph",
        ontology,
    )

    ontology_key_one = (
        main._validation_ontology_projection_cache_key(
            data_graph,
            shapes_one,
        )
    )

    ontology.add((
        EX.Book,
        RDFS.subClassOf,
        EX.Entity,
    ))

    ontology_key_two = (
        main._validation_ontology_projection_cache_key(
            data_graph,
            shapes_one,
        )
    )

    assert ontology_key_one != ontology_key_two