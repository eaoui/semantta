import sys
from pathlib import Path
from unittest.mock import AsyncMock

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