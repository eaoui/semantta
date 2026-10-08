import io
import sys
from pathlib import Path
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
    main.state["created_instances_graph"].remove(
        list(main.state["created_instances_graph"])
    )


async def _noop(*args, **kwargs):
    return None


def test_placeholder():
    assert True