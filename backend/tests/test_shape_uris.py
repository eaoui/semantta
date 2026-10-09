import sys
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, URIRef

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from utils import shape_uri_for_entity, migrate_shape_graph


SH = Namespace("http://www.w3.org/ns/shacl#")


def test_shape_uris_are_unique_for_duplicate_prefixes():
    prefix_map = {
        "http://one.example/": "ex",
        "http://two.example/": "ex",
    }

    first = shape_uri_for_entity(
        "http://one.example/Title",
        "property",
        prefix_map,
    )

    second = shape_uri_for_entity(
        "http://two.example/Title",
        "property",
        prefix_map,
    )

    assert first != second


def test_legacy_shape_migration_preserves_constraints():
    graph = Graph()

    old_property_shape = URIRef(
        "urn:shape:property:Title~ex"
    )

    first_property = URIRef(
        "http://one.example/Title"
    )
    second_property = URIRef(
        "http://two.example/Title"
    )

    first_class_shape = URIRef(
        "urn:shape:class:CatalogOne~ex"
    )
    second_class_shape = URIRef(
        "urn:shape:class:CatalogTwo~ex"
    )

    first_class = URIRef(
        "http://one.example/CatalogOne"
    )
    second_class = URIRef(
        "http://two.example/CatalogTwo"
    )

    graph.add((
        old_property_shape,
        RDF.type,
        SH.PropertyShape,
    ))
    graph.add((
        old_property_shape,
        SH.path,
        first_property,
    ))
    graph.add((
        old_property_shape,
        SH.path,
        second_property,
    ))
    graph.add((
        old_property_shape,
        SH.minCount,
        Literal(1),
    ))

    for class_shape, class_uri in (
        (first_class_shape, first_class),
        (second_class_shape, second_class),
    ):
        graph.add((class_shape, RDF.type, SH.NodeShape))
        graph.add((class_shape, SH.targetClass, class_uri))
        graph.add((
            class_shape,
            SH.property,
            old_property_shape,
        ))

    migrated, migrated_count, ambiguous_count = (
        migrate_shape_graph(graph)
    )

    new_first_property = URIRef(
        shape_uri_for_entity(
            str(first_property),
            "property",
            {},
        )
    )
    new_second_property = URIRef(
        shape_uri_for_entity(
            str(second_property),
            "property",
            {},
        )
    )

    assert migrated_count == 3
    assert ambiguous_count == 1

    assert set(
        migrated.objects(new_first_property, SH.path)
    ) == {first_property}

    assert set(
        migrated.objects(new_second_property, SH.path)
    ) == {second_property}

    assert set(
        migrated.objects(new_first_property, SH.minCount)
    ) == {Literal(1)}

    assert set(
        migrated.objects(new_second_property, SH.minCount)
    ) == {Literal(1)}

    # Existing class-to-property links are retained and rewritten.
    new_first_class_shape = URIRef(
        shape_uri_for_entity(str(first_class), "class", {})
    )
    assert set(
        migrated.objects(new_first_class_shape, SH.property)
    ) == {new_first_property, new_second_property}

    # The migration is idempotent.
    remigrated, count, ambiguous = migrate_shape_graph(migrated)

    assert count == 0
    assert ambiguous == 0
    assert set(remigrated) == set(migrated)