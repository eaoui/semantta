from pathlib import Path
import sys
from unittest.mock import AsyncMock

import pytest
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD
from typing import cast

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


EX = Namespace("https://example.org/constraint-resolver-service-test/")
SH = Namespace("http://www.w3.org/ns/shacl#")


@pytest.mark.asyncio
async def test_property_constraint_resolver_uses_injected_store(
    monkeypatch,
):
    profile_store = AsyncMock()
    unrelated_store = AsyncMock()

    property_uri = str(EX.title)
    property_ref = URIRef(property_uri)
    shape_uri = URIRef("urn:test:title-shape")

    shapes_graph = Graph()

    shapes_graph.add((
        shape_uri,
        RDF.type,
        SH.PropertyShape,
    ))
    shapes_graph.add((
        shape_uri,
        SH.path,
        property_ref,
    ))
    shapes_graph.add((
        shape_uri,
        SH.datatype,
        XSD.integer,
    ))
    shapes_graph.add((
        shape_uri,
        SH.minCount,
        Literal(2),
    ))

    profile_store.load_shapes_graph = AsyncMock(
        return_value=shapes_graph
    )

    profile_store.query.return_value = [
        {
            "class": str(EX.Book),
        },
    ]

    monkeypatch.setattr(
        main,
        "store",
        unrelated_store,
    )

    monkeypatch.setattr(
        main,
        "get_original_constraints",
        lambda *_: {
            str(RDFS.range): [str(XSD.string)],
        },
    )

    monkeypatch.setattr(
        main,
        "get_property_domains",
        lambda uri: [str(EX.Book)],
    )

    load_modes = AsyncMock(return_value={
        str(SH.datatype): main.PROFILE_FIELD_MODE_OVERRIDE,
    })

    monkeypatch.setattr(
        main,
        "_load_stored_profile_field_modes",
        load_modes,
    )

    monkeypatch.setattr(
        main,
        "_validate_profile_range_constraint_compatibility",
        lambda *args, **kwargs: None,
    )

    profile = main.SHACLProfile(
        cast(main.RDFStore, profile_store)
    )

    result = await profile.get_entity_constraints(
        property_uri,
        "datatype_property",
    )

    assert result["type"] == "datatype_property"

    assert result["original"][str(SH.datatype)] == [
        str(XSD.string),
    ]

    assert result["overrides"][str(SH.datatype)] == (
        str(XSD.integer)
    )

    assert result["effective"][str(SH.datatype)] == [
        str(XSD.integer),
    ]

    assert result["overrides"][str(SH.minCount)] == "2"

    assert result["effective"]["urn:domainClasses"] == [
        str(EX.Book),
    ]

    assert result["field_modes"][str(SH.datatype)] == (
        main.PROFILE_FIELD_MODE_OVERRIDE
    )

    profile_store.load_shapes_graph.assert_awaited_once()
    profile_store.query.assert_awaited_once()

    unrelated_store.load_shapes_graph.assert_not_awaited()
    unrelated_store.query.assert_not_awaited()

    load_modes.assert_awaited_once_with(
        property_uri,
        profile_store=profile_store,
    )


@pytest.mark.asyncio
async def test_class_constraint_resolver_uses_injected_store(
    monkeypatch,
):
    profile_store = AsyncMock()
    unrelated_store = AsyncMock()

    profile = main.SHACLProfile(profile_store)

    profile_store.query.return_value = [
        {
            "pred": str(SH.message),
            "val": "Stored class message",
        },
    ]

    direct_property = str(EX.directProperty)
    universal_property = str(EX.universalProperty)
    class_uri = str(EX.Book)

    domains = {
        direct_property: [class_uri],
        universal_property: [],
    }

    monkeypatch.setattr(
        main,
        "store",
        unrelated_store,
    )

    monkeypatch.setattr(
        main,
        "get_original_constraints",
        lambda *_: {},
    )

    monkeypatch.setattr(
        main,
        "get_property_domains",
        lambda uri: (
            [class_uri]
            if uri == direct_property
            else []
        ),
    )

    monkeypatch.setattr(
        profile,
        "get_active_properties",
        AsyncMock(return_value=[
            direct_property,
            universal_property,
        ]),
    )

    monkeypatch.setattr(
        profile,
        "get_active_classes",
        AsyncMock(return_value=[class_uri]),
    )

    domain_resolver = AsyncMock(return_value=domains)

    monkeypatch.setattr(
        main.ap,
        "_get_shacl_domains",
        domain_resolver,
    )

    load_modes = AsyncMock(return_value={})

    monkeypatch.setattr(
        main,
        "_load_stored_profile_field_modes",
        load_modes,
    )

    monkeypatch.setattr(
        main,
        "_validate_profile_range_constraint_compatibility",
        lambda *args, **kwargs: None,
    )

    result = await profile.get_entity_constraints(
        class_uri,
        "class",
    )

    assert result["type"] == "class"

    assert result["overrides"][str(SH.property)] == [
        direct_property,
    ]

    assert result["universal_properties"] == [
        universal_property,
    ]

    assert result["effective"][str(SH.property)] == [
        direct_property,
    ]

    assert result["overrides"][str(SH.message)] == (
        "Stored class message"
    )

    assert profile_store.query.await_count == 1
    unrelated_store.query.assert_not_awaited()

    domain_resolver.assert_awaited_once_with(
        profile_store=profile_store,
    )

    load_modes.assert_awaited_once_with(
        class_uri,
        profile_store=profile_store,
    )


@pytest.mark.asyncio
async def test_constraint_endpoint_delegates_to_shacl_profile(
    monkeypatch,
):
    entity_uri = str(EX.Book)

    expected = {
        "uri": entity_uri,
        "type": "class",
        "original": {},
        "overrides": {},
        "field_modes": {},
        "effective": {},
    }

    get_entity_type = AsyncMock(return_value="class")
    resolve_constraints = AsyncMock(return_value=expected)

    monkeypatch.setattr(
        main.ap,
        "get_entity_type",
        get_entity_type,
    )

    monkeypatch.setattr(
        main.shacl,
        "get_entity_constraints",
        resolve_constraints,
    )

    result = await main.get_entity_constraints(entity_uri)

    assert result == expected

    get_entity_type.assert_awaited_once_with(entity_uri)

    resolve_constraints.assert_awaited_once_with(
        entity_uri,
        "class",
    )