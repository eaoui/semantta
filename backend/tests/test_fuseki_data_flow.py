
import io
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
from collections import defaultdict
from unittest.mock import AsyncMock
import pyshacl
from typing import Any, cast

from rdflib.collection import Collection
from rdflib.namespace import RDF, XSD

import pytest
from fastapi import HTTPException, UploadFile
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main
from fuseki_store import FusekiStore


EX = Namespace("https://example.org/test/")
SH = Namespace("http://www.w3.org/ns/shacl#")

BOOK = EX.Book
TITLE = EX.title


async def construct_graph(store, query):
    turtle = await store.construct(query)
    graph = Graph()

    if turtle.strip():
        graph.parse(data=turtle, format="turtle")

    return graph


@pytest.mark.asyncio
async def test_ontology_to_profile_to_metadata_persists_only_valid_data(
    fuseki_store,
    monkeypatch,
):
    store = fuseki_store

    # Construct a small domain ontology with a required title.
    ontology = Graph()
    ontology.add((BOOK, RDF.type, OWL.Class))
    ontology.add((TITLE, RDF.type, OWL.DatatypeProperty))
    ontology.add((TITLE, RDFS.domain, BOOK))
    ontology.add((TITLE, RDFS.range, XSD.string))

    restriction = BNode()
    ontology.add((BOOK, RDFS.subClassOf, restriction))
    ontology.add((restriction, RDF.type, OWL.Restriction))
    ontology.add((restriction, OWL.onProperty, TITLE))
    ontology.add((
        restriction,
        OWL.minCardinality,
        Literal(1, datatype=XSD.nonNegativeInteger),
    ))

    ontology.add((EX.pageCount, RDF.type, OWL.DatatypeProperty))
    ontology.add((EX.pageCount, RDFS.domain, BOOK))
    ontology.add((EX.pageCount, RDFS.range, XSD.integer))

    # Process the ontology using the production reasoning function.
    main.apply_reasoning(ontology)

    monkeypatch.setitem(main.state, "combined_onto_graph", ontology)
    monkeypatch.setitem(main.state, "prefix_map", {})
    monkeypatch.setattr(main, "store", store)

    # Rebuild the ontology indexes used to generate profile constraints.
    monkeypatch.setattr(main, "load_indexes", lambda: False)
    monkeypatch.setattr(main, "save_indexes", lambda: None)
    monkeypatch.setattr(main, "update_label_hierarchy", lambda: None)
    monkeypatch.setattr(main, "_property_domains", defaultdict(list))
    monkeypatch.setattr(main, "_property_ranges", defaultdict(list))
    monkeypatch.setattr(main, "_property_cardinalities", {})
    monkeypatch.setattr(main, "_subclass_pairs", set())
    monkeypatch.setattr(main, "_disjoint_pairs", set())

    main.rebuild_precomputed()

    profile = main.SHACLProfile(store)
    monkeypatch.setattr(main, "shacl", profile)

    # Generate and persist the Application Profile from ontology entities.
    await profile.add_class(str(BOOK))
    await profile.add_property_to_class(str(BOOK), str(TITLE))

    await profile.add_property_to_class(
        str(BOOK),
        str(EX.pageCount),
    )

    class_shape = URIRef(
        main.shape_uri_for_entity(str(BOOK), "class", {})
    )
    property_shape = URIRef(
        main.shape_uri_for_entity(str(TITLE), "property", {})
    )

    # Reload shapes from Fuseki instead of checking only the write request.
    persisted_shapes = await store.load_shapes_graph()

    assert (class_shape, SH.targetClass, BOOK) in persisted_shapes
    assert (class_shape, SH.property, property_shape) in persisted_shapes
    assert (property_shape, SH.path, TITLE) in persisted_shapes
    assert (property_shape, SH.minCount, Literal(1)) in persisted_shapes
    assert (property_shape, SH.datatype, XSD.string) in persisted_shapes

    monkeypatch.setattr(
        main, "check_disjoint_classes", AsyncMock()
    )
    monkeypatch.setattr(main, "save_created_instances", lambda: None)
    monkeypatch.setattr(main, "invalidate_instance_count", lambda: None)
    monkeypatch.setattr(main, "invalidate_profile", lambda: None)
    monkeypatch.setitem(main.state, "created_instances", set())
    monkeypatch.setitem(main.state, "created_instances_graph", Graph())

    invalid_uri = str(EX.invalidBook)

    probe = Graph()
    probe.add((EX.invalidBook, RDF.type, BOOK))

    conforms, _, report_text = pyshacl.validate(
        probe,
        shacl_graph=persisted_shapes,
        ont_graph=main.validation_ontology_graph,
        inference="owlrl",
    )

    assert not conforms, report_text

    # Invalid metadata must fail without adding anything to the default graph.
    with pytest.raises(HTTPException) as exc_info:
        await main.create_instance({
            "class_uris": [str(BOOK)],
            "instance_uri": invalid_uri,
            "properties": {
                str(TITLE): ["A valid title"],
                str(EX.pageCount): ["42"],
            },
        })

    assert exc_info.value.status_code == 400
    assert "SHACL validation failed" in exc_info.value.detail
    assert not await store.query(
        f"SELECT ?p ?o WHERE {{ <{invalid_uri}> ?p ?o }}"
    )

    # Valid metadata must be persisted as RDF triples.
    valid_uri = str(EX.validBook)

    result = await main.create_instance({
        "class_uris": [str(BOOK)],
        "instance_uri": valid_uri,
        "properties": {str(TITLE): ["A valid title"]},
    })

    assert result == {"status": "created", "uri": valid_uri}

    default_graph = await construct_graph(
        store,
        "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
    )

    expected = Graph()
    expected.add((URIRef(valid_uri), RDF.type, BOOK))
    expected.add((
        URIRef(valid_uri),
        TITLE,
        Literal("A valid title", datatype=XSD.string),
    ))

    expected.add((
        URIRef(valid_uri),
        EX.pageCount,
        Literal("42", datatype=XSD.integer),
    ))

    assert set(default_graph) == set(expected)
    assert set(main.state["created_instances_graph"]) == set(expected)


@pytest.mark.asyncio
async def test_default_graph_is_exact_union_of_registered_sources_and_created_instances(
    fuseki_store,
    monkeypatch,
):
    store = fuseki_store

    graph_a = main.metadata_graph_uri("flow-a.ttl")
    graph_b = main.metadata_graph_uri("flow-b.ttl")
    unregistered_graph = "urn:test:unregistered-source"

    a_triple = (EX.bookA, TITLE, Literal("A"))
    b_triple = (EX.bookB, TITLE, Literal("B"))
    unrelated_triple = (EX.orphan, TITLE, Literal("Unregistered"))
    created_triple = (EX.createdBook, TITLE, Literal("Created"))

    await store.update(f"""
        INSERT DATA {{
            GRAPH <{graph_a}> {{ <{a_triple[0]}> <{a_triple[1]}> "A" . }}
            GRAPH <{graph_b}> {{ <{b_triple[0]}> <{b_triple[1]}> "B" . }}
            GRAPH <{unregistered_graph}> {{
                <{unrelated_triple[0]}> <{unrelated_triple[1]}> "Unregistered" .
            }}
        }}
    """)

    created_graph = Graph()
    created_graph.add(created_triple)

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setitem(
        main.state,
        "metadata_files",
        [
            {"filename": "flow-a.ttl", "graph_uri": graph_a},
            {"filename": "flow-b.ttl", "graph_uri": graph_b},
        ],
    )
    monkeypatch.setitem(main.state, "created_instances_graph", created_graph)

    await main.rebuild_default_data_graph()

    default_graph = await construct_graph(
        store,
        "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
    )

    expected = {a_triple, b_triple, created_triple}

    assert set(default_graph) == expected
    assert unrelated_triple not in default_graph


@pytest.mark.asyncio
async def test_metadata_replacement_updates_named_and_default_graphs_without_losing_shapes(
    fuseki_store,
    monkeypatch,
    tmp_path,
):
    store = fuseki_store

    filename = "replacement-case.ttl"
    target_graph = main.metadata_graph_uri(filename)
    other_graph = main.metadata_graph_uri("other-case.ttl")

    old_triple = (EX.oldBook, TITLE, Literal("Old title"))
    other_triple = (EX.otherBook, TITLE, Literal("Keep this record"))

    await store.update(f"""
        INSERT DATA {{
            GRAPH <{target_graph}> {{
                <{old_triple[0]}> <{old_triple[1]}> "Old title" .
            }}
            GRAPH <{other_graph}> {{
                <{other_triple[0]}> <{other_triple[1]}> "Keep this record" .
            }}
            <{EX.staleDefault}> <{TITLE}> "Must not survive rebuilding" .
        }}
    """)

    # The metadata upload must not overwrite the separate SHACL graph
    # when vocabulary integration is disabled.
    await store.insert_shapes(f"""
        <urn:test:PreservedShape> a sh:NodeShape ;
            sh:targetClass <{BOOK}> .
    """)
    shapes_before = set(await store.load_shapes_graph())

    old_payload = f'@prefix ex: <{EX}> .\nex:oldBook ex:title "Old title" .\n'
    (tmp_path / filename).write_text(old_payload, encoding="utf-8")

    new_payload = (
        f'@prefix ex: <{EX}> .\n'
        'ex:newBook a ex:Book ; ex:title "New title" .\n'
    ).encode("utf-8")

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "METADATA_DIR", tmp_path)
    monkeypatch.setattr(main, "rebuild_used_uris", AsyncMock())
    monkeypatch.setattr(main, "invalidate_caches", lambda: None)
    monkeypatch.setattr(main.ap, "invalidate", lambda: None)

    monkeypatch.setitem(
        main.state,
        "ontologies",
        [{"filename": "test-ontology.ttl"}],
    )
    monkeypatch.setitem(
        main.state,
        "metadata_files",
        [
            {"filename": "other-case.ttl", "graph_uri": other_graph},
            {"filename": filename, "graph_uri": target_graph},
        ],
    )
    monkeypatch.setitem(main.state, "metadata_only_sources", {})
    monkeypatch.setitem(main.state, "metadata_graph_stats", {})
    monkeypatch.setitem(main.state, "created_instances_graph", Graph())

    result = await main.upload_metadata(
        file=UploadFile(
            file=io.BytesIO(new_payload),
            filename=filename,
        ),
        integrate_vocab=False,
    )

    assert result == {"status": "ok", "filename": filename}
    assert (tmp_path / filename).read_bytes() == new_payload

    uploaded_graph = Graph()
    uploaded_graph.parse(data=new_payload.decode("utf-8"), format="turtle")

    stored_metadata = await construct_graph(
        store,
        f"""
        CONSTRUCT {{ ?s ?p ?o }}
        WHERE {{ GRAPH <{target_graph}> {{ ?s ?p ?o }} }}
        """,
    )
    assert set(stored_metadata) == set(uploaded_graph)
    assert old_triple not in stored_metadata

    other_expected = {other_triple}
    default_graph = await construct_graph(
        store,
        "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
    )

    assert set(default_graph) == set(uploaded_graph) | other_expected
    assert (EX.staleDefault, TITLE, Literal("Must not survive rebuilding")) not in default_graph

    assert set(await store.load_shapes_graph()) == shapes_before

    staging_graphs = await store.query("""
        SELECT DISTINCT ?g
        WHERE {
            GRAPH ?g { ?s ?p ?o }
            FILTER(STRSTARTS(STR(?g), "urn:semantta:staging:"))
        }
    """)
    assert staging_graphs == []

@pytest.mark.asyncio
async def test_persisted_shapes_graph_conforms_to_meta_shacl(
    fuseki_store,
):
    await fuseki_store.insert_shapes(f"""
        <urn:test:BookShape>
            a sh:NodeShape ;
            sh:targetClass <{EX.Book}> ;
            sh:property <urn:test:TitleShape> .

        <urn:test:TitleShape>
            a sh:PropertyShape ;
            sh:path <{EX.title}> ;
            sh:datatype <{XSD.string}> ;
            sh:minCount 1 .
    """)

    shapes = await fuseki_store.load_shapes_graph()

    conforms, _, report_text = pyshacl.validate(
        Graph(),
        shacl_graph=shapes,
        meta_shacl=True,
        inference="none",
    )

    assert conforms, report_text

@pytest.mark.asyncio
async def test_object_property_uses_types_of_existing_references(
    fuseki_store,
    monkeypatch,
):
    node_shape = URIRef("urn:test:BookShape")
    property_shape = URIRef("urn:test:AuthorShape")

    await fuseki_store.insert_shapes(f"""
        <{node_shape}>
            a sh:NodeShape ;
            sh:targetClass <{EX.Book}> ;
            sh:property <{property_shape}> .

        <{property_shape}>
            a sh:PropertyShape ;
            sh:path <{EX.author}> ;
            sh:class <{EX.Person}> .
    """)

    person_uri = EX.person1

    # The referenced resource exists in the actual Fuseki dataset.
    await fuseki_store.update(f"""
        INSERT DATA {{
            <{person_uri}> a <{EX.Person}> .
        }}
    """)

    monkeypatch.setattr(
        main,
        "validation_ontology_graph",
        Graph(),
    )

    profile = main.SHACLProfile(fuseki_store)

    assert await profile.validate_instance(
        [str(EX.Book)],
        {str(EX.author): [str(person_uri)]},
    ) is True

@pytest.mark.asyncio
async def test_sh_in_constraint_is_persisted_as_an_rdf_list(
    fuseki_store,
    monkeypatch,
):
    shape_uri = URIRef("urn:test:StatusShape")

    await fuseki_store.insert_shapes(f"""
        <{shape_uri}>
            a sh:PropertyShape ;
            sh:path <{EX.status}> .
    """)

    monkeypatch.setattr(main, "store", fuseki_store)

    await main._apply_constraints(
        str(shape_uri),
        {
            str(SH["in"]): [
                str(EX.Draft),
                str(EX.Published),
            ],
        },
        keep_predicates={RDF.type, SH.path},
    )

    shapes = await fuseki_store.load_shapes_graph()

    list_heads = list(
        shapes.objects(shape_uri, SH["in"])
    )

    assert len(list_heads) == 1, (
        "sh:in must have exactly one value: an RDF list head."
    )

    assert list(Collection(shapes, list_heads[0])) == [
        EX.Draft,
        EX.Published,
    ]

@pytest.mark.asyncio
async def test_invalid_edit_preserves_persisted_metadata(
    fuseki_store,
    monkeypatch,
):
    instance_uri = EX.book1
    class_uri = EX.Book
    property_uri = EX.title

    await fuseki_store.insert_shapes(f"""
        <urn:test:BookShape>
            a sh:NodeShape ;
            sh:targetClass <{class_uri}> ;
            sh:property <urn:test:TitleShape> .

        <urn:test:TitleShape>
            a sh:PropertyShape ;
            sh:path <{property_uri}> ;
            sh:minCount 1 .
    """)

    await fuseki_store.update(f"""
        INSERT DATA {{
            <{instance_uri}> a <{class_uri}> ;
                <{property_uri}> "Original title" .
        }}
    """)

    monkeypatch.setattr(main, "store", fuseki_store)
    monkeypatch.setattr(
        main,
        "shacl",
        main.SHACLProfile(fuseki_store),
    )
    monkeypatch.setattr(
        main,
        "check_disjoint_classes",
        AsyncMock(),
    )
    monkeypatch.setattr(
        main,
        "invalidate_profile",
        lambda: None,
    )
    monkeypatch.setitem(
        main.state,
        "created_instances",
        set(),
    )
    monkeypatch.setitem(
        main.state,
        "created_instances_graph",
        Graph(),
    )

    before = Graph()
    before.parse(
        data=await fuseki_store.construct(f"""
            CONSTRUCT {{ <{instance_uri}> ?p ?o }}
            WHERE {{ <{instance_uri}> ?p ?o }}
        """),
        format="turtle",
    )

    with pytest.raises(HTTPException) as exc_info:
        await main.update_instance(
            str(instance_uri),
            {
                "class_uris": [str(class_uri)],
                "properties": {},
                "editable_property_uris": [str(property_uri)],
            },
        )

    assert exc_info.value.status_code == 400

    after = Graph()
    after.parse(
        data=await fuseki_store.construct(f"""
            CONSTRUCT {{ <{instance_uri}> ?p ?o }}
            WHERE {{ <{instance_uri}> ?p ?o }}
        """),
        format="turtle",
    )

    assert set(after) == set(before)

@pytest.mark.asyncio
async def test_create_form_exposes_saved_profile_constraints(
    fuseki_store,
    monkeypatch,
):
    class_uri = str(EX.Book)
    property_uri = str(EX.title)

    class_shape = main.shape_uri_for_entity(
        class_uri, "class", {}
    )
    property_shape = main.shape_uri_for_entity(
        property_uri, "property", {}
    )

    await fuseki_store.insert_shapes(f"""
        <{class_shape}>
            a sh:NodeShape ;
            sh:targetClass <{class_uri}> ;
            sh:property <{property_shape}> .

        <{property_shape}>
            a sh:PropertyShape ;
            sh:path <{property_uri}> ;
            sh:datatype <{XSD.string}> ;
            sh:minCount 1 ;
            sh:maxCount 1 .
    """)

    ontology = Graph()
    ontology.add((EX.Book, RDF.type, OWL.Class))
    ontology.add((
        EX.title,
        RDF.type,
        OWL.DatatypeProperty,
    ))
    ontology.add((EX.title, RDFS.range, XSD.string))

    ontology_entry = {
        "filename": "test.ttl",
        "graph": ontology,
        "entities": [
            {"uri": class_uri, "type": "class"},
            {"uri": property_uri, "type": "datatype_property"},
        ],
    }

    monkeypatch.setattr(main, "store", fuseki_store)
    monkeypatch.setattr(
        main,
        "shacl",
        main.SHACLProfile(fuseki_store),
    )
    monkeypatch.setattr(
        main,
        "ap",
        main.ApplicationProfile(fuseki_store),
    )
    monkeypatch.setattr(
        main,
        "_used_uris_set",
        {class_uri, property_uri},
    )
    monkeypatch.setattr(
        main,
        "get_property_ranges",
        lambda uri: [str(XSD.string)] if uri == property_uri else [],
    )
    monkeypatch.setattr(
        main,
        "get_property_cardinality",
        lambda *_: {
            "minCardinality": None,
            "maxCardinality": None,
        },
    )

    monkeypatch.setitem(
        main.state,
        "ontologies",
        [ontology_entry],
    )
    monkeypatch.setitem(
        main.state,
        "combined_onto_graph",
        ontology,
    )
    monkeypatch.setitem(
        main.state,
        "prefix_map",
        {},
    )

    classes = await main.get_active_classes()

    assert any(item["uri"] == class_uri for item in classes)


    response = cast(
        dict[str, Any],
        await main.get_properties_for_class(class_uri),
    )
    assert response["class_uri"] == class_uri

    properties = cast(
        list[dict[str, Any]],
        response["properties"],
    )

    title = next(
        (
            item
            for item in properties
            if item["uri"] == property_uri
        ),
        None,
    )

    assert title is not None, (
        f"Expected property {property_uri} in the form response."
    )
    assert title["datatype"] == str(XSD.string)
    assert title["constraints"]["minCount"] == 1
    assert title["constraints"]["maxCount"] == 1
    assert title["allowMultiple"] is False
