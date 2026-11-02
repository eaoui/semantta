
from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from rdflib import Dataset, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS
from rdflib.query import Result

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")


class DatasetBackedStore:
    """Minimal RDF store backed by RDFLib for profile lifecycle tests."""

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

    async def insert_shapes(self, triples: str) -> None:
        graph = self.dataset.graph(URIRef(main.SHAPES_GRAPH))
        graph.parse(
            data=(
                f'@prefix sh: <{SH}> .\n'
                f"@prefix rdfs: <{RDFS}> .\n"
                f"{triples}"
            ),
            format="turtle",
        )

    async def graph_exists(self, graph_uri: str) -> bool:
        return len(self.dataset.graph(URIRef(graph_uri))) > 0

    async def get_graph_stats(self, graph_uri: str) -> dict:
        graph = self.dataset.graph(URIRef(graph_uri))
        return {
            "triples": len(graph),
            "subjects": len(set(graph.subjects())),
        }


def add_shape(
    graph,
    role: str,
    entity_uri: str,
    *,
    deactivated: bool = False,
) -> URIRef:
    """Create a profile shape containing representative configuration."""
    shape_uri = URIRef(
        main.shape_uri_for_entity(entity_uri, role, {})
    )
    entity_ref = URIRef(entity_uri)

    if role == "class":
        graph.add((shape_uri, RDF.type, SH.NodeShape))
        graph.add((shape_uri, SH.targetClass, entity_ref))
        graph.add((shape_uri, SH.closed, Literal(True)))

    elif role == "property":
        graph.add((shape_uri, RDF.type, SH.PropertyShape))
        graph.add((shape_uri, SH.path, entity_ref))
        graph.add((shape_uri, SH.minCount, Literal(1)))
        graph.add((shape_uri, SH.order, Literal(4)))

    elif role in {"datatype", "individual"}:
        graph.add((shape_uri, RDF.type, SH.NodeShape))
        graph.add((shape_uri, SH.targetNode, entity_ref))
        graph.add((shape_uri, SH.nodeKind, SH.IRI))

    else:
        raise ValueError(f"Unsupported shape role: {role}")

    graph.add((shape_uri, RDFS.label, Literal(f"Preserved {role}")))

    # A false marker is valid SHACL and should be replaced by true
    # when the entity is deactivated.
    if deactivated:
        graph.add((shape_uri, SH.deactivated, Literal(False)))

    return shape_uri


def add_field_mode_record(
    dataset: Dataset,
    entity_uri: str,
    field_uri: str,
    mode: str = main.PROFILE_FIELD_MODE_OVERRIDE,
) -> URIRef:
    """Add a representative persisted profile field-mode record."""
    state_graph = dataset.graph(
        URIRef(main.PROFILE_FIELD_STATE_GRAPH)
    )

    record_uri = main._profile_field_state_uri(
        entity_uri,
        field_uri,
    )

    vocab = main.PROFILE_FIELD_STATE_VOCAB

    state_graph.add((
        record_uri,
        vocab.entity,
        URIRef(entity_uri),
    ))
    state_graph.add((
        record_uri,
        vocab.field,
        URIRef(field_uri),
    ))
    state_graph.add((
        record_uri,
        vocab.mode,
        Literal(mode),
    ))

    return record_uri


def without_deactivation_markers(graph) -> set:
    return {
        triple
        for triple in graph
        if triple[1] != SH.deactivated
    }


@pytest.fixture
def dataset_store():
    dataset = Dataset()
    return dataset, DatasetBackedStore(dataset)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "uri"),
    [
        ("class", str(EX.Book)),
        ("property", str(EX.title)),
        ("datatype", str(EX.CustomDatatype)),
        ("individual", str(EX.Person)),
    ],
)
async def test_deactivation_and_reactivation_preserve_complete_shapes(
    role,
    uri,
    dataset_store,
    monkeypatch,
):
    dataset, store = dataset_store

    shapes_graph = dataset.graph(URIRef(main.SHAPES_GRAPH))
    state_graph = dataset.graph(
        URIRef(main.PROFILE_FIELD_STATE_GRAPH)
    )

    monkeypatch.setitem(main.state, "prefix_map", {})

    # Add the entity shape.
    shape_uri = add_shape(
        shapes_graph,
        role,
        uri,
        deactivated=True,
    )

    # Preserve a class-property relationship when testing a property
    # or class shape.
    class_uri = str(EX.Book)
    property_uri = str(EX.title)

    class_shape = URIRef(
        main.shape_uri_for_entity(class_uri, "class", {})
    )
    property_shape = URIRef(
        main.shape_uri_for_entity(property_uri, "property", {})
    )

    if role == "class":
        # The class shape owns the association.
        shapes_graph.add((class_shape, RDF.type, SH.NodeShape))
        shapes_graph.add((class_shape, SH.targetClass, URIRef(uri)))
        shapes_graph.add((class_shape, SH.property, property_shape))
        shapes_graph.add((property_shape, RDF.type, SH.PropertyShape))
        shapes_graph.add((property_shape, SH.path, URIRef(property_uri)))

    elif role == "property":
        # A different active class references this property shape.
        shapes_graph.add((class_shape, RDF.type, SH.NodeShape))
        shapes_graph.add((class_shape, SH.targetClass, URIRef(class_uri)))
        shapes_graph.add((class_shape, SH.property, shape_uri))

    add_field_mode_record(
        dataset,
        uri,
        "urn:test:preserved-field",
    )

    original_shape_graph = without_deactivation_markers(shapes_graph)
    original_state_graph = set(state_graph)

    # Configure operations that are outside this lifecycle test.
    sync_domains = AsyncMock()
    monkeypatch.setattr(
        main,
        "_reconcile_property_domain_links",
        sync_domains,
    )

    profile = main.SHACLProfile(store)

    # Default initialization should not be part of property reactivation.
    # The test is specifically checking that existing configuration survives.
    monkeypatch.setattr(
        profile,
        "_set_default_constraints",
        AsyncMock(),
    )

    remove_methods = {
        "class": profile.remove_class,
        "property": profile.remove_property_global,
        "datatype": profile.remove_datatype,
        "individual": profile.remove_individual,
    }

    add_methods = {
        "class": profile.add_class,
        "property": profile.add_property_global,
        "datatype": profile.add_datatype,
        "individual": profile.add_individual,
    }

    await remove_methods[role](uri)

    expected_deactivated_graph = set(original_shape_graph)

    if role == "property":
        expected_deactivated_graph = {
            triple
            for triple in expected_deactivated_graph
            if not (
                triple[0] == shape_uri
                and triple[1] == SH.order
            )
        }

    # Property deactivation also removes its ordering value.
    assert without_deactivation_markers(shapes_graph) == (
        expected_deactivated_graph
    )

    assert set(state_graph) == original_state_graph

    assert set(shapes_graph.objects(
        shape_uri,
        SH.deactivated,
    )) == {Literal(True)}

    # Incoming class-property relationships must survive.
    if role == "property":
        assert (
            class_shape,
            SH.property,
            shape_uri,
        ) in shapes_graph

    if role == "class":
        assert (
            shape_uri,
            SH.property,
            property_shape,
        ) in shapes_graph

    # Reactivation must restore the existing shape, not reconstruct
    # its constraints or discard other RDF statements.
    await add_methods[role](uri)

    expected_shape_graph = set(original_shape_graph)

    if role == "property":
        expected_shape_graph = {
            triple
            for triple in expected_shape_graph
            if not (
                triple[0] == shape_uri
                and triple[1] == SH.order
            )
        }

    # Reactivated entities receive the first position in their own sequence.
    expected_shape_graph.add((
        shape_uri,
        SH.order,
        Literal(1),
    ))

    if role == "property":
        expected_group = main._get_property_group_uri(uri)

        expected_shape_graph.add((
            shape_uri,
            SH.group,
            expected_group,
        ))

        for group_uri, label, order in (
            main.PROPERTY_GROUP_DEFINITIONS
        ):
            expected_shape_graph.update({
                (
                    group_uri,
                    RDF.type,
                    SH.PropertyGroup,
                ),
                (
                    group_uri,
                    RDFS.label,
                    Literal(label, lang="en"),
                ),
                (
                    group_uri,
                    SH.order,
                    Literal(order),
                ),
            })

    assert without_deactivation_markers(shapes_graph) == (
        expected_shape_graph
    )

    assert not list(shapes_graph.objects(
        shape_uri,
        SH.deactivated,
    ))

    assert set(state_graph) == original_state_graph


@pytest.mark.asyncio
async def test_active_entity_queries_exclude_deactivated_shapes(
    dataset_store,
):
    dataset, store = dataset_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    active_entities = {
        "class": str(EX.ActiveClass),
        "property": str(EX.activeProperty),
        "datatype": str(EX.ActiveDatatype),
        "individual": str(EX.ActiveIndividual),
    }

    inactive_entities = {
        "class": str(EX.InactiveClass),
        "property": str(EX.inactiveProperty),
        "datatype": str(EX.InactiveDatatype),
        "individual": str(EX.InactiveIndividual),
    }

    for role in active_entities:
        add_shape(
            graph,
            role,
            active_entities[role],
        )
        inactive_shape = add_shape(
            graph,
            role,
            inactive_entities[role],
        )
        graph.add((
            inactive_shape,
            SH.deactivated,
            Literal(True),
        ))

    untyped_property = str(EX.untypedProperty)

    graph.add((
        URIRef("urn:test:untyped-property-shape"),
        SH.path,
        URIRef(untyped_property),
    ))

    profile = main.SHACLProfile(store)

    getters = {
        "class": profile.get_active_classes,
        "property": profile.get_active_properties,
        "datatype": profile.get_active_datatypes,
        "individual": profile.get_active_individuals,
    }

    for role, getter in getters.items():
        result = await getter()

        assert set(result) == {active_entities[role]}
        assert inactive_entities[role] not in result
        
    assert untyped_property not in await profile.get_active_properties()


@pytest.mark.asyncio
async def test_profile_form_property_list_excludes_deactivated_properties(
    dataset_store,
    monkeypatch,
):
    dataset, store = dataset_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    class_uri = str(EX.Book)
    active_property = str(EX.activeTitle)
    inactive_property = str(EX.inactiveTitle)

    add_shape(graph, "class", class_uri)

    active_shape = add_shape(
        graph,
        "property",
        active_property,
    )
    inactive_shape = add_shape(
        graph,
        "property",
        inactive_property,
    )

    graph.add((
        main.PROPERTY_GROUP_OBJECT,
        RDF.type,
        SH.PropertyGroup,
    ))
    graph.add((
        main.PROPERTY_GROUP_OBJECT,
        SH.order,
        Literal(1),
    ))

    graph.add((
        active_shape,
        SH.group,
        main.PROPERTY_GROUP_OBJECT,
    ))
    graph.add((
        inactive_shape,
        SH.group,
        main.PROPERTY_GROUP_OBJECT,
    ))
    graph.add((
        active_shape,
        SH.order,
        Literal(1),
    ))
    graph.add((
        inactive_shape,
        SH.order,Literal(2),
    ))
    graph.add((inactive_shape,
        SH.deactivated,
        Literal(True),
    ))

    profile = main.ApplicationProfile(store)

    # Isolate shape selection from domain resolution.
    monkeypatch.setattr(
        profile,
        "_get_shacl_domains",
        AsyncMock(return_value={
            active_property: [class_uri],
            inactive_property: [class_uri],
        }),
    )

    result = await profile._list_active_properties(class_uri)

    assert [item["uri"] for item in result] == [active_property]


@pytest.mark.asyncio
async def test_class_property_editor_rejects_deactivated_entities(
    dataset_store,
    monkeypatch,
):
    dataset, store = dataset_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    monkeypatch.setitem(main.state, "prefix_map", {})

    inactive_class = str(EX.InactiveClass)
    active_class = str(EX.ActiveClass)
    active_property = str(EX.activeProperty)
    inactive_property = str(EX.inactiveProperty)

    inactive_class_shape = add_shape(
        graph,
        "class",
        inactive_class,
    )
    add_shape(graph, "class", active_class)

    inactive_property_shape = add_shape(
        graph,
        "property",
        inactive_property,
    )
    add_shape(graph, "property", active_property)

    graph.add((
        inactive_class_shape,
        SH.deactivated,
        Literal(True),
    ))
    graph.add((
        inactive_property_shape,
        SH.deactivated,
        Literal(True),
    ))

    # An inactive class cannot be edited through the class-property
    # selector.
    with pytest.raises(HTTPException) as exc_info:
        await main._sync_entity_links(
            inactive_class,
            "class",
            [active_property],
            profile_store=store,
        )

    assert exc_info.value.status_code == 400

    # An inactive property cannot be associated with an active class.
    with pytest.raises(HTTPException) as exc_info:
        await main._sync_entity_links(
            active_class,
            "class",
            [inactive_property],
            profile_store=store,
        )

    assert exc_info.value.status_code == 400

    # Neither rejected operation should modify the shapes graph.
    assert store.update_calls == []


@pytest.mark.asyncio
async def test_domain_resolution_retains_links_to_deactivated_classes(
    dataset_store,
    monkeypatch,
):
    dataset, store = dataset_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    class_uri = str(EX.Book)
    property_uri = str(EX.title)

    class_shape = add_shape(
        graph,
        "class",
        class_uri,
    )
    property_shape = add_shape(
        graph,
        "property",
        property_uri,
    )

    graph.add((
        class_shape,
        SH.property,
        property_shape,
    ))
    graph.add((
        class_shape,
        SH.deactivated,
        Literal(True),
    ))

    add_field_mode_record(
        dataset,
        property_uri,
        "urn:domainClasses",
        main.PROFILE_FIELD_MODE_OVERRIDE,
    )

    monkeypatch.setattr(
        main,
        "get_property_domains",
        lambda _uri: [],
    )

    # Use an explicit store so the global Application Profile domain
    # cache cannot hide the result.
    effective_domains = await main.ap._get_shacl_domains(
        profile_store=store,
    )

    assert effective_domains[property_uri] == [class_uri]


@pytest.mark.asyncio
async def test_metadata_integration_status_excludes_deactivated_shapes(
    dataset_store,
    monkeypatch,
):
    dataset, store = dataset_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    active_class = str(EX.ActiveClass)
    inactive_property = str(EX.inactiveProperty)
    inactive_datatype = str(EX.InactiveDatatype)
    inactive_individual = str(EX.InactiveIndividual)

    add_shape(graph, "class", active_class)

    for role, uri in (
        ("property", inactive_property),
        ("datatype", inactive_datatype),
        ("individual", inactive_individual),
    ):
        shape = add_shape(graph, role, uri)
        graph.add((shape, SH.deactivated, Literal(True)))

    graph_uri = "urn:test:metadata-status"

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setitem(main.state, "ontologies", [])
    monkeypatch.setitem(
        main.state,
        "metadata_files",
        [{
            "filename": "status-test.ttl",
            "graph_uri": graph_uri,
        }],
    )
    monkeypatch.setitem(
        main.state,
        "metadata_graph_stats",
        {
            graph_uri: {
                "vocabulary_entities": {
                    "class": [active_class],
                    "property": [inactive_property],
                    "datatype": [inactive_datatype],
                    "individual": [inactive_individual],
                },
                "vocabulary_individuals_signature": (),
            }
        },
    )

    result = await main.get_metadata_integration_status()

    status = result["statuses"]["status-test.ttl"]

    assert status["required_count"] == 4
    assert status["missing_count"] == 3
    assert status["status"] == "not_integrated"


@pytest.mark.asyncio
async def test_reactivating_property_does_not_reset_existing_constraints(
    dataset_store,
    monkeypatch,
):
    dataset, store = dataset_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    monkeypatch.setitem(main.state, "prefix_map", {})

    prop_uri = str(EX.title)
    shape_uri = add_shape(graph, "property", prop_uri)

    graph.add((shape_uri, SH.pattern, Literal("^[A-Z]")))
    graph.add((shape_uri, SH.maxLength, Literal(100)))

    graph.add((shape_uri, SH.deactivated, Literal(True)))

    existing_constraints = {
        triple
        for triple in graph.triples((shape_uri, None, None))
            if triple[1] not in {
                RDF.type,
                SH.deactivated,
                SH.group,
                SH.order,
            }
    }

    profile = main.SHACLProfile(store)

    initialize_defaults = AsyncMock()
    synchronize_domains = AsyncMock()

    monkeypatch.setattr(
        profile,
        "_set_default_constraints",
        initialize_defaults,
    )
    monkeypatch.setattr(
        main,
        "_reconcile_property_domain_links",
        synchronize_domains,
    )

    await profile.add_property_global(prop_uri)

    restored_constraints = {
        triple
        for triple in graph.triples((shape_uri, None, None))
            if triple[1] not in {
                RDF.type,
                SH.deactivated,
                SH.group,
                SH.order,
            }
    }

    assert restored_constraints == existing_constraints

    assert set(
        graph.objects(shape_uri, SH.group)
    ) == {
        main._get_property_group_uri(prop_uri)
    }
    
    assert not list(graph.objects(
        shape_uri,
        SH.deactivated,
    ))

    assert set(
        graph.objects(shape_uri, SH.order)
    ) == {Literal(1)}

    initialize_defaults.assert_awaited_once_with(prop_uri)
    synchronize_domains.assert_awaited_once()


def prepare_property_type_map(monkeypatch, property_types):
    """Prepare the canonical property type mapping for lifecycle tests."""
    graph = Graph()

    declarations = {
        "object_property": OWL.ObjectProperty,
        "datatype_property": OWL.DatatypeProperty,
        "annotation_property": OWL.AnnotationProperty,
    }

    for uri, entity_type in property_types.items():
        graph.add((
            URIRef(uri),
            RDF.type,
            declarations[entity_type],
        ))

    monkeypatch.setitem(
        main.state,
        "combined_onto_graph",
        graph,
    )
    monkeypatch.setitem(
        main.state,
        "ontologies",
        [],
    )
    monkeypatch.setitem(
        main.state,
        "ontology_property_type_map",
        {},
    )
    monkeypatch.setitem(
        main.state,
        "metadata_property_type_map",
        {},
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


@pytest.mark.asyncio
async def test_property_activation_and_deactivation_maintain_group_order(
    dataset_store,
    monkeypatch,
):
    dataset, store = dataset_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    monkeypatch.setitem(
        main.state,
        "prefix_map",
        {},
    )

    object_first = str(EX.ObjectFirst)
    object_second = str(EX.ObjectSecond)
    datatype_property = str(EX.DatatypeProperty)

    prepare_property_type_map(
        monkeypatch,
        {
            object_first: "object_property",
            object_second: "object_property",
            datatype_property: "datatype_property",
        },
    )

    profile = main.SHACLProfile(store)

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

    def shape_for(uri):
        return URIRef(
            main.shape_uri_for_entity(
                uri,
                "property",
                {},
            )
        )

    def order_for(uri):
        values = set(
            graph.objects(
                shape_for(uri),
                SH.order,
            )
        )

        assert len(values) == 1

        return int(next(iter(values)))

    # Add the first object property.
    await profile.add_property_global(object_first)

    assert order_for(object_first) == 1

    # A newly added property is placed before existing group members.
    await profile.add_property_global(object_second)

    assert order_for(object_second) == 1
    assert order_for(object_first) == 2

    # Property ordering is independent across type groups.
    await profile.add_property_global(datatype_property)

    assert order_for(datatype_property) == 1

    assert (
        shape_for(datatype_property),
        SH.group,
        main.PROPERTY_GROUP_DATATYPE,
    ) in graph

    # Deactivation removes the order and closes the gap.
    await profile.remove_property_global(object_second)

    assert not list(
        graph.objects(
            shape_for(object_second),
            SH.order,
        )
    )

    assert set(
        graph.objects(
            shape_for(object_second),
            SH.deactivated,
        )
    ) == {Literal(True)}

    assert order_for(object_first) == 1
    assert order_for(datatype_property) == 1

    # Reactivation places the property at the top again.
    await profile.add_property_global(object_second)

    assert order_for(object_second) == 1
    assert order_for(object_first) == 2
    assert order_for(datatype_property) == 1

    # Adding an already-active property must not move it.
    await profile.add_property_global(object_first)

    assert order_for(object_second) == 1
    assert order_for(object_first) == 2

    assert not list(
        graph.objects(
            shape_for(object_second),
            SH.deactivated,
        )
    )


@pytest.mark.asyncio
async def test_batch_property_activation_and_deactivation_preserve_order(
    dataset_store,
    monkeypatch,
):
    dataset, store = dataset_store
    graph = dataset.graph(URIRef(main.SHAPES_GRAPH))

    monkeypatch.setitem(
        main.state,
        "prefix_map",
        {},
    )

    existing_first = str(EX.xExistingFirst)
    existing_second = str(EX.yExistingSecond)
    reactivated = str(EX.bReactivated)
    new_property = str(EX.aNewProperty)

    property_uris = {
        existing_first,
        existing_second,
        reactivated,
        new_property,
    }

    prepare_property_type_map(
        monkeypatch,
        {
            uri: "object_property"
            for uri in property_uris
        },
    )

    group_uri = main.PROPERTY_GROUP_OBJECT

    def shape_for(uri):
        return URIRef(
            main.shape_uri_for_entity(
                uri,
                "property",
                {},
            )
        )

    # Two properties are already active and ordered.
    for uri, order in (
        (existing_first, 4),
        (existing_second, 9),
    ):
        shape_uri = shape_for(uri)

        graph.add((shape_uri, RDF.type, SH.PropertyShape))
        graph.add((shape_uri, SH.path, URIRef(uri)))
        graph.add((shape_uri, SH.group, group_uri))
        graph.add((shape_uri, SH.order, Literal(order)))

    # This property is retained but deactivated.
    reactivated_shape = shape_for(reactivated)

    graph.add((
        reactivated_shape,
        RDF.type,
        SH.PropertyShape,
    ))
    graph.add((
        reactivated_shape,
        SH.path,
        URIRef(reactivated),
    ))
    graph.add((
        reactivated_shape,
        SH.group,
        group_uri,
    ))
    graph.add((
        reactivated_shape,
        SH.order,
        Literal(99),
    ))
    graph.add((
        reactivated_shape,
        SH.deactivated,
        Literal(True),
    ))

    profile = main.SHACLProfile(store)

    # Activate both a previously deactivated property and a new property.
    await profile.activate_properties({
        reactivated,
        new_property,
    })

    # Newly activated properties are prepended deterministically.
    expected_order = [
        new_property,
        reactivated,
        existing_first,
        existing_second,
    ]

    for order, uri in enumerate(expected_order, start=1):
        assert set(
            graph.objects(
                shape_for(uri),
                SH.order,
            )
        ) == {Literal(order)}

    for uri in (reactivated, new_property):
        assert (
            shape_for(uri),
            SH.group,
            group_uri,
        ) in graph

        assert not list(
            graph.objects(
                shape_for(uri),
                SH.deactivated,
            )
        )

    # Repeated activation must not alter the ordering.
    first_snapshot = set(graph)

    await profile.activate_properties({
        reactivated,
        new_property,
    })

    assert set(graph) == first_snapshot

    # Batch deactivation removes both orders and compacts the group.
    await profile.deactivate_properties({
        reactivated,
        new_property,
    })

    for uri in (reactivated, new_property):
        assert (
            shape_for(uri),
            SH.group,
            group_uri,
        ) in graph

        assert set(
            graph.objects(
                shape_for(uri),
                SH.deactivated,
            )
        ) == {Literal(True)}

        assert not list(
            graph.objects(
                shape_for(uri),
                SH.order,
            )
        )

    assert set(
        graph.objects(
            shape_for(existing_first),
            SH.order,
        )
    ) == {Literal(1)}

    assert set(
        graph.objects(
            shape_for(existing_second),
            SH.order,
        )
    ) == {Literal(2)}