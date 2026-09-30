"""
Async Fuseki SPARQL 1.1 store for Semantta.
Handles all communication with the triplestore, including bulk loads,
instance retrieval, and SHACL shape management.
"""

from typing import Any, Dict, List, Optional

from fastapi import HTTPException
import httpx
from rdflib import Graph

from config import FUSEKI_CONFIG, FusekiConfig
from utils import shape_uri_for_entity

SHAPES_GRAPH = "urn:profile:shapes"


class FusekiStore:
    """Async wrapper around an Apache Jena Fuseki dataset."""

    def __init__(
        self,
        dataset_url: Optional[str] = None,
        label_properties: Optional[List[str]] = None,
        config: Optional[FusekiConfig] = None,
    ):
        fuseki_config = config or FUSEKI_CONFIG

        # Explicit dataset_url remains supported for compatibility and testing.
        dataset_url = dataset_url or fuseki_config.dataset_url
        timeout = fuseki_config.timeout

        self.dataset = dataset_url.rstrip("/")
        self.query_url = f"{self.dataset}/query"
        self.update_url = f"{self.dataset}/update"
        self.data_url = f"{self.dataset}/data"
        self.client = httpx.AsyncClient(timeout=timeout)

        # Optional list of label property URIs (rdfs:label sub-properties)
        self.label_properties: List[str] = label_properties or []

    async def close(self):
        await self.client.aclose()

    async def healthcheck(self) -> bool:
        """Check whether the configured Fuseki dataset is reachable."""
        await self.query(
            "SELECT (1 AS ?ok) WHERE {}"
        )
        return True

    def set_label_properties(self, uris: List[str]):
        """Update the label property list used for instance labelling."""
        self.label_properties = uris[:]

    # ── Core SPARQL operations ──────────────────────────────────────────

    async def query(self, sparql: str) -> List[Dict[str, str]]:
        """Execute a SPARQL SELECT query and return the bindings."""
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

    async def update(self, sparql: str) -> None:
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

    async def construct(
        self,
        sparql: str,
        accept: str = "text/turtle",
    ) -> str:
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
        rows = await self.query(query)
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
        rows = await self.query("""
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

    @staticmethod
    def _sparql_string_literal(value: str) -> str:
        """Return a safely escaped SPARQL double-quoted string literal."""
        escaped = (
            value
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        return f'"{escaped}"'

    @staticmethod
    def _iri_values(uris: List[str]) -> str:
        return " ".join(f"<{uri}>" for uri in uris)

    def _instance_constraints(
        self,
        *,
        search: str = "",
        type_uri: Optional[str] = None,
        include_blank_nodes: bool = False,
        include_uris: Optional[List[str]] = None,
        exclude_uris: Optional[List[str]] = None,
    ) -> List[str]:
        clauses = [
            "?instance a ?instanceType .",
        ]

        if not include_blank_nodes:
            clauses.append(
                'FILTER(!STRSTARTS(STR(?instance), "urn:bnid:"))'
            )

        if type_uri:
            clauses.append(
                f"?instance a <{type_uri}> ."
            )

        if search:
            literal = self._sparql_string_literal(
                search.strip().lower()
            )

            conditions = [
                "CONTAINS("
                "LCASE(STR(?instance)), "
                f"{literal})"
            ]

            for prop in self.label_properties:
                conditions.append(
                    "EXISTS { "
                    f"?instance <{prop}> ?searchLabel . "
                    "FILTER("
                    "CONTAINS("
                    "LCASE(STR(?searchLabel)), "
                    f"{literal}"
                    ")"
                    ") }"
                )

            clauses.append(
                "FILTER("
                + " || ".join(conditions)
                + ")"
            )

        if include_uris is not None:
            if not include_uris:
                clauses.append("FILTER(false)")
            else:
                clauses.append(
                    "VALUES ?instance { "
                    f"{self._iri_values(include_uris)} }}"
                )

        if exclude_uris:
            clauses.append(
                "FILTER NOT EXISTS { "
                "VALUES ?excludedInstance { "
                f"{self._iri_values(exclude_uris)} "
                "} "
                "FILTER(?instance = ?excludedInstance) "
                "}"
            )

        return clauses

    async def count_instances(
        self,
        *,
        search: str = "",
        type_uri: Optional[str] = None,
        include_blank_nodes: bool = False,
        include_uris: Optional[List[str]] = None,
        exclude_uris: Optional[List[str]] = None,
    ) -> int:
        constraints = self._instance_constraints(
            search=search,
            type_uri=type_uri,
            include_blank_nodes=include_blank_nodes,
            include_uris=include_uris,
            exclude_uris=exclude_uris,
        )

        rows = await self.query(
            "SELECT (COUNT(DISTINCT ?instance) AS ?count) "
            "WHERE { "
            + " ".join(constraints)
            + " }"
        )

        return int(rows[0]["count"]) if rows else 0

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
        """
        Retrieve a bounded page of instance summaries.

        Only URI, types, blank-node status, and label are returned.
        Full properties remain available through the individual-instance API.
        """
        constraints = self._instance_constraints(
            search=search,
            type_uri=type_uri,
            include_blank_nodes=include_blank_nodes,
            include_uris=include_uris,
            exclude_uris=exclude_uris,
        )

        uri_rows = await self.query(
            "SELECT DISTINCT ?instance WHERE { "
            + " ".join(constraints)
            + " } "
            "ORDER BY STR(?instance) "
            f"LIMIT {limit} OFFSET {offset}"
        )

        uris = [row["instance"] for row in uri_rows]

        if not uris:
            return []

        values = self._iri_values(uris)

        type_rows = await self.query(
            "PREFIX rdf: "
            "<http://www.w3.org/1999/02/22-rdf-syntax-ns#> "
            "SELECT ?instance ?type WHERE { "
            f"VALUES ?instance {{ {values} }} "
            "?instance rdf:type ?type . "
            "}"
        )

        types: Dict[str, List[str]] = {
            uri: []
            for uri in uris
        }

        for row in type_rows:
            uri = row["instance"]
            type_uri_value = row.get("type")

            if (
                type_uri_value
                and type_uri_value
                not in types.setdefault(uri, [])
            ):
                types[uri].append(type_uri_value)

        labels = await self._fetch_best_labels(uris)

        return [
            {
                "uri": uri,
                "types": types.get(uri, []),
                "properties": {},
                "is_blank": uri.startswith("urn:bnid:"),
                "label": labels.get(uri),
            }
            for uri in uris
        ]

    async def get_instance_types(
        self,
        limit: int = 10000,
    ) -> List[str]:
        rows = await self.query(
            "SELECT DISTINCT ?type WHERE { "
            "?instance a ?type . "
            "FILTER(ISIRI(?type)) "
            "} "
            "ORDER BY STR(?type) "
            f"LIMIT {limit}"
        )

        return [
            row["type"]
            for row in rows
        ]

    async def get_instance_labels(
        self,
        uris: List[str],
    ) -> Dict[str, str]:
        return await self._fetch_best_labels(
            uris,
        )

    # ── SHACL shape management ─────────────────────────────────────────

    async def load_shapes_graph(self) -> Graph:
        """Return a copy of the SHACL shapes named graph."""
        query = f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH <{SHAPES_GRAPH}> {{ ?s ?p ?o }} }}"
        turtle = await self.construct(query)
        g = Graph()
        g.parse(data=turtle, format="turtle")
        return g

    async def insert_shapes(self, triples: str):
        await self.update(
            f"PREFIX sh: <http://www.w3.org/ns/shacl#>\n"
            f"INSERT DATA {{ GRAPH <{SHAPES_GRAPH}> {{ {triples} }} }}"
        )

    async def add_property_shape(self, class_uri: str, prop_uri: str, prefix_map: dict):
        shape_uri = shape_uri_for_entity(prop_uri, "property", prefix_map)
        class_shape = shape_uri_for_entity(class_uri, "class", prefix_map)

        await self.update(
            f"PREFIX sh: <http://www.w3.org/ns/shacl#>\n"
            f"INSERT DATA {{ GRAPH <{SHAPES_GRAPH}> {{ "
            f"<{shape_uri}> a sh:PropertyShape ; sh:path <{prop_uri}> . "
            f"}} }}"
        )
        await self.update(
            f"PREFIX sh: <http://www.w3.org/ns/shacl#>\n"
            f"INSERT DATA {{ GRAPH <{SHAPES_GRAPH}> {{ "
            f"<{class_shape}> sh:property <{shape_uri}> . "
            f"}} }}"
        )

    async def remove_property_shape(self, class_uri: str, prop_uri: str, prefix_map: dict):
        shape_uri = shape_uri_for_entity(prop_uri, "property", prefix_map)
        class_shape = shape_uri_for_entity(class_uri, "class", prefix_map)

        await self.update(
            f"PREFIX sh: <http://www.w3.org/ns/shacl#>\n"
            f"DELETE WHERE {{ GRAPH <{SHAPES_GRAPH}> {{ "
            f"<{class_shape}> sh:property <{shape_uri}> . "
            f"}} }}"
        )

    async def remove_class_shape(self, class_uri: str, prefix_map: dict):
        """Remove a class shape and all its attached property shapes."""
        shape_uri = shape_uri_for_entity(class_uri, "class", prefix_map)
        await self.update(
            f"DELETE WHERE {{ GRAPH <{SHAPES_GRAPH}> {{ <{shape_uri}> ?p ?o }} }}"
        )