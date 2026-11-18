import sys
from pathlib import Path

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


EX = Namespace("https://example.org/validation-ontology-source-test/")
SH = Namespace("http://www.w3.org/ns/shacl#")


def test_asserted_type_copy_does_not_use_reasoned_combined_graph(
    monkeypatch,
):
    asserted_graph = Graph()
    asserted_graph.add((
        EX.CatalogedClass,
        RDF.type,
        OWL.Class,
    ))

    reasoned_graph = Graph()
    reasoned_graph += asserted_graph
    reasoned_graph.add((
        EX.CatalogedClass,
        RDF.type,
        OWL.NamedIndividual,
    ))

    monkeypatch.setitem(
        main.state,
        "ontologies",
        [{
            "filename": "test-ontology.ttl",
            "original_graph": asserted_graph,
        }],
    )
    monkeypatch.setitem(
        main.state,
        "combined_onto_graph",
        reasoned_graph,
    )

    result = Graph()

    main._add_asserted_ontology_types(
        result,
        {EX.CatalogedClass},
        owl_types_only=True,
    )

    assert (
        EX.CatalogedClass,
        RDF.type,
        OWL.Class,
    ) in result

    # The additional type exists only in the reasoned graph.
    assert (
        EX.CatalogedClass,
        RDF.type,
        OWL.NamedIndividual,
    ) not in result


def test_validation_ontology_override_resolution_preserves_annotation_ranges():
    profiles = {
        str(EX.objectProperty): {
            "type": "object_property",
            "original": {
                str(SH["class"]): [str(EX.ObjectRange)],
            },
            "field_modes": {
                "urn:domainClasses": main.PROFILE_FIELD_MODE_OVERRIDE,
                str(SH["class"]): main.PROFILE_FIELD_MODE_OVERRIDE,
            },
        },
        str(EX.datatypeProperty): {
            "type": "datatype_property",
            "original": {
                str(SH.datatype): [str(XSD.string)],
            },
            "field_modes": {
                str(SH.datatype): main.PROFILE_FIELD_MODE_OVERRIDE,
            },
        },
        str(EX.annotationProperty): {
            "type": "annotation_property",
            "original": {
                str(SH["class"]): [str(EX.AnnotationRange)],
                str(SH.datatype): [str(XSD.string)],
            },
            "field_modes": {
                str(SH["class"]): main.PROFILE_FIELD_MODE_OVERRIDE,
                str(SH.datatype): main.PROFILE_FIELD_MODE_DEFAULT,
            },
        },
    }

    overridden_domains, overridden_ranges = (
        main._get_validation_ontology_overrides(profiles)
    )

    assert overridden_domains == {
        EX.objectProperty,
    }

    # Object and datatype properties have a single applicable range field.
    assert overridden_ranges[EX.objectProperty] is None
    assert overridden_ranges[EX.datatypeProperty] is None

    # An annotation-property override suppresses only the selected range kind.
    assert overridden_ranges[EX.annotationProperty] == {
        str(EX.AnnotationRange),
    }

    source = Graph()
    source.add((
        EX.annotationProperty,
        RDFS.range,
        EX.AnnotationRange,
    ))
    source.add((
        EX.annotationProperty,
        RDFS.range,
        XSD.string,
    ))

    filtered = main._suppress_validation_ontology_overrides(
        source,
        set(),
        {
            EX.annotationProperty: {
                str(EX.AnnotationRange),
            },
        },
    )

    assert (
        EX.annotationProperty,
        RDFS.range,
        EX.AnnotationRange,
    ) not in filtered

    assert (
        EX.annotationProperty,
        RDFS.range,
        XSD.string,
    ) in filtered

    # Suppression operates on a copy.
    assert (
        EX.annotationProperty,
        RDFS.range,
        EX.AnnotationRange,
    ) in source


def test_overridden_property_preserves_superproperty_semantics(
    monkeypatch,
):
    ontology = Graph()

    properties = (
        EX.overriddenProperty,
        EX.inheritedProperty,
        EX.siblingProperty,
        EX.superProperty,
    )

    for property_uri in properties:
        ontology.add((
            property_uri,
            RDF.type,
            OWL.ObjectProperty,
        ))

    ontology.add((
        EX.overriddenProperty,
        RDFS.subPropertyOf,
        EX.superProperty,
    ))
    ontology.add((
        EX.inheritedProperty,
        RDFS.subPropertyOf,
        EX.superProperty,
    ))
    ontology.add((
        EX.siblingProperty,
        RDFS.subPropertyOf,
        EX.superProperty,
    ))

    # The selected property's direct ontology defaults will be overridden.
    ontology.add((
        EX.overriddenProperty,
        RDFS.domain,
        EX.LegacyDomain,
    ))
    ontology.add((
        EX.overriddenProperty,
        RDFS.range,
        EX.LegacyRange,
    ))

    # These superproperty declarations remain valid for its subproperties.
    ontology.add((
        EX.superProperty,
        RDFS.domain,
        EX.SuperDomain,
    ))
    ontology.add((
        EX.superProperty,
        RDFS.range,
        EX.SuperRange,
    ))

    original_triples = set(ontology)

    reasoned_ontology = Graph()
    reasoned_ontology += ontology

    monkeypatch.setitem(
        main.state,
        "ontologies",
        [{
            "filename": "test-ontology.ttl",
            "original_graph": ontology,
        }],
    )
    monkeypatch.setitem(
        main.state,
        "combined_onto_graph",
        reasoned_ontology,
    )
    monkeypatch.setattr(
        main,
        "validation_ontology_graph",
        Graph(),
    )

    main.rebuild_validation_ontology()

    # The shared asserted source contains schema relationships but does not
    # contain ontology-wide property-kind declarations.
    assert (
        EX.superProperty,
        RDFS.domain,
        EX.SuperDomain,
    ) in main.validation_ontology_graph

    assert (
        EX.overriddenProperty,
        RDF.type,
        OWL.ObjectProperty,
    ) not in main.validation_ontology_graph

    data_graph = Graph()
    instance = URIRef("urn:test:instance")

    data_graph.add((
        instance,
        RDF.type,
        EX.Work,
    ))
    data_graph.add((
        instance,
        EX.overriddenProperty,
        EX.overriddenValue,
    ))
    data_graph.add((
        instance,
        EX.inheritedProperty,
        EX.inheritedValue,
    ))
    data_graph.add((
        instance,
        EX.siblingProperty,
        EX.siblingValue,
    ))

    shapes_graph = Graph()
    node_shape = URIRef("urn:test:WorkShape")

    shapes_graph.add((
        node_shape,
        RDF.type,
        SH.NodeShape,
    ))
    shapes_graph.add((
        node_shape,
        SH.targetClass,
        EX.Work,
    ))

    for index, property_uri in enumerate(properties[:-1]):
        property_shape = URIRef(
            f"urn:test:PropertyShape{index}"
        )

        shapes_graph.add((
            node_shape,
            SH.property,
            property_shape,
        ))
        shapes_graph.add((
            property_shape,
            RDF.type,
            SH.PropertyShape,
        ))
        shapes_graph.add((
            property_shape,
            SH.path,
            property_uri,
        ))

    resolved_profiles = {
        str(EX.overriddenProperty): {
            "type": "object_property",
            "original": {
                str(SH["class"]): [str(EX.LegacyRange)],
            },
            "field_modes": {
                "urn:domainClasses": main.PROFILE_FIELD_MODE_OVERRIDE,
                str(SH["class"]): main.PROFILE_FIELD_MODE_OVERRIDE,
            },
        },
    }

    overridden_domains, overridden_ranges = (
        main._get_validation_ontology_overrides(
            resolved_profiles
        )
    )

    projected = main._build_validation_ontology_for_instance(
        data_graph,
        shapes_graph,
        overridden_domain_properties=overridden_domains,
        overridden_range_values=overridden_ranges,
    )

    # The selected property's own asserted defaults are suppressed.
    assert (
        EX.overriddenProperty,
        RDFS.domain,
        EX.LegacyDomain,
    ) not in projected

    assert (
        EX.overriddenProperty,
        RDFS.range,
        EX.LegacyRange,
    ) not in projected

    # Its subproperty relationship and property-kind declaration survive.
    assert (
        EX.overriddenProperty,
        RDFS.subPropertyOf,
        EX.superProperty,
    ) in projected

    assert (
        EX.overriddenProperty,
        RDF.type,
        OWL.ObjectProperty,
    ) in projected

    # The parent schema and the other subproperty relationships survive.
    assert (
        EX.superProperty,
        RDFS.domain,
        EX.SuperDomain,
    ) in projected

    assert (
        EX.superProperty,
        RDFS.range,
        EX.SuperRange,
    ) in projected

    assert (
        EX.inheritedProperty,
        RDFS.subPropertyOf,
        EX.superProperty,
    ) in projected

    assert (
        EX.siblingProperty,
        RDFS.subPropertyOf,
        EX.superProperty,
    ) in projected

    # Reason over a separate data-plus-ontology graph, as the validation
    # engine does when applying the ontology to the instance data.
    reasoned_validation_graph = Graph()
    reasoned_validation_graph += data_graph
    reasoned_validation_graph += projected

    main.apply_reasoning(reasoned_validation_graph)

    # The suppressed direct requirements must not reappear.
    assert (
        EX.overriddenProperty,
        RDFS.domain,
        EX.LegacyDomain,
    ) not in reasoned_validation_graph

    assert (
        EX.overriddenProperty,
        RDFS.range,
        EX.LegacyRange,
    ) not in reasoned_validation_graph

    assert (
        instance,
        RDF.type,
        EX.LegacyDomain,
    ) not in reasoned_validation_graph

    assert (
        EX.overriddenValue,
        RDF.type,
        EX.LegacyRange,
    ) not in reasoned_validation_graph

    # All three properties still inherit the valid parent domain and range.
    for value_uri in (
        EX.overriddenValue,
        EX.inheritedValue,
        EX.siblingValue,
    ):
        assert (
            instance,
            RDF.type,
            EX.SuperDomain,
        ) in reasoned_validation_graph

        assert (
            value_uri,
            RDF.type,
            EX.SuperRange,
        ) in reasoned_validation_graph

    # Neither projection nor reasoning mutated the uploaded ontology.
    assert set(ontology) == original_triples