import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


PROPERTY_URI = "http://example.org/title"
CLASS_URI = "http://example.org/Book"
OTHER_CLASS_URI = "http://example.org/Article"
INVALID_PROPERTY_URI = "http://example.org/unknownProperty"


@pytest.mark.asyncio
async def test_property_links_can_materialize_inactive_domain_class(
    monkeypatch,
):
    store = AsyncMock()
    store.query.return_value = []

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(
        main,
        "shape_uri_for_entity",
        lambda uri, role, prefix_map: (
            "urn:test:property-shape"
            if role == "property"
            else "urn:test:class-shape"
        ),
    )
    monkeypatch.setitem(main.state, "prefix_map", {})

    await main._sync_entity_links(
        PROPERTY_URI,
        "object_property",
        [OTHER_CLASS_URI],
        profile_store=store,
    )

    store.update.assert_awaited_once()

    update = store.update.await_args.args[0]

    assert OTHER_CLASS_URI in update
    assert "urn:test:class-shape" in update
    assert "urn:test:property-shape" in update
    assert "sh:deactivated true" in update
    assert "sh:property" in update


@pytest.mark.asyncio
async def test_class_links_validate_before_mutation(monkeypatch):
    store = AsyncMock()

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(
        main, "get_property_domains",
        lambda _: [OTHER_CLASS_URI],
    )
    monkeypatch.setattr(
        main, "is_subclass",
        lambda child, parents: False,
    )

    with pytest.raises(HTTPException) as exc_info:
        await main._sync_entity_links(
            CLASS_URI,
            "class",
            [INVALID_PROPERTY_URI],
        )

    assert exc_info.value.status_code == 400
    store.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_valid_link_replacement_uses_one_update(monkeypatch):
    store = AsyncMock()
    store.query.return_value = [
        {
            "class": OTHER_CLASS_URI,
            "classShape": "urn:test:ArticleShape",
        }
    ]

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(
        main, "get_property_domains",
        lambda _: [],
    )

    await main._sync_entity_links(
        PROPERTY_URI,
        "object_property",
        [OTHER_CLASS_URI],
    )

    store.update.assert_awaited_once()

    update = store.update.await_args.args[0]
    assert "DELETE {" in update
    assert "WHERE" in update
    assert "INSERT DATA" in update


@pytest.mark.asyncio
async def test_saving_empty_domain_classes_clears_relationships(
    monkeypatch,
):
    store = AsyncMock()
    store.query.return_value = [{"ps": "urn:test:property-shape"}]

    apply_constraints = AsyncMock()
    sync_links = AsyncMock()

    monkeypatch.setattr(
        main,
        "store",
        store,
    )
    monkeypatch.setattr(
        main.ap,
        "get_entity_type",
        AsyncMock(return_value="datatype_property"),
    )
    monkeypatch.setattr(
        main,
        "validate_constraints",
        lambda *_: True,
    )
    monkeypatch.setattr(
        main,
        "_apply_constraints",
        apply_constraints,
    )
    monkeypatch.setattr(
        main,
        "_sync_entity_links",
        sync_links,
    )
    monkeypatch.setattr(
        main,
        "invalidate_profile",
        lambda: None
    )
    monkeypatch.setattr(
        main,
        "_load_stored_profile_field_modes",
        AsyncMock(return_value={}),
    )

    await main.set_entity_constraints(
        PROPERTY_URI,
        {
            "urn:domainClasses": [],
            str(main.SH.maxLength): 50,
            main.PROFILE_FIELD_MODES_KEY: {
                "urn:domainClasses": main.PROFILE_FIELD_MODE_OVERRIDE,
            }
        },
    )

    apply_constraints.assert_awaited_once()
    sync_links.assert_awaited_once_with(
        PROPERTY_URI,
        "datatype_property",
        [],
        profile_store=store,
    )

    apply_constraints.assert_awaited_once_with(
        "urn:test:property-shape",
        {str(main.SH.maxLength): 50},
        keep_predicates={
            main.RDF.type,
            main.SH.path,
            main.SH.order,
            main.SH.property,
        },
    )


@pytest.mark.asyncio
async def test_saving_empty_class_properties_clears_relationships(
    monkeypatch,
):
    apply_constraints = AsyncMock()
    sync_links = AsyncMock()

    monkeypatch.setattr(
        main.ap,
        "get_entity_type",
        AsyncMock(return_value="class"),
    )
    monkeypatch.setattr(
        main,
        "validate_constraints",
        lambda *_: True,
    )
    monkeypatch.setattr(
        main,
        "shape_uri_for_entity",
        lambda *_: "urn:test:class-shape",
    )
    monkeypatch.setattr(
        main,
        "_apply_constraints",
        apply_constraints,
    )
    monkeypatch.setattr(
        main,
        "_sync_entity_links",
        sync_links,
    )
    monkeypatch.setattr(main, "invalidate_profile", lambda: None)

    await main.set_entity_constraints(
        CLASS_URI,
        {
            str(main.SH.property): [],
            str(main.SH.minCount): 1,
        },
    )

    apply_constraints.assert_awaited_once()
    sync_links.assert_awaited_once_with(
        CLASS_URI,
        "class",
        [],
        profile_store=main.store,
    )

    apply_constraints.assert_awaited_once_with(
        "urn:test:class-shape",
        {str(main.SH.minCount): 1},
        keep_predicates={
            main.RDF.type,
            main.SH.targetClass,
            main.SH.property,
        },
    )


@pytest.mark.asyncio
async def test_empty_property_domain_list_deletes_existing_links(
    monkeypatch,
):
    store = AsyncMock()
    store.query.return_value = [
        {
            "class": CLASS_URI,
            "classShape": "urn:test:BookShape",
        }
    ]

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(
        main,
        "get_property_domains",
        lambda _: [],
    )

    await main._sync_entity_links(
        PROPERTY_URI,
        "datatype_property",
        [],
    )

    store.update.assert_awaited_once()
    update = store.update.await_args.args[0]

    assert "DELETE {" in update
    assert "WHERE" in update
    assert "INSERT DATA" not in update
    assert "sh:property" in update


@pytest.mark.asyncio
async def test_empty_class_property_list_deletes_existing_links(
    monkeypatch,
):
    store = AsyncMock()

    store.query.side_effect = [
        # Active classes.
        [{"class": CLASS_URI}],

        # Active properties.
        [{"prop": PROPERTY_URI}],

        # Class shapes queried by _replace_property_domain_links().
        [{
            "class": CLASS_URI,
            "classShape": "urn:test:BookShape",
        }],
    ]

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(
        main,
        "get_property_domains",
        lambda _: [CLASS_URI],
    )

    get_domains_mock = AsyncMock(
        return_value={
            PROPERTY_URI: [CLASS_URI],
        }
    )
    monkeypatch.setattr(
        main.ap,
        "_get_shacl_domains",
        get_domains_mock,
    )

    persist_modes_mock = AsyncMock()
    monkeypatch.setattr(
        main,
        "_persist_profile_field_modes",
        persist_modes_mock,
    )

    await main._sync_entity_links(
        CLASS_URI,
        "class",
        [],
    )

    store.update.assert_awaited_once()

    update = store.update.await_args.args[0]

    assert "DELETE {" in update
    assert "WHERE" in update
    assert "INSERT DATA" not in update

    persist_modes_mock.assert_awaited_once_with(
        PROPERTY_URI,
        {
            "urn:domainClasses": main.PROFILE_FIELD_MODE_OVERRIDE,
        },
        store,
    )
