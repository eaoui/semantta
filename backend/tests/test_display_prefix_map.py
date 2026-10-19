import sys
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main


def test_display_prefix_map_generates_missing_ontology_namespace(
    monkeypatch,
):
    namespace = "https://example.org/bibframe/"
    entity_uri = URIRef(f"{namespace}Contribution")

    graph = Graph()
    graph.add((entity_uri, RDF.type, OWL.Class))

    monkeypatch.setitem(
        main.state,
        "prefix_map",
        {
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf",
            "http://www.w3.org/2002/07/owl#": "owl",
        },
    )
    monkeypatch.setitem(
        main.state,
        "ontologies",
        [{"graph": graph}],
    )

    display_map = main.build_display_prefix_map()

    assert namespace in display_map
    assert display_map[namespace] == "bibframe"
    assert (
        display_map[namespace]
        + ":"
        + str(entity_uri)[len(namespace):]
    ) == "bibframe:Contribution"


def test_display_prefix_map_preserves_declared_prefixes(
    monkeypatch,
):
    namespace = "https://example.org/vocab#"

    graph = Graph()
    graph.bind("ex", namespace)
    graph.add((
        URIRef(f"{namespace}Thing"),
        RDF.type,
        OWL.Class,
    ))

    monkeypatch.setitem(
        main.state,
        "prefix_map",
        {namespace: "ex"},
    )
    monkeypatch.setitem(
        main.state,
        "ontologies",
        [{"graph": graph}],
    )

    assert main.build_display_prefix_map()[namespace] == "ex"