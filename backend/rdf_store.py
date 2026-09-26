"""
Abstract RDF store interface used by Semantta.

This module intentionally defines only the operations required by the
application.
"""

from __future__ import annotations

from typing import Any, Dict, List, Protocol

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

    async def bulk_load_nt(self, nt_data: str) -> None:
        ...

    async def get_all_instances(self) -> List[Dict[str, Any]]:
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