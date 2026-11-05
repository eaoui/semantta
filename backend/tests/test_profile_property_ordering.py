from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

import main

GROUP_ANNOTATION = str(main.PROPERTY_GROUP_ANNOTATION)
GROUP_OBJECT = str(main.PROPERTY_GROUP_OBJECT)
GROUP_DATATYPE = str(main.PROPERTY_GROUP_DATATYPE)

PROPERTY_A = "http://example.org/propertyA"
PROPERTY_B = "http://example.org/propertyB"
PROPERTY_C = "http://example.org/propertyC"


@pytest.mark.asyncio
async def test_order_map_query_excludes_inactive_properties():
    store = AsyncMock()
    store.query.return_value = [
        {"propUri": PROPERTY_A, "ord": "1"},
        {"propUri": PROPERTY_B, "ord": "2"},
    ]

    profile = main.ApplicationProfile(store)

    await profile._ensure_order_map()

    assert profile._order_map == {
        PROPERTY_A: 1,
        PROPERTY_B: 2,
    }

    query = store.query.await_args.args[0]

    assert "sh:group" in query
    assert "sh:PropertyGroup" in query
    assert "sh:deactivated true" in query


@pytest.mark.asyncio
async def test_list_active_properties_sorts_by_group_then_local_order(
    monkeypatch,
):
    store = AsyncMock()
    store.query.return_value = [
        {
            "propUri": PROPERTY_B,
            "groupUri": GROUP_OBJECT,
            "sampledGroupLabel": "Object Properties",
            "sortOrder": "2",
            "sortGroupOrder": "2",
        },
        {
            "propUri": PROPERTY_C,
            "groupUri": GROUP_DATATYPE,
            "sampledGroupLabel": "Datatype Properties",
            "sortOrder": "1",
            "sortGroupOrder": "3",
        },
        {
            "propUri": PROPERTY_A,
            "groupUri": GROUP_ANNOTATION,
            "sampledGroupLabel": "Annotation Properties",
            "sortOrder": "1",
            "sortGroupOrder": "1",
        },
    ]

    profile = main.ApplicationProfile(store)

    monkeypatch.setattr(
        profile,
        "_get_shacl_domains",
        AsyncMock(return_value={
            PROPERTY_A: [],
            PROPERTY_B: [],
            PROPERTY_C: [],
        }),
    )

    monkeypatch.setattr(
        main,
        "_get_active_profile_classes",
        AsyncMock(return_value=set()),
    )

    result = await profile._list_active_properties(
        "http://example.org/Book"
    )

    assert result == [
        {
            "uri": PROPERTY_A,
            "groupUri": GROUP_ANNOTATION,
            "groupLabel": "Annotation Properties",
            "groupOrder": 1,
            "order": 1,
        },
        {
            "uri": PROPERTY_B,
            "groupUri": GROUP_OBJECT,
            "groupLabel": "Object Properties",
            "groupOrder": 2,
            "order": 2,
        },
        {
            "uri": PROPERTY_C,
            "groupUri": GROUP_DATATYPE,
            "groupLabel": "Datatype Properties",
            "groupOrder": 3,
            "order": 1,
        },
    ]

    query = store.query.await_args.args[0]

    assert "SAMPLE(?group) AS ?groupUri" in query
    assert "SAMPLE(?order) AS ?sortOrder" in query
    assert "SAMPLE(?groupOrder) AS ?sortGroupOrder" in query
    assert "rdfs:label" in query
    assert "SAMPLE(?groupLabel) AS ?sampledGroupLabel" in query
    assert "SAMPLE(?groupLabel) AS ?groupLabel" not in query


@pytest.mark.asyncio
async def test_get_properties_for_class_preserves_group_and_property_order(
    monkeypatch,
):
    annotation_uri = "http://example.org/annotation"
    object_first_uri = "http://example.org/object-first"
    object_second_uri = "http://example.org/object-second"
    datatype_uri = "http://example.org/datatype"
    person_uri = "http://example.org/Person"

    group = [
        {
            "uri": annotation_uri,
            "groupUri": GROUP_ANNOTATION,
            "groupLabel": "Annotation Properties",
            "groupOrder": 1,
            "order": 1,
        },
        {
            "uri": object_first_uri,
            "groupUri": GROUP_OBJECT,
            "groupLabel": "Object Properties",
            "groupOrder": 2,
            "order": 1,
        },
        {
            "uri": object_second_uri,
            "groupUri": GROUP_OBJECT,
            "groupLabel": "Object Properties",
            "groupOrder": 2,
            "order": 2,
        },
        {
            "uri": datatype_uri,
            "groupUri": GROUP_DATATYPE,
            "groupLabel": "Datatype Properties",
            "groupOrder": 3,
            "order": 1,
        },
    ]

    entity_types = {
        annotation_uri: "annotation_property",
        object_first_uri: "object_property",
        object_second_uri: "object_property",
        datatype_uri: "datatype_property",
    }

    effective_constraints = {
        annotation_uri: {
            str(main.SH["class"]): [person_uri],
            str(main.SH.datatype): [str(main.XSD.string)],
        },
        object_first_uri: {
            str(main.SH["class"]): [person_uri],
            str(main.SH.datatype): [],
        },
        object_second_uri: {
            str(main.SH["class"]): [person_uri],
            str(main.SH.datatype): [],
        },
        datatype_uri: {
            str(main.SH["class"]): [],
            str(main.SH.datatype): [str(main.XSD.string)],
        },
    }

    profile = main.ApplicationProfile(
        store=AsyncMock(),
    )

    profile._list_active_properties = AsyncMock(
        return_value=group,
    )

    profile._constraint_resolver.get_active_datatypes = AsyncMock(
        return_value=set(),
    )

    profile._constraint_resolver.get_entity_constraints = AsyncMock(
        side_effect=lambda uri, entity_type: {
            "effective": effective_constraints[uri],
        },
    )

    profile._get_property_constraints = AsyncMock(
        return_value={},
    )

    monkeypatch.setattr(
        main,
        "_get_property_entity_type",
        lambda uri: entity_types[uri],
    )

    monkeypatch.setattr(
        main,
        "_validate_profile_range_constraint_compatibility",
        lambda *args, **kwargs: None,
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

    monkeypatch.setattr(
        main,
        "get_label",
        lambda uri: uri.rsplit("/", 1)[-1],
    )

    result = await profile.get_properties_for_class(
        "http://example.org/Book",
    )

    assert [item["uri"] for item in result] == [
        annotation_uri,
        object_first_uri,
        object_second_uri,
        datatype_uri,
    ]

    assert [item["groupOrder"] for item in result] == [
        1, 2, 2, 3,
    ]

    assert [item["order"] for item in result] == [
        1, 1, 2, 1,
    ]

    assert [item["groupUri"] for item in result] == [
        GROUP_ANNOTATION,
        GROUP_OBJECT,
        GROUP_OBJECT,
        GROUP_DATATYPE,
    ]

    assert [item["groupLabel"] for item in result] == [
        "Annotation Properties",
        "Object Properties",
        "Object Properties",
        "Datatype Properties",
    ]


@pytest.mark.asyncio
async def test_update_profile_order_accepts_one_complete_group(
    monkeypatch,
):
    store = AsyncMock()

    store.query.side_effect = [
        [
            {"propUri": PROPERTY_A, "group": GROUP_OBJECT},
            {"propUri": PROPERTY_B, "group": GROUP_OBJECT},
        ],
        [
            {"propUri": PROPERTY_A},
            {"propUri": PROPERTY_B},
        ],
    ]

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "invalidate_profile", lambda: None)

    result = await main.update_profile_order({
        "items": [
            {"uri": PROPERTY_B, "order": 1},
            {"uri": PROPERTY_A, "order": 2},
        ],
    })

    assert result == {"status": "ok"}
    store.query.assert_awaited()
    store.update.assert_awaited_once()

    update = store.update.await_args.args[0]

    assert "DELETE" in update
    assert "INSERT" in update
    assert "sh:order" in update
    assert GROUP_OBJECT in update


@pytest.mark.asyncio
async def test_update_profile_order_rejects_duplicate_properties(
    monkeypatch,
):
    store = AsyncMock()
    monkeypatch.setattr(main, "store", store)

    with pytest.raises(HTTPException) as exc_info:
        await main.update_profile_order({
            "items": [
                {"uri": PROPERTY_A, "order": 1},
                {"uri": PROPERTY_A, "order": 2},
            ],
        })

    assert exc_info.value.status_code == 400
    store.query.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_profile_order_rejects_inactive_properties(
    monkeypatch,
):
    store = AsyncMock()
    store.query.return_value = []

    monkeypatch.setattr(main, "store", store)

    with pytest.raises(HTTPException) as exc_info:
        await main.update_profile_order({
            "items": [
                {"uri": PROPERTY_A, "order": 1},
            ],
        })

    assert exc_info.value.status_code == 400
    store.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_profile_order_rejects_mixed_groups(
    monkeypatch,
):
    store = AsyncMock()
    store.query.return_value = [
        {"propUri": PROPERTY_A, "group": GROUP_OBJECT},
        {"propUri": PROPERTY_B, "group": GROUP_DATATYPE},
    ]

    monkeypatch.setattr(main, "store", store)

    with pytest.raises(HTTPException) as exc_info:
        await main.update_profile_order({
            "items": [
                {"uri": PROPERTY_A, "order": 1},
                {"uri": PROPERTY_B, "order": 2},
            ],
        })

    assert exc_info.value.status_code == 400
    assert store.query.await_count == 1
    store.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_profile_order_rejects_incomplete_group(
    monkeypatch,
):
    store = AsyncMock()

    store.query.side_effect = [
        [
            {"propUri": PROPERTY_A, "group": GROUP_OBJECT},
        ],
        [
            {"propUri": PROPERTY_A},
            {"propUri": PROPERTY_B},
        ],
    ]

    monkeypatch.setattr(main, "store", store)

    with pytest.raises(HTTPException) as exc_info:
        await main.update_profile_order({
            "items": [
                {"uri": PROPERTY_A, "order": 1},
            ],
        })

    assert exc_info.value.status_code == 400
    store.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_profile_order_rejects_noncontiguous_orders(
    monkeypatch,
):
    store = AsyncMock()
    monkeypatch.setattr(main, "store", store)

    with pytest.raises(HTTPException) as exc_info:
        await main.update_profile_order({
            "items": [
                {"uri": PROPERTY_A, "order": 1},
                {"uri": PROPERTY_B, "order": 3},
            ],
        })

    assert exc_info.value.status_code == 400
    store.query.assert_not_awaited()

@pytest.mark.asyncio
async def test_update_profile_order_rejects_zero_based_values(
    monkeypatch,
):
    store = AsyncMock()
    monkeypatch.setattr(main, "store", store)

    with pytest.raises(HTTPException) as exc_info:
        await main.update_profile_order({
            "items": [
                {"uri": PROPERTY_A, "order": 0},
            ],
        })

    assert exc_info.value.status_code == 400
    assert "positive integers" in exc_info.value.detail
    store.query.assert_not_awaited()
    store.update.assert_not_awaited()