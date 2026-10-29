from pathlib import Path
import sys
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from rdflib import Namespace

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


EX = Namespace("https://example.org/profile-mode-test/")
SH = Namespace("http://www.w3.org/ns/shacl#")


def test_matching_legacy_value_is_inferred_as_default():
    original = {
        str(SH["class"]): [str(EX.Person)],
        "urn:domainClasses": [str(EX.Book)],
    }
    overrides = {
        str(SH["class"]): str(EX.Person),
        "urn:domainClasses": [str(EX.Book)],
    }

    modes = main._resolve_profile_field_modes(
        "object_property",
        original,
        overrides,
        {},
    )

    assert modes[str(SH["class"])] == "default"
    assert modes["urn:domainClasses"] == "default"


def test_different_legacy_value_is_inferred_as_override():
    original = {
        str(SH["class"]): [str(EX.Person)],
        "urn:domainClasses": [str(EX.Book)],
    }
    overrides = {
        str(SH["class"]): str(EX.Agent),
        "urn:domainClasses": [str(EX.Article)],
    }

    modes = main._resolve_profile_field_modes(
        "object_property",
        original,
        overrides,
        {},
    )

    assert modes[str(SH["class"])] == "override"
    assert modes["urn:domainClasses"] == "override"


def test_explicit_mode_wins_when_value_equals_default():
    original = {
        str(SH["class"]): [str(EX.Person)],
    }
    overrides = {
        str(SH["class"]): str(EX.Person),
    }

    modes = main._resolve_profile_field_modes(
        "object_property",
        original,
        overrides,
        {
            str(SH["class"]): "override",
        },
    )

    assert modes[str(SH["class"])] == "override"


def test_explicit_empty_override_remains_override():
    original = {
        str(SH["class"]): [str(EX.Person)],
    }

    modes = main._resolve_profile_field_modes(
        "object_property",
        original,
        {},
        {
            str(SH["class"]): "override",
        },
    )

    assert modes[str(SH["class"])] == "override"


def test_explicit_default_wins_over_a_different_stored_value():
    original = {
        str(SH["class"]): [str(EX.Person)],
    }
    overrides = {
        str(SH["class"]): str(EX.Agent),
    }

    modes = main._resolve_profile_field_modes(
        "object_property",
        original,
        overrides,
        {
            str(SH["class"]): "default",
        },
    )

    assert modes[str(SH["class"])] == "default"


@pytest.mark.asyncio
async def test_persist_profile_field_modes_writes_default_and_override(
    monkeypatch,
):
    store = AsyncMock()
    monkeypatch.setattr(main, "store", store)

    await main._persist_profile_field_modes(
        str(EX.title),
        {
            str(SH.datatype): "default",
            str(SH.maxCount): "override",
        },
    )

    store.update.assert_awaited_once()

    update = store.update.await_args.args[0]

    assert main.PROFILE_FIELD_STATE_GRAPH in update
    assert str(SH.datatype) in update
    assert str(SH.maxCount) in update
    assert '"default"' in update
    assert '"override"' in update


@pytest.mark.asyncio
async def test_load_stored_profile_field_modes_reads_persisted_state(
    monkeypatch,
):
    store = AsyncMock()
    store.query.return_value = [
        {
            "field": str(SH["class"]),
            "mode": "override",
        },
        {
            "field": "urn:domainClasses",
            "mode": "default",
        },
    ]
    monkeypatch.setattr(main, "store", store)

    modes = await main._load_stored_profile_field_modes(
        str(EX.title),
    )

    assert modes == {
        str(SH["class"]): "override",
        "urn:domainClasses": "default",
    }

    query = store.query.await_args.args[0]
    assert main.PROFILE_FIELD_STATE_GRAPH in query


def test_datatype_property_rejects_range_class_constraints():
    with pytest.raises(HTTPException) as exc_info:
        main._validate_profile_range_constraint_compatibility(
            "datatype_property",
            {
                str(SH["class"]): [str(EX.Person)],
            },
            entity_uri=str(EX.title),
        )

    assert exc_info.value.status_code == 400
    assert "cannot have a sh:class constraint" in exc_info.value.detail


def test_object_property_rejects_range_datatype_constraints():
    with pytest.raises(HTTPException) as exc_info:
        main._validate_profile_range_constraint_compatibility(
            "object_property",
            {
                str(SH.datatype): [
                    "http://www.w3.org/2001/XMLSchema#string",
                ],
            },
            entity_uri=str(EX.author),
        )

    assert exc_info.value.status_code == 400
    assert "cannot have a sh:datatype constraint" in exc_info.value.detail


def test_annotation_property_keeps_both_range_selector_modes_available():
    assert (
        str(SH["class"])
        in main.PROFILE_EDITABLE_FIELDS_BY_TYPE["annotation_property"]
    )
    assert (
        str(SH.datatype)
        in main.PROFILE_EDITABLE_FIELDS_BY_TYPE["annotation_property"]
    )


def test_mode_validator_rejects_datatype_selector_for_object_property():
    with pytest.raises(HTTPException) as exc_info:
        main._validate_profile_field_modes(
            {
                str(SH.datatype): "override",
            },
            "object_property",
        )

    assert exc_info.value.status_code == 400


def test_mode_validator_rejects_class_selector_for_datatype_property():
    with pytest.raises(HTTPException) as exc_info:
        main._validate_profile_field_modes(
            {
                str(SH["class"]): "override",
            },
            "datatype_property",
        )

    assert exc_info.value.status_code == 400


def test_mode_validator_rejects_ontology_native_fields():
    with pytest.raises(HTTPException) as exc_info:
        main._validate_profile_field_modes(
            {
                "http://www.w3.org/2000/01/rdf-schema#subClassOf": "override",
            },
            "class",
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_save_rejects_incompatible_range_before_mutating_profile(
    monkeypatch,
):
    store = AsyncMock()

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(
        main.ap,
        "get_entity_type",
        AsyncMock(return_value="datatype_property"),
    )
    monkeypatch.setattr(
        main,
        "validate_constraints",
        lambda *_: True,
    )

    with pytest.raises(HTTPException) as exc_info:
        await main.set_entity_constraints(
            str(EX.title),
            {
                str(SH["class"]): [str(EX.Person)],
            },
        )

    assert exc_info.value.status_code == 400
    store.query.assert_not_awaited()
    store.update.assert_not_awaited()