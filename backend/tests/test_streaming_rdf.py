import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from streaming_rdf import (
    RelativeIRIWithoutBaseError,
    stream_rdf_to_ntriples,
)


def test_absolute_iris_are_preserved_without_a_base(
    tmp_path,
):
    source = tmp_path / "records.ttl"
    target = tmp_path / "records.nt"

    source.write_text(
        '@prefix ex: <https://example.org/> .\n'
        'ex:book1 ex:title "A book" .\n',
        encoding="utf-8",
    )

    count = stream_rdf_to_ntriples(
        source,
        "turtle",
        target,
    )

    output = target.read_text(encoding="utf-8")

    assert count == 1
    assert (
        "<https://example.org/book1>"
        in output
    )
    assert (
        "<https://example.org/title>"
        in output
    )
    assert str(tmp_path) not in output


def test_relative_iris_use_the_declared_absolute_base(
    tmp_path,
):
    source = tmp_path / "records.ttl"
    target = tmp_path / "records.nt"

    source.write_text(
        '@base <https://example.org/catalog/> .\n'
        '<book1> <title> "A book" .\n',
        encoding="utf-8",
    )

    count = stream_rdf_to_ntriples(
        source,
        "turtle",
        target,
    )

    output = target.read_text(encoding="utf-8")

    assert count == 1
    assert (
        "<https://example.org/catalog/book1>"
        in output
    )
    assert (
        "<https://example.org/catalog/title>"
        in output
    )


def test_relative_iris_without_a_base_are_rejected(
    tmp_path,
):
    source = tmp_path / "records.ttl"
    target = tmp_path / "records.nt"

    source.write_text(
        '@prefix ex: <https://example.org/> .\n'
        '<lclang> ex:title "A book" .\n',
        encoding="utf-8",
    )

    with pytest.raises(
        RelativeIRIWithoutBaseError,
        match="explicit absolute base URI",
    ):
        stream_rdf_to_ntriples(
            source,
            "turtle",
            target,
        )

    assert (
        "semantta.invalid"
        not in target.read_text(encoding="utf-8")
    )