"""
Async Fuseki SPARQL 1.1 store for Semantta.
Handles all communication with the triplestore, including bulk loads,
instance retrieval, and SHACL shape management.
"""

from typing import Any, Dict, List, Optional

from fastapi import HTTPException
import httpx
from rdflib import Graph

from utils import shape_uri_for_entity

SHAPES_GRAPH = "urn:profile:shapes"


class FusekiStore:
    """Async wrapper around an Apache Jena Fuseki dataset."""

    def __init__(
        self,
        dataset_url: str = "http://localhost:3030/obmms",
        label_properties: Optional[List[str]] = None,
    ):
        self.dataset = dataset_url
        self.query_url = f"{dataset_url}/query"
        self.update_url = f"{dataset_url}/update"
        self.data_url = f"{dataset_url}/data"
        self.client = httpx.AsyncClient(timeout=120.0)

        # Optional list of label property URIs (rdfs:label sub‑properties)
        self.label_properties: List[str] = label_properties or []

    async def close(self):
        await self.client.aclose()

    def set_label_properties(self, uris: List[str]):
        """Update the label property list used for instance labelling."""
        self.label_properties = uris[:]

    # ── Core SPARQL operations ──────────────────────────────────────────

    async def _sparql_query(self, sparql: str) -> List[Dict[str, str]]:
        """Execute a SPARQL SELECT/ASK query and return the bindings."""
        try:
            resp = await self.client.get(
                self.query_url,
                params={"query": sparql},
                headers={"Accept": "application/sparql-results+json"},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]  # truncate to avoid huge responses
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"SPARQL query failed: {detail}",
            )
        bindings = resp.json()["results"]["bindings"]
        return [{k: v["value"] for k, v in row.items()} for row in bindings]

    async def _sparql_update(self, sparql: str):
        """Execute a SPARQL UPDATE request."""
        try:
            resp = await self.client.post(
                self.update_url,
                data={"update": sparql},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]  # truncate to avoid huge responses
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"SPARQL query failed: {detail}",
            )

    async def _sparql_construct(self, sparql: str, accept: str = "text/turtle") -> str:
        """Execute a SPARQL CONSTRUCT query and return the serialised RDF."""
        try:
            resp = await self.client.get(
                self.query_url,
                params={"query": sparql},
                headers={"Accept": accept},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]  # truncate to avoid huge responses
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"SPARQL query failed: {detail}",
            )
        return resp.text

    # ── High‑level operations ──────────────────────────────────────────

    async def bulk_load_nt(self, nt_data: str):
        """Load N‑Triples data into the default graph."""
        resp = await self.client.post(
            self.data_url + "?default",
            content=nt_data.encode("utf-8"),
            headers={"Content-Type": "application/n-triples"},
        )
        resp.raise_for_status()

    async def _fetch_best_labels(self, uris: List[str]) -> Dict[str, str]:
        """
        Return the best available label for each URI,
        using the configured label properties in priority order.
        """
        if not uris or not self.label_properties:
            return {}

        # Build OPTIONAL patterns for each label property
        clauses = []
        for i, prop in enumerate(self.label_properties):
            clauses.append(f"OPTIONAL {{ ?instance <{prop}> ?lbl{i} }}")

        coalesce_parts = ", ".join(f"?lbl{i}" for i in range(len(self.label_properties)))
        query = f"""
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?instance (COALESCE({coalesce_parts}) AS ?label)
            WHERE {{
                VALUES ?instance {{ {" ".join(f"<{u}>" for u in uris)} }}
                {" ".join(clauses)}
            }}
        """
        rows = await self._sparql_query(query)
        label_map = {}
        for r in rows:
            lbl = r.get("label")
            if lbl and r["instance"] not in label_map:
                label_map[r["instance"]] = lbl
        return label_map

    async def get_all_instances(self) -> List[Dict[str, Any]]:
        """
        Retrieve every instance (subject with rdf:type) from the default graph,
        including their properties and a best‑effort label.
        """
        rows = await self._sparql_query("""
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?instance ?type ?prop ?value WHERE {
                ?instance a ?type .
                OPTIONAL { ?instance ?prop ?value . FILTER(?prop != rdf:type) }
            }
        """)

        instances: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            uri = row["instance"]
            if uri not in instances:
                instances[uri] = {
                    "uri": uri,
                    "types": [],
                    "properties": {},
                    "is_blank": uri.startswith("urn:bnid:"),
                    "label": None,
                }

            t = row.get("type")
            if t and t not in instances[uri]["types"]:
                instances[uri]["types"].append(t)

            p = row.get("prop")
            v = row.get("value")
            if p and v:
                instances[uri]["properties"].setdefault(p, []).append(v)

        # Deduplicate property values
        for inst in instances.values():
            for prop in inst["properties"]:
                seen = set()
                uniq = []
                for val in inst["properties"][prop]:
                    if val not in seen:
                        seen.add(val)
                        uniq.append(val)
                inst["properties"][prop] = uniq

        # Attach labels
        all_uris = list(instances.keys())
        if all_uris:
            label_map = await self._fetch_best_labels(all_uris)
            for uri, lbl in label_map.items():
                if lbl:
                    instances[uri]["label"] = lbl

        return list(instances.values())

    # ── SHACL shape management ─────────────────────────────────────────

    async def load_shapes_graph(self) -> Graph:
        """Return a copy of the SHACL shapes named graph."""
        query = f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH <{SHAPES_GRAPH}> {{ ?s ?p ?o }} }}"
        turtle = await self._sparql_construct(query)
        g = Graph()
        g.parse(data=turtle, format="turtle")
        return g

    async def insert_shapes(self, triples: str):
        await self._sparql_update(
            f"PREFIX sh: <http://www.w3.org/ns/shacl#>\n"
            f"INSERT DATA {{ GRAPH <{SHAPES_GRAPH}> {{ {triples} }} }}"
        )

    async def add_property_shape(self, class_uri: str, prop_uri: str, prefix_map: dict):
        shape_uri = shape_uri_for_entity(prop_uri, "property", prefix_map)
        class_shape = shape_uri_for_entity(class_uri, "class", prefix_map)

        await self._sparql_update(
            f"PREFIX sh: <http://www.w3.org/ns/shacl#>\n"
            f"INSERT DATA {{ GRAPH <{SHAPES_GRAPH}> {{ "
            f"<{shape_uri}> a sh:PropertyShape ; sh:path <{prop_uri}> . "
            f"}} }}"
        )
        await self._sparql_update(
            f"PREFIX sh: <http://www.w3.org/ns/shacl#>\n"
            f"INSERT DATA {{ GRAPH <{SHAPES_GRAPH}> {{ "
            f"<{class_shape}> sh:property <{shape_uri}> . "
            f"}} }}"
        )

    async def remove_property_shape(self, class_uri: str, prop_uri: str, prefix_map: dict):
        shape_uri = shape_uri_for_entity(prop_uri, "property", prefix_map)
        class_shape = shape_uri_for_entity(class_uri, "class", prefix_map)

        await self._sparql_update(
            f"PREFIX sh: <http://www.w3.org/ns/shacl#>\n"
            f"DELETE WHERE {{ GRAPH <{SHAPES_GRAPH}> {{ "
            f"<{class_shape}> sh:property <{shape_uri}> . "
            f"}} }}"
        )

    async def remove_class_shape(self, class_uri: str, prefix_map: dict):
        """Remove a class shape and all its attached property shapes."""
        shape_uri = shape_uri_for_entity(class_uri, "class", prefix_map)
        await self._sparql_update(
            f"DELETE WHERE {{ GRAPH <{SHAPES_GRAPH}> {{ <{shape_uri}> ?p ?o }} }}"
        )