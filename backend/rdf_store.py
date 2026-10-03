"""
Abstract RDF store interface used by Semantta.

This module intentionally defines only the operations required by the
application.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol
from pathlib import Path
from rdflib import Graph


class RDFStore(Protocol):
    """Interface required by the Semantta application."""

    async def close(self) -> None:
        ...

    async def healthcheck(self) -> bool:
        ...

    def set_label_properties(self, uris: List[str]) -> None:
        ...

    async def query(self, sparql: str) -> List[Dict[str, str]]:
        ...

    async def update(self, sparql: str) -> None:
        ...

    async def construct(
        self,
        sparql: str,
        accept: str = "text/turtle",
    ) -> str:
        ...

    async def bulk_load_nt(
        self,
        nt_data: str,
    ) -> None:
        ...

    async def bulk_load_nt_file(
        self,
        file_path: str | Path,
    ) -> None:
        ...

    async def count_instances(
        self,
        *,
        search: str = "",
        type_uri: Optional[str] = None,
        include_blank_nodes: bool = False,
        include_uris: Optional[List[str]] = None,
        exclude_uris: Optional[List[str]] = None,
    ) -> int:
        ...

    async def get_instance_labels(
        self,
        uris: List[str],
    ) -> Dict[str, str]:
        ...

    async def list_instances(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        search: str = "",
        type_uri: Optional[str] = None,
        include_blank_nodes: bool = False,
        include_uris: Optional[List[str]] = None,
        exclude_uris: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        ...

    async def get_instance_types(
        self,
        limit: int = 10000,
    ) -> List[str]:
        ...

    async def load_shapes_graph(self) -> Graph:
        ...

    async def insert_shapes(self, triples: str) -> None:
        ...

    async def add_property_shape(
        self,
        class_uri: str,
        prop_uri: str,
        prefix_map: dict,
    ) -> None:
        ...

    async def remove_property_shape(
        self,
        class_uri: str,
        prop_uri: str,
        prefix_map: dict,
    ) -> None:
        ...

    async def remove_class_shape(
        self,
        class_uri: str,
        prefix_map: dict,
    ) -> None:
        ...