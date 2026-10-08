import io
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import tempfile

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock

from fastapi import HTTPException, UploadFile

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


RDF_CONTENT = b"""
@prefix ex: <http://example.org/> .

ex:book1 ex:title "New title" .
"""


class FailingStore:
    def __init__(self):
        self.bulk_calls = []
        self.update_calls = []

    async def bulk_load_nt_file(self, file_path, graph_uri):
        self.bulk_calls.append((Path(file_path), graph_uri))
        raise RuntimeError("simulated Fuseki failure")

    async def update(self, sparql):
        self.update_calls.append(sparql)

    async def query(self, sparql):
        return []

    async def graph_exists(self, graph_uri):
        return True


class WorkingStore:
    def __init__(self):
        self.bulk_calls = []
        self.update_calls = []

    async def bulk_load_nt_file(self, file_path, graph_uri):
        self.bulk_calls.append((Path(file_path), graph_uri))

    async def update(self, sparql):
        self.update_calls.append(sparql)

    async def query(self, sparql):
        return []

    async def graph_exists(self, graph_uri):
        return True


def _upload(filename: str = "records.ttl"):
    return UploadFile(
        file=io.BytesIO(RDF_CONTENT),
        filename=filename,
    )


def _reset_metadata_state():
    main.state["metadata_files"] = []
    main.state["metadata_only_sources"] = {}
    main.state["created_instances"].clear()
    main.state["created_instances_graph"].remove((None, None, None))


async def _noop(*args, **kwargs):
    return None


def test_placeholder():
    assert True



def test_failed_fuseki_import_preserves_existing_file(
    tmp_path,
):
    # Patch application state/storage.
    original_metadata_dir = main.METADATA_DIR
    original_store = main.store
    original_ontologies = list(
        main.state["ontologies"]
    )
    original_metadata_files = list(
        main.state["metadata_files"]
    )
    original_created_instances = set(
        main.state["created_instances"]
    )

    try:
        main.METADATA_DIR = tmp_path

        existing_file = (
            tmp_path / "records.ttl"
        )

        existing_content = (
            b"""
            @prefix ex: <http://example.org/> .
            ex:old ex:title "Original" .
            """
        )

        existing_file.write_bytes(
            existing_content
        )

        main.state["ontologies"] = [
            {"filename": "test.ttl"}
        ]

        main.state["metadata_files"] = [
            {
                "filename": "records.ttl",
                "graph_uri":
                    main.metadata_graph_uri(
                        "records.ttl"
                    ),
                "vocab_integrated": False,
                "instances_merged": True,
            }
        ]

        main.state[
            "metadata_only_sources"
        ] = {}

        main.state[
            "created_instances"
        ] = set()

        main.state["created_instances_graph"].remove((None, None, None))

        main.store = FailingStore()

        # Suppress unrelated application side effects.
        main.invalidate_instance_count = (
            lambda: None
        )
        main.invalidate_caches = (
            lambda: None
        )
        main.clear_metadata_graph_stats = (
            lambda: None
        )
        main.rebuild_used_uris = (
            AsyncMock()
        )

        import asyncio

        async def run():
            try:
                await main.upload_metadata(
                    file=_upload(
                        "records.ttl"
                    ),
                    integrate_vocab=False,
                    merge_instances=True,
                )
            except HTTPException as exc:
                assert exc.status_code == 400
            else:
                raise AssertionError(
                    "Expected import failure"
                )

        asyncio.run(run())

        assert (
            existing_file.read_bytes()
            == existing_content
        )

        assert main.state[
            "metadata_files"
        ][0]["filename"] == "records.ttl"

        # Most importantly, no update request should
        # have modified the final metadata graph.
        assert not any(
            "urn:semantta:metadata:"
            in update
            for update
            in main.store.update_calls
        )

    finally:
        main.METADATA_DIR = (
            original_metadata_dir
        )
        main.store = original_store
        main.state["ontologies"] = (
            original_ontologies
        )
        main.state["metadata_files"] = (
            original_metadata_files
        )
        main.state[
            "created_instances"
        ] = original_created_instances

@pytest.mark.asyncio
async def test_check_instances_exist_rejects_invalid_uri():
    original_store = main.store
    main.store = AsyncMock()

    try:
        with pytest.raises(HTTPException) as exc_info:
            await main.check_instances_exist({
                "uris": [
                    "http://example.org/good",
                    "http://example.org/> UNION { ?s ?p ?o } #",
                ]
            })

        assert exc_info.value.status_code == 400
        main.store.query.assert_not_awaited()
    finally:
        main.store = original_store


@pytest.mark.asyncio
async def test_check_instances_exist_uses_validated_uris():
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

        assert (
            "<http://example.org/book1>"
            in query
        )
        assert (
            "<urn:test:book2>"
            in query
        )
    finally:
        main.store = original_store