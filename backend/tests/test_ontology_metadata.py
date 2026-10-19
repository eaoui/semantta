import json
import sys
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


def make_ontology_graph():
    graph = Graph()

    ontology_iri = URIRef("https://example.org/catalog")
    version_iri = URIRef("https://example.org/catalog/2.0")

    graph.add((ontology_iri, RDF.type, OWL.Ontology))
    graph.add((ontology_iri, OWL.versionIRI, version_iri))
    graph.add((ontology_iri, RDFS.label, Literal("Example Catalog")))
    graph.add((ontology_iri, OWL.versionInfo, Literal("2.0")))

    # Simulate a version IRI that is also typed and labelled as an ontology.
    graph.add((version_iri, RDF.type, OWL.Ontology))
    graph.add((version_iri, RDFS.label, Literal("Example Catalog 2.0")))

    return graph


def test_metadata_extraction_prefers_canonical_ontology_iri():
    metadata = main.extract_ontology_metadata(make_ontology_graph())

    assert metadata == {
        "title": "Example Catalog",
        "version": "2.0",
        "iri": "https://example.org/catalog",
    }


def test_metadata_extraction_is_independent_of_triple_insertion_order():
    graph = make_ontology_graph()
    reversed_graph = Graph()

    for triple in reversed(list(graph)):
        reversed_graph.add(triple)

    assert main.extract_ontology_metadata(graph) == (
        main.extract_ontology_metadata(reversed_graph)
    )


def test_saved_ontology_metadata_is_reused_after_reload(
    tmp_path,
    monkeypatch,
):
    source_path = tmp_path / "example.ttl"
    source_path.write_text("# original ontology source", encoding="utf-8")

    metadata_path = tmp_path / "cache" / "example.ttl.reasoned.meta.json"

    monkeypatch.setattr(main, "ONTOLOGY_DIR", tmp_path)
    monkeypatch.setattr(
        main,
        "reasoned_cache_metadata_path",
        lambda filename: metadata_path,
    )

    original_metadata = main._load_ontology_metadata(
        "example.ttl",
        make_ontology_graph(),
    )

    saved = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert saved["ontology_metadata"] == original_metadata

    # Simulate loading the same source again: persisted metadata should be
    # returned instead of making a new selection from the graph.
    different_graph = Graph()
    different_graph.add((
        URIRef("https://example.org/other"),
        RDF.type,
        OWL.Ontology,
    ))
    different_graph.add((
        URIRef("https://example.org/other"),
        RDFS.label,
        Literal("Different ontology"),
    ))

    reloaded_metadata = main._load_ontology_metadata(
        "example.ttl",
        different_graph,
    )

    assert reloaded_metadata == original_metadata


def test_dc_title_is_used_when_rdfs_label_is_missing():
    graph = Graph()
    ontology_iri = URIRef("https://example.org/catalog")

    graph.add((ontology_iri, RDF.type, OWL.Ontology))
    graph.add((
        ontology_iri,
        main.DC_TITLE,
        Literal("Example Catalog"),
    ))

    metadata = main.extract_ontology_metadata(graph)

    assert metadata["title"] == "Example Catalog"


def test_rdfs_label_is_preferred_over_dc_title():
    graph = Graph()
    ontology_iri = URIRef("https://example.org/catalog")

    graph.add((ontology_iri, RDF.type, OWL.Ontology))
    graph.add((
        ontology_iri,
        RDFS.label,
        Literal("Preferred RDFS label"),
    ))
    graph.add((
        ontology_iri,
        main.DC_TITLE,
        Literal("Alternative DC title"),
    ))

    metadata = main.extract_ontology_metadata(graph)

    assert metadata["title"] == "Preferred RDFS label"


def test_rdfs_label_subproperty_is_preferred_over_dc_title():
    graph = Graph()
    ontology_iri = URIRef("https://example.org/catalog")
    custom_label = URIRef("https://example.org/vocab/displayLabel")

    graph.add((ontology_iri, RDF.type, OWL.Ontology))
    graph.add((custom_label, RDFS.subPropertyOf, RDFS.label))
    graph.add((
        ontology_iri,
        custom_label,
        Literal("Custom label"),
    ))
    graph.add((
        ontology_iri,
        main.DC_TITLE,
        Literal("Alternative DC title"),
    ))

    metadata = main.extract_ontology_metadata(graph)

    assert metadata["title"] == "Custom label"

def test_dcterms_title_is_used_when_dc_title_is_missing():
    graph = Graph()
    ontology_iri = URIRef("https://example.org/catalog")

    graph.add((ontology_iri, RDF.type, OWL.Ontology))
    graph.add((
        ontology_iri,
        main.DCTERMS_TITLE,
        Literal("Example Catalog"),
    ))

    metadata = main.extract_ontology_metadata(graph)

    assert metadata["title"] == "Example Catalog"


def test_dc_title_is_preferred_over_dcterms_title():
    graph = Graph()
    ontology_iri = URIRef("https://example.org/catalog")

    graph.add((ontology_iri, RDF.type, OWL.Ontology))
    graph.add((
        ontology_iri,
        main.DC_TITLE,
        Literal("DC Elements title"),
    ))
    graph.add((
        ontology_iri,
        main.DCTERMS_TITLE,
        Literal("DC Terms title"),
    ))

    metadata = main.extract_ontology_metadata(graph)

    assert metadata["title"] == "DC Elements title"


def test_ontology_iri_namespace_is_excluded():
    graph = Graph()
    ontology_iri = URIRef("https://example.org/catalog")

    graph.bind("catalog", "https://example.org/catalog/")
    graph.add((ontology_iri, RDF.type, OWL.Ontology))
    graph.add((
        URIRef("https://example.org/catalog/Book"),
        RDF.type,
        OWL.Class,
    ))

    namespaces = main.get_ontology_namespaces(graph)

    assert not any(
        main._normalize_namespace_delimiters(namespace)
        == main._normalize_namespace_delimiters(str(ontology_iri))
        for namespace in namespaces
    )