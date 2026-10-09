import sys
from pathlib import Path
from unittest.mock import AsyncMock
from rdflib import Graph, Literal, URIRef

import pytest
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main

@pytest.mark.asyncio
async def test_check_instances_exist_rejects_invalid_uri():
    original_store = main.store
    store = AsyncMock()
    main.store = store

    try:
        with pytest.raises(HTTPException) as exc_info:
            await main.check_instances_exist({
                "uris": [
                    "http://example.org/> UNION { ?s ?p ?o } #",
                ]
            })

        assert exc_info.value.status_code == 400
        store.query.assert_not_awaited()
    finally:
        main.store = original_store


@pytest.mark.asyncio
async def test_check_instances_exist_returns_existing_uris():
    original_store = main.store
    store = AsyncMock()
    store.query.return_value = [
        {"uri": "http://example.org/book1"},
    ]
    main.store = store

    try:
        result = await main.check_instances_exist({
            "uris": [
                "http://example.org/book1",
                "urn:test:book2",
            ]
        })

        assert result == {
            "existing": [
                "http://example.org/book1",
            ]
        }

        query = store.query.await_args.args[0]

        assert "<http://example.org/book1>" in query
        assert "<urn:test:book2>" in query
    finally:
        main.store = original_store

@pytest.mark.asyncio
async def test_apply_base_iri_rewrites_metadata_references(monkeypatch):
    old_uri = "urn:uuid:test-id"
    new_uri = "https://example.org/testing/test-id"
    metadata_graph_uri = "urn:semantta:metadata:records.ttl"

    store = AsyncMock()
    store.query.return_value = []

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "rebuild_used_uris", AsyncMock())
    monkeypatch.setattr(main, "save_created_instances", lambda: None)
    monkeypatch.setattr(main, "atomic_write_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "invalidate_instance_count", lambda: None)
    monkeypatch.setattr(main, "invalidate_profile", lambda: None)

    created_graph = Graph()
    rdf_type = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
    book_class = URIRef("http://example.org/Book")
    record = URIRef("http://example.org/record/1")
    related = URIRef("http://example.org/related")

    created_graph.add((URIRef(old_uri), rdf_type, book_class))
    created_graph.add((record, related, URIRef(old_uri)))

    monkeypatch.setitem(main.state, "base_iri", "https://example.org/resources")
    monkeypatch.setitem(main.state, "created_instances", {old_uri})
    monkeypatch.setitem(main.state, "created_instances_graph", created_graph)
    monkeypatch.setitem(main.state, "starred_instance_uris", {old_uri})
    monkeypatch.setitem(main.state, "non_integrated_uris", {old_uri})
    monkeypatch.setitem(main.state, "metadata_only_sources", {old_uri: "records.ttl"})
    monkeypatch.setitem(
        main.state,
        "metadata_files",
        [{"graph_uri": metadata_graph_uri}],
    )

    result = await main.apply_base_iri({
        "base_iri": "https://example.org/testing/",
    })

    assert result == {
        "status": "ok",
        "updated": 1,
        "base_iri": "https://example.org/testing/",
    }
    store.update.assert_awaited_once()

    update = store.update.await_args.args[0]
    assert metadata_graph_uri in update
    assert f"<{old_uri}>" in update
    assert f"<{new_uri}>" in update

    assert main.state["created_instances"] == {new_uri}
    assert main.state["starred_instance_uris"] == {new_uri}
    assert main.state["non_integrated_uris"] == {new_uri}
    assert main.state["metadata_only_sources"] == {
        new_uri: "records.ttl",
    }

    assert (URIRef(new_uri), rdf_type, book_class) in created_graph
    assert (record, related, URIRef(new_uri)) in created_graph
    assert not list(created_graph.triples((URIRef(old_uri), None, None)))

def test_base_iri_mapping_supports_repeated_changes():
    identifier = "123e4567-e89b-12d3-a456-426614174000"

    first = main._build_base_iri_mapping(
        {f"https://first.example/data/{identifier}"},
        "https://first.example/data/",
        "https://second.example/data/",
    )

    assert first == {
        f"https://first.example/data/{identifier}":
        f"https://second.example/data/{identifier}"
    }

    second = main._build_base_iri_mapping(
        set(first.values()),
        "https://second.example/data/",
        "https://third.example/data/",
    )

    assert second == {
        f"https://second.example/data/{identifier}":
        f"https://third.example/data/{identifier}"
    }

@pytest.mark.asyncio
async def test_delete_instance_preserves_incoming_references(monkeypatch):
    uri = "http://example.org/book2"
    subject = URIRef(uri)
    related_subject = URIRef("http://example.org/book1")
    related_predicate = URIRef("http://example.org/relatedTo")
    title_predicate = URIRef("http://example.org/title")

    graph = Graph()
    graph.add((subject, title_predicate, Literal("Book 2")))
    graph.add((related_subject, related_predicate, subject))

    store = AsyncMock()
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setitem(main.state, "created_instances", {uri})
    monkeypatch.setitem(main.state, "created_instances_graph", graph)
    monkeypatch.setattr(main, "save_created_instances", lambda: None)
    monkeypatch.setattr(main, "invalidate_instance_count", lambda: None)
    monkeypatch.setattr(main, "invalidate_profile", lambda: None)

    result = await main.delete_instance(uri)

    assert result == {"status": "ok"}
    store.update.assert_awaited_once()

    update = store.update.await_args.args[0]
    assert "?s ?p" not in update

    assert (subject, title_predicate, Literal("Book 2")) not in graph
    assert (related_subject, related_predicate, subject) in graph
    assert uri not in main.state["created_instances"]

@pytest.mark.asyncio
async def test_create_instance_rejects_inactive_class(monkeypatch):
    store = AsyncMock()

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(
        main,
        "check_disjoint_classes",
        AsyncMock(),
    )
    monkeypatch.setattr(
        main.shacl,
        "get_active_classes",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        main.shacl,
        "get_active_properties",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setitem(
        main.state,
        "base_iri",
        "https://example.org/resources/",
    )

    with pytest.raises(HTTPException) as exc_info:
        await main.create_instance({
            "class_uris": ["https://example.org/InactiveClass"],
            "properties": {},
        })

    assert exc_info.value.status_code == 400
    store.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_instance_rejects_inactive_property(monkeypatch):
    store = AsyncMock()
    class_uri = "https://example.org/Book"
    property_uri = "https://example.org/inactiveProperty"

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(
        main,
        "check_disjoint_classes",
        AsyncMock(),
    )
    monkeypatch.setattr(
        main.shacl,
        "get_active_classes",
        AsyncMock(return_value=[class_uri]),
    )
    monkeypatch.setattr(
        main.shacl,
        "get_active_properties",
        AsyncMock(return_value=[]),
    )

    with pytest.raises(HTTPException) as exc_info:
        await main.update_instance(
            "https://example.org/book/1",
            {
                "class_uris": [class_uri],
                "properties": {
                    property_uri: ["Example"],
                },
            },
        )

    assert exc_info.value.status_code == 400
    store.update.assert_not_awaited()