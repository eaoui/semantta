
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

import main


# ---------------------------------------------------------------------------
# Test URIs
# ---------------------------------------------------------------------------

BOOK = "http://example.org/Book"
RESOURCE = "http://example.org/Resource"
ARTICLE = "http://example.org/Article"
PERSON = "http://example.org/Person"

DIRECT_PROPERTY = "http://example.org/title"
INHERITED_PROPERTY = "http://example.org/identifier"
OVERRIDE_PROPERTY = "http://example.org/author"
REMOVED_PROPERTY = "http://example.org/summary"
ORPHAN_PROPERTY = "http://example.org/legacyProperty"
UNIVERSAL_PROPERTY = "http://example.org/globalIdentifier"

BOOK_SHAPE = "urn:test:BookShape"
ARTICLE_SHAPE = "urn:test:ArticleShape"
TITLE_SHAPE = "urn:test:TitleShape"
AUTHOR_SHAPE = "urn:test:AuthorShape"
GLOBAL_SHAPE = "urn:test:GlobalShape"


def domain_map(monkeypatch, values):
    """Replace the ontology domain index for an isolated test."""
    monkeypatch.setattr(
        main,
        "_property_domains",
        defaultdict(list, values),
    )


# ---------------------------------------------------------------------------
# Effective applicability
# ---------------------------------------------------------------------------

def test_property_applies_to_direct_domain():
    assert main._property_applies_to_class(
        BOOK,
        [BOOK],
    )


def test_property_applies_to_subclasses(monkeypatch):
    monkeypatch.setattr(
        main,
        "_subclass_pairs",
        {
            (BOOK, RESOURCE),
        },
    )

    assert main._property_applies_to_class(
        BOOK,
        [RESOURCE],
    )


def test_property_does_not_apply_to_unrelated_class(monkeypatch):
    monkeypatch.setattr(
        main,
        "_subclass_pairs",
        {
            (BOOK, RESOURCE),
        },
    )

    assert not main._property_applies_to_class(
        PERSON,
        [RESOURCE],
    )


def test_empty_effective_domain_is_universal():
    assert main._property_applies_to_class(BOOK, [])
    assert main._property_applies_to_class(ARTICLE, [])
    assert main._property_applies_to_class(PERSON, [])


# ---------------------------------------------------------------------------
# Default and override domain resolution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_effective_domains_respect_default_and_override_modes(
    monkeypatch,
):
    store = AsyncMock()

    # First query: stored class-property associations.
    store.query.side_effect = [
        [
            # A stale link must not replace a default-mode ontology domain.
            {
                "propUri": DIRECT_PROPERTY,
                "class": ARTICLE,
            },
            {
                "propUri": OVERRIDE_PROPERTY,
                "class": ARTICLE,
            },
            {
                "propUri": REMOVED_PROPERTY,
                "class": None,
            },
            {
                "propUri": UNIVERSAL_PROPERTY,
                "class": None,
            },
        ],
        # Second query: stored field modes.
        [
            {
                "entity": DIRECT_PROPERTY,
                "mode": main.PROFILE_FIELD_MODE_DEFAULT,
            },
            {
                "entity": OVERRIDE_PROPERTY,
                "mode": main.PROFILE_FIELD_MODE_OVERRIDE,
            },
            {
                "entity": REMOVED_PROPERTY,
                "mode": main.PROFILE_FIELD_MODE_OVERRIDE,
            },
        ],
    ]

    domain_map(
        monkeypatch,
        {
            DIRECT_PROPERTY: [BOOK],
            OVERRIDE_PROPERTY: [BOOK],
            REMOVED_PROPERTY: [BOOK],
            UNIVERSAL_PROPERTY: [],
        },
    )

    profile = main.ApplicationProfile(store)

    result = await profile._get_shacl_domains()

    # Default mode uses the ontology domain.
    assert result[DIRECT_PROPERTY] == [BOOK]

    # Override mode uses the explicitly selected class.
    assert result[OVERRIDE_PROPERTY] == [ARTICLE]

    # An explicitly empty override is universal.
    assert result[REMOVED_PROPERTY] == []

    # An empty ontology domain in default mode is also universal.
    assert result[UNIVERSAL_PROPERTY] == []


# ---------------------------------------------------------------------------
# Class Properties view
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_active_properties_includes_direct_inherited_and_universal(
    monkeypatch,
):
    store = AsyncMock()
    store.query.return_value = [
        {"propUri": DIRECT_PROPERTY, "order": "1"},
        {"propUri": INHERITED_PROPERTY, "order": "2"},
        {"propUri": ORPHAN_PROPERTY, "order": "3"},
        {"propUri": UNIVERSAL_PROPERTY, "order": "4"},
    ]

    profile = main.ApplicationProfile(store)

    monkeypatch.setattr(
        profile,
        "_get_shacl_domains",
        AsyncMock(
            return_value={
                DIRECT_PROPERTY: [BOOK],
                INHERITED_PROPERTY: [RESOURCE],
                ORPHAN_PROPERTY: [ARTICLE],
                UNIVERSAL_PROPERTY: [],
            }
        ),
    )

    monkeypatch.setattr(
        main,
        "_subclass_pairs",
        {
            (BOOK, RESOURCE),
        },
    )

    monkeypatch.setattr(
        main,
        "_get_active_profile_classes",
        AsyncMock(
            return_value={BOOK, RESOURCE, ARTICLE}
        ),
    )

    result = await profile._list_active_properties(BOOK)

    result_uris = [item["uri"] for item in result]

    assert result_uris == [
        DIRECT_PROPERTY,
        INHERITED_PROPERTY,
        UNIVERSAL_PROPERTY,
    ]

    assert ORPHAN_PROPERTY not in result_uris


@pytest.mark.asyncio
async def test_unlinked_property_with_nonempty_default_domain_is_not_universal(
    monkeypatch,
):
    store = AsyncMock()
    store.query.return_value = [
        {"propUri": ORPHAN_PROPERTY, "order": "1"},
    ]

    profile = main.ApplicationProfile(store)

    # The property shape has no class link, but its effective domain
    # remains non-empty in default mode.
    monkeypatch.setattr(
        profile,
        "_get_shacl_domains",
        AsyncMock(
            return_value={
                ORPHAN_PROPERTY: [ARTICLE],
            }
        ),
    )

    monkeypatch.setattr(
        main,
        "_get_active_profile_classes",
        AsyncMock(return_value=set()),
    )

    result = await profile._list_active_properties(BOOK)

    assert result == []


# ---------------------------------------------------------------------------
# Materializing and removing SHACL associations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_replace_property_domain_links_writes_inverse_association(
    monkeypatch,
):
    store = AsyncMock()
    store.query.return_value = [
        {
            "class": BOOK,
            "classShape": BOOK_SHAPE,
        },
    ]

    monkeypatch.setattr(
        main,
        "shape_uri_for_entity",
        lambda uri, entity_type, prefix_map: (
            TITLE_SHAPE if entity_type == "property"
            else BOOK_SHAPE
        ),
    )

    await main._replace_property_domain_links(
        DIRECT_PROPERTY,
        [BOOK],
        profile_store=store,
    )

    store.update.assert_awaited_once()

    update = store.update.await_args.args[0]

    assert "DELETE {" in update
    assert "WHERE" in update
    assert "INSERT DATA" in update
    assert BOOK_SHAPE in update
    assert TITLE_SHAPE in update


@pytest.mark.asyncio
async def test_empty_domain_override_removes_all_class_links(
    monkeypatch,
):
    store = AsyncMock()
    store.query.return_value = [
        {
            "class": BOOK,
            "classShape": BOOK_SHAPE,
        },
        {
            "class": ARTICLE,
            "classShape": ARTICLE_SHAPE,
        },
    ]

    await main._replace_property_domain_links(
        DIRECT_PROPERTY,
        [],
        profile_store=store,
    )

    store.update.assert_awaited_once()

    update = store.update.await_args.args[0]

    assert "DELETE {" in update
    assert "WHERE" in update
    assert "sh:property" in update
    assert "INSERT DATA" not in update


@pytest.mark.asyncio
async def test_property_override_can_select_another_active_domain(
    monkeypatch,
):
    store = AsyncMock()
    store.query.return_value = [
        {
            "class": ARTICLE,
            "classShape": ARTICLE_SHAPE,
        },
    ]

    monkeypatch.setattr(
        main,
        "shape_uri_for_entity",
        lambda uri, entity_type, prefix_map: (
            AUTHOR_SHAPE if entity_type == "property"
            else ARTICLE_SHAPE
        ),
    )

    domain_map(
        monkeypatch,
        {
            OVERRIDE_PROPERTY: [BOOK],
        },
    )

    # Article is an active class. It may be selected as an explicit
    # override even though the ontology default is Book.
    await main._sync_entity_links(
        OVERRIDE_PROPERTY,
        "object_property",
        [ARTICLE],
        profile_store=store,
    )

    store.update.assert_awaited_once()

    update = store.update.await_args.args[0]

    assert ARTICLE_SHAPE in update
    assert AUTHOR_SHAPE in update


# ---------------------------------------------------------------------------
# Class-side editing updates property-side Domain Classes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_class_properties_edit_updates_property_domain_associations(
    monkeypatch,
):
    store = AsyncMock()

    store.query.side_effect = [
        # Active classes.
        [{"class": BOOK}],
        # Active properties.
        [
            {"prop": DIRECT_PROPERTY},
            {"prop": OVERRIDE_PROPERTY},
            {"prop": REMOVED_PROPERTY},
        ],
    ]

    effective_domains = {
        DIRECT_PROPERTY: [BOOK],
        OVERRIDE_PROPERTY: [ARTICLE],
        REMOVED_PROPERTY: [BOOK],
    }

    ontology_domains = {
        DIRECT_PROPERTY: [BOOK],
        OVERRIDE_PROPERTY: [ARTICLE],
        REMOVED_PROPERTY: [BOOK],
    }

    monkeypatch.setattr(
        main.ap,
        "_get_shacl_domains",
        AsyncMock(return_value=effective_domains),
    )

    monkeypatch.setattr(
        main,
        "get_property_domains",
        lambda uri: ontology_domains.get(uri, []),
    )

    replace_links = AsyncMock()
    persist_modes = AsyncMock()

    monkeypatch.setattr(
        main,
        "_replace_property_domain_links",
        replace_links,
    )
    monkeypatch.setattr(
        main,
        "_persist_profile_field_modes",
        persist_modes,
    )

    # Keep DIRECT_PROPERTY, add OVERRIDE_PROPERTY to Book,
    # and remove REMOVED_PROPERTY from Book.
    await main._sync_entity_links(
        BOOK,
        "class",
        [
            DIRECT_PROPERTY,
            OVERRIDE_PROPERTY,
        ],
        profile_store=store,
    )

    replacements = {
        call.args[0]: set(call.args[1])
        for call in replace_links.await_args_list
    }

    assert replacements == {
        OVERRIDE_PROPERTY: {ARTICLE, BOOK},
        REMOVED_PROPERTY: set(),
    }

    persisted_modes = {
        call.args[0]: call.args[1]["urn:domainClasses"]
        for call in persist_modes.await_args_list
    }

    assert persisted_modes == {
        OVERRIDE_PROPERTY: main.PROFILE_FIELD_MODE_OVERRIDE,
        REMOVED_PROPERTY: main.PROFILE_FIELD_MODE_OVERRIDE,
    }


@pytest.mark.asyncio
async def test_class_properties_editor_cannot_add_universal_property(
    monkeypatch,
):
    store = AsyncMock()

    store.query.side_effect = [
        [{"class": BOOK}],
        [{"prop": UNIVERSAL_PROPERTY}],
    ]

    monkeypatch.setattr(
        main.ap,
        "_get_shacl_domains",
        AsyncMock(
            return_value={
                UNIVERSAL_PROPERTY: [],
            }
        ),
    )

    replace_links = AsyncMock()
    persist_modes = AsyncMock()

    monkeypatch.setattr(
        main,
        "_replace_property_domain_links",
        replace_links,
    )
    monkeypatch.setattr(
        main,
        "_persist_profile_field_modes",
        persist_modes,
    )

    with pytest.raises(HTTPException) as exc_info:
        await main._sync_entity_links(
            BOOK,
            "class",
            [UNIVERSAL_PROPERTY],
            profile_store=store,
        )

    assert exc_info.value.status_code == 409
    replace_links.assert_not_awaited()
    persist_modes.assert_not_awaited()


# ---------------------------------------------------------------------------
# Property activation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_property_to_class_does_not_require_preexisting_profile_entity(
    monkeypatch,
):
    store = AsyncMock()
    profile = main.SHACLProfile(store)

    get_entity_type_mock = AsyncMock(
        side_effect=AssertionError(
            "A property must not need to be active before activation."
        )
    )
    monkeypatch.setattr(
        main.ap,
        "get_entity_type",
        get_entity_type_mock,
    )

    monkeypatch.setattr(
        main.ap,
        "_get_shacl_domains",
        AsyncMock(
            return_value={
                DIRECT_PROPERTY: [BOOK],
            }
        ),
    )

    monkeypatch.setattr(
        main,
        "get_property_domains",
        lambda _: [BOOK],
    )

    set_default_constraints_mock = AsyncMock()
    monkeypatch.setattr(
        profile,
        "_set_default_constraints",
        set_default_constraints_mock,
    )

    replace_links = AsyncMock()
    persist_modes = AsyncMock()

    monkeypatch.setattr(
        main,
        "_replace_property_domain_links",
        replace_links,
    )
    monkeypatch.setattr(
        main,
        "_persist_profile_field_modes",
        persist_modes,
    )

    set_deactivated_mock = AsyncMock()

    monkeypatch.setattr(
        profile,
        "_set_shape_deactivated",
        set_deactivated_mock,
    )

    load_modes_mock = AsyncMock(return_value={})

    monkeypatch.setattr(
        main,
        "_load_stored_profile_field_modes",
        load_modes_mock,
    )

    await profile.add_property_to_class(
        BOOK,
        DIRECT_PROPERTY,
    )

    get_entity_type_mock.assert_not_awaited()
    set_default_constraints_mock.assert_awaited_once()

    set_deactivated_mock.assert_awaited_once_with(
        main.shape_uri_for_entity(
            DIRECT_PROPERTY,
            "property",
            main.state["prefix_map"],
        ),
        False,
    )

    replace_links.assert_awaited_once_with(
        DIRECT_PROPERTY,
        [BOOK],
        profile_store=store,
    )

    persist_modes.assert_awaited_once_with(
        DIRECT_PROPERTY,
        {
            "urn:domainClasses": main.PROFILE_FIELD_MODE_DEFAULT,
        },
        store,
    )


# ---------------------------------------------------------------------------
# Class editor is the inverse of property Domain Classes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_class_constraints_expose_direct_inherited_and_universal_properties(
    monkeypatch,
):
    domains = {
        DIRECT_PROPERTY: [BOOK],
        INHERITED_PROPERTY: [RESOURCE],
        ORPHAN_PROPERTY: [ARTICLE],
        UNIVERSAL_PROPERTY: [],
    }

    domain_map(monkeypatch, domains)

    monkeypatch.setattr(
        main.ap,
        "get_entity_type",
        AsyncMock(return_value="class"),
    )

    monkeypatch.setattr(
        main,
        "get_original_constraints",
        lambda *_: {},
    )

    monkeypatch.setattr(
        main.store,
        "query",
        AsyncMock(return_value=[]),
    )

    monkeypatch.setattr(
        main.shacl,
        "get_active_properties",
        AsyncMock(
            return_value=[
                DIRECT_PROPERTY,
                INHERITED_PROPERTY,
                ORPHAN_PROPERTY,
                UNIVERSAL_PROPERTY,
            ]
        ),
    )

    monkeypatch.setattr(
        main.ap,
        "_get_shacl_domains",
        AsyncMock(return_value=domains),
    )

    monkeypatch.setattr(
        main,
        "_load_stored_profile_field_modes",
        AsyncMock(return_value={}),
    )

    monkeypatch.setattr(
        main,
        "_validate_profile_range_constraint_compatibility",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        main,
        "shape_uri_for_entity",
        lambda *_: BOOK_SHAPE,
    )

    monkeypatch.setattr(
        main,
        "_subclass_pairs",
        {
            (BOOK, RESOURCE),
        },
    )

    monkeypatch.setattr(
        main.shacl,
        "get_active_classes",
        AsyncMock(
            return_value=[
                BOOK,
                RESOURCE,
                ARTICLE,
                PERSON,
            ]
        ),
    )

    result = await main.get_entity_constraints(BOOK)

    assert result["effective"][str(main.SH.property)] == [
        DIRECT_PROPERTY,
    ]

    assert result["inherited_properties"] == [
        INHERITED_PROPERTY,
    ]

    assert result["universal_properties"] == [
        UNIVERSAL_PROPERTY,
    ]

    assert ORPHAN_PROPERTY not in result["effective"][
        str(main.SH.property)
    ]


# ---------------------------------------------------------------------------
# Metadata membership validation
# ---------------------------------------------------------------------------

def make_membership_profile(store):
    return SimpleNamespace(
        store=store,
        get_active_classes=AsyncMock(
            return_value=[
                BOOK,
                RESOURCE,
                ARTICLE,
                PERSON,
            ]
        ),
        get_active_properties=AsyncMock(
            return_value=[
                DIRECT_PROPERTY,
                INHERITED_PROPERTY,
                UNIVERSAL_PROPERTY,
            ]
        ),
    )


@pytest.mark.asyncio
async def test_membership_accepts_property_applicable_to_any_selected_class(
    monkeypatch,
):
    store = AsyncMock()
    profile = make_membership_profile(store)

    monkeypatch.setattr(main, "shacl", profile)

    get_domains_mock = AsyncMock(
        return_value={
            DIRECT_PROPERTY: [RESOURCE],
        }
    )
    monkeypatch.setattr(
        main.ap,
        "_get_shacl_domains",
        get_domains_mock,
    )

    monkeypatch.setattr(
        main,
        "_subclass_pairs",
        {
            (BOOK, RESOURCE),
        },
    )

    await main._validate_metadata_profile_membership(
        [PERSON, BOOK],
        {
            DIRECT_PROPERTY: ["A title"],
        },
    )

    get_domains_mock.assert_awaited_once_with(
        profile_store=store,
    )


@pytest.mark.asyncio
async def test_membership_rejects_property_unrelated_to_all_selected_classes(
    monkeypatch,
):
    store = AsyncMock()
    profile = make_membership_profile(store)

    monkeypatch.setattr(main, "shacl", profile)

    monkeypatch.setattr(
        main.ap,
        "_get_shacl_domains",
        AsyncMock(
            return_value={
                DIRECT_PROPERTY: [BOOK],
            }
        ),
    )

    monkeypatch.setattr(
        main,
        "_subclass_pairs",
        set(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await main._validate_metadata_profile_membership(
            [PERSON, ARTICLE],
            {
                DIRECT_PROPERTY: ["A title"],
            },
        )

    assert exc_info.value.status_code == 400
    assert "not applicable" in exc_info.value.detail


@pytest.mark.asyncio
async def test_membership_accepts_universal_property_for_any_selected_class(
    monkeypatch,
):
    store = AsyncMock()
    profile = make_membership_profile(store)

    monkeypatch.setattr(main, "shacl", profile)

    monkeypatch.setattr(
        main.ap,
        "_get_shacl_domains",
        AsyncMock(
            return_value={
                UNIVERSAL_PROPERTY: [],
            }
        ),
    )

    await main._validate_metadata_profile_membership(
        [PERSON],
        {
            UNIVERSAL_PROPERTY: ["global-id"],
        },
    )
    

@pytest.mark.asyncio
async def test_list_active_properties_uses_distinct_aggregate_alias(
    monkeypatch,
):
    store = AsyncMock()
    store.query.return_value = []

    profile = main.ApplicationProfile(store)

    monkeypatch.setattr(
        profile,
        "_get_shacl_domains",
        AsyncMock(return_value={}),
    )

    monkeypatch.setattr(
        main,
        "_get_active_profile_classes",
        AsyncMock(return_value=set()),
    )

    result = await profile._list_active_properties(BOOK)

    assert result == []

    query = store.query.await_args_list[0].args[0]

    assert "SAMPLE(?order) AS ?sortOrder" in query
    assert "SAMPLE(?order) AS ?order" not in query