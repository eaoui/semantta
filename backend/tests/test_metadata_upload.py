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
    def __init__(self, existing_graphs=None):
        self.bulk_calls = []
        self.update_calls = []
        self.existing_graphs = set(
            existing_graphs or []
        )

    async def bulk_load_nt_file(self, file_path, graph_uri):
        self.bulk_calls.append((Path(file_path), graph_uri))

    async def update(self, sparql):
        self.update_calls.append(sparql)

    async def query(self, sparql):
        return []

    async def graph_exists(self, graph_uri):
        return graph_uri in self.existing_graphs


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


@pytest.mark.parametrize(
    "existing_metadata",
    [True, False],
)
def test_failed_file_replacement_rolls_back_metadata_upload(
    tmp_path,
    monkeypatch,
    existing_metadata,
):
    import asyncio

    original_metadata_dir = main.METADATA_DIR
    original_store = main.store

    original_ontologies = main.state["ontologies"]
    original_metadata_files = main.state["metadata_files"]
    original_metadata_only_sources = (
        main.state["metadata_only_sources"]
    )
    original_created_instances = (
        main.state["created_instances"]
    )
    original_created_instances_graph = (
        main.state["created_instances_graph"]
    )
    original_metadata_graph_stats = (
        main.state["metadata_graph_stats"]
    )

    metadata_path = tmp_path / "records.ttl"
    meta_path = tmp_path / "records.ttl.meta.json"

    graph_uri = main.metadata_graph_uri(
        "records.ttl"
    )

    original_content = b"original metadata"
    original_meta_content = b'{"vocab_integrated": false}'

    try:
        main.METADATA_DIR = tmp_path

        if existing_metadata:
            metadata_path.write_bytes(
                original_content
            )

            meta_path.write_bytes(
                original_meta_content
            )

            main.state["metadata_files"] = [
                {
                    "filename": "records.ttl",
                    "graph_uri": graph_uri,
                    "vocab_integrated": False,
                }
            ]

            store = WorkingStore(
                {graph_uri}
            )
        else:
            main.state["metadata_files"] = []
            store = WorkingStore()

        main.state["ontologies"] = [
            {"filename": "test.ttl"}
        ]

        main.state["metadata_only_sources"] = {}
        main.state["created_instances"] = set()
        main.state["created_instances_graph"] = main.Graph()
        main.state["metadata_graph_stats"] = {}

        main.store = store

        # Prevent unrelated cache and application side
        # effects from influencing this regression test.
        monkeypatch.setattr(
            main,
            "invalidate_instance_count",
            lambda: None,
        )
        monkeypatch.setattr(
            main,
            "invalidate_caches",
            lambda: None,
        )
        monkeypatch.setattr(
            main,
            "clear_metadata_graph_stats",
            lambda: None,
        )
        monkeypatch.setattr(
            main,
            "rebuild_used_uris",
            AsyncMock(),
        )
        monkeypatch.setattr(
            main.ap,
            "invalidate",
            lambda: None,
        )

        original_replace = main.os.replace

        def fail_on_staged_sidecar(
            source,
            destination,
        ):
            source_path = Path(source)
            destination_path = Path(destination)

            if (
                source_path.name
                == "records.ttl.meta.json"
                and source_path.parent.name.startswith(
                    "semantta-metadata-"
                )
                and destination_path == meta_path
            ):
                raise OSError(
                    "Simulated sidecar replacement failure"
                )

            return original_replace(
                source,
                destination,
            )

        monkeypatch.setattr(
            main.os,
            "replace",
            fail_on_staged_sidecar,
        )

        async def run_upload():
            with pytest.raises(
                HTTPException
            ) as exc_info:
                await main.upload_metadata(
                    file=_upload("records.ttl"),
                    integrate_vocab=False,
                )

            assert exc_info.value.status_code == 400

        asyncio.run(
            run_upload()
        )

        # The failure must occur after the graph commit,
        # exercising the post-commit recovery path.
        assert any(
            "MOVE GRAPH" in update
            for update in store.update_calls
        )

        # Both files must return to their original state.
        if existing_metadata:
            assert (
                metadata_path.read_bytes()
                == original_content
            )

            assert (
                meta_path.read_bytes()
                == original_meta_content
            )
        else:
            assert not metadata_path.exists()
            assert not meta_path.exists()

        # Application state must remain unchanged.
        if existing_metadata:
            assert (
                main.state["metadata_files"][0]["filename"]
                == "records.ttl"
            )
        else:
            assert main.state["metadata_files"] == []

        # The default graph and affected named graph must
        # be restored after the committed update fails.
        rollback_updates = [
            update
            for update in store.update_calls
            if (
                "CLEAR DEFAULT" in update
                and "ADD SILENT GRAPH" in update
            )
        ]

        assert rollback_updates

        rollback_update = rollback_updates[-1]

        if existing_metadata:
            assert "COPY GRAPH" in rollback_update
        else:
            assert (
                f"DROP SILENT GRAPH <{graph_uri}>"
                in rollback_update
            )

    finally:
        main.METADATA_DIR = original_metadata_dir
        main.store = original_store

        main.state["ontologies"] = original_ontologies
        main.state["metadata_files"] = original_metadata_files
        main.state["metadata_only_sources"] = (
            original_metadata_only_sources
        )
        main.state["created_instances"] = (
            original_created_instances
        )
        main.state["created_instances_graph"] = (
            original_created_instances_graph
        )
        main.state["metadata_graph_stats"] = (
            original_metadata_graph_stats
        )


def test_restore_file_does_not_delete_destination_without_backup(
    tmp_path,
):
    destination = tmp_path / "records.ttl"
    backup = tmp_path / "missing.backup"

    destination.write_text(
        "current content",
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError):
        main._restore_file(
            destination,
            backup,
            existed_before=True,
        )

    assert destination.read_text(
        encoding="utf-8"
    ) == "current content"


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

def test_metadata_files_after_upload_preserves_existing_sources(
    monkeypatch,
):
    existing_graph_uri = main.metadata_graph_uri(
        "existing.ttl"
    )
    previous_graph_uri = main.metadata_graph_uri(
        "records.ttl"
    )
    replacement_graph_uri = main.metadata_graph_uri(
        "records.ttl"
    )

    monkeypatch.setitem(
        main.state,
        "metadata_files",
        [
            {
                "filename": "existing.ttl",
                "graph_uri": existing_graph_uri,
                "vocab_integrated": False,
            },
            {
                "filename": "records.ttl",
                "graph_uri": previous_graph_uri,
                "vocab_integrated": False,
            },
        ],
    )

    candidate_files = main._metadata_files_after_upload(
        "records.ttl",
        replacement_graph_uri,
        True,
    )

    assert [
        item["filename"]
        for item in candidate_files
    ] == [
        "existing.ttl",
        "records.ttl",
    ]

    assert (
        candidate_files[0]["graph_uri"]
        == existing_graph_uri
    )

    assert (
        candidate_files[1]["graph_uri"]
        == replacement_graph_uri
    )

    assert (
        candidate_files[1]["vocab_integrated"]
        is True
    )

@pytest.mark.asyncio
async def test_rebuild_default_graph_includes_all_metadata_sources(
    monkeypatch,
):
    metadata_files = [
        {
            "filename": "first.ttl",
            "graph_uri": main.metadata_graph_uri(
                "first.ttl"
            ),
            "vocab_integrated": False,
        },
        {
            "filename": "second.ttl",
            "graph_uri": main.metadata_graph_uri(
                "second.ttl"
            ),
            "vocab_integrated": True,
        },
    ]

    existing_graphs = {
        item["graph_uri"]
        for item in metadata_files
    }
    store = WorkingStore(existing_graphs)

    monkeypatch.setattr(
        main,
        "store",
        store,
    )
    monkeypatch.setitem(
        main.state,
        "metadata_files",
        metadata_files,
    )
    monkeypatch.setitem(
        main.state,
        "created_instances_graph",
        main.Graph(),
    )

    await main.rebuild_default_data_graph()

    assert "CLEAR DEFAULT" in store.update_calls

    for metadata_file in metadata_files:
        assert (
            f"ADD GRAPH <{metadata_file['graph_uri']}> TO DEFAULT"
            in store.update_calls
        )

def test_load_saved_metadata_reads_current_sidecar(
    tmp_path,
    monkeypatch,
):
    metadata_file = tmp_path / "records.ttl"
    metadata_file.write_text(
        "@prefix ex: <http://example.org/> .",
        encoding="utf-8",
    )

    sidecar = tmp_path / "records.ttl.meta.json"
    sidecar.write_text(
        '{"vocab_integrated": false}',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        main,
        "METADATA_DIR",
        tmp_path,
    )
    monkeypatch.setitem(
        main.state,
        "metadata_files",
        [],
    )

    main.load_saved_metadata()

    assert len(main.state["metadata_files"]) == 1

    metadata_info = main.state["metadata_files"][0]

    assert metadata_info["filename"] == "records.ttl"
    assert metadata_info["vocab_integrated"] is False