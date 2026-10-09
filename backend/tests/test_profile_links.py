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
async def test_property_links_validate_before_mutation(monkeypatch):
    store = AsyncMock()
    store.query.return_value = [{"class": CLASS_URI}]

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(
        main, "get_property_domains",
        lambda _: [CLASS_URI],
    )
    monkeypatch.setattr(
        main, "is_subclass",
        lambda child, parents: False,
    )

    with pytest.raises(HTTPException) as exc_info:
        await main._sync_entity_links(
            PROPERTY_URI,
            "object_property",
            [OTHER_CLASS_URI],
        )

    assert exc_info.value.status_code == 400
    store.update.assert_not_awaited()


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
    store.query.return_value = [{"class": CLASS_URI}]

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
    assert "DELETE DATA" in update
    assert "INSERT DATA" in update