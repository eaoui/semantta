from pathlib import Path
import sys
from unittest.mock import AsyncMock

import pytest
from rdflib import Graph, Namespace
from rdflib.namespace import XSD

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


EX = Namespace("https://example.org/profile-resolution-test/")
SH = Namespace("http://www.w3.org/ns/shacl#")


def test_default_mode_uses_ontology_value_not_stored_shape_value():
    original = {
        str(SH["class"]): [str(EX.Person)],
        "urn:domainClasses": [str(EX.Book)],
    }

    overrides = {
        str(SH["class"]): [str(EX.Agent)],
        "urn:domainClasses": [str(EX.Article)],
        str(SH.minCount): 2,
        str(SH.message): "Preserved profile message",
    }

    modes = {
        str(SH["class"]): "default",
        "urn:domainClasses": "default",
        str(SH.minCount): "override",
    }

    effective = main._resolve_effective_profile_constraints(
        "object_property",
        original,
        overrides,
        modes,
    )

    assert effective[str(SH["class"])] == [str(EX.Person)]
    assert effective["urn:domainClasses"] == [str(EX.Book)]
    assert effective[str(SH.minCount)] == 2

    # Non-editable SHACL constraints remain available.
    assert effective[str(SH.message)] == "Preserved profile message"


def test_override_mode_replaces_ontology_default():
    original = {
        str(SH["class"]): [str(EX.Person)],
    }
    overrides = {
        str(SH["class"]): [str(EX.Agent)],
    }

    effective = main._resolve_effective_profile_constraints(
        "object_property",
        original,
        overrides,
        {
            str(SH["class"]): "override",
        },
    )

    assert effective[str(SH["class"])] == [str(EX.Agent)]


def test_explicit_empty_override_does_not_restore_ontology_value():
    original = {
        str(SH["class"]): [str(EX.Person)],
    }
    overrides = {}

    effective = main._resolve_effective_profile_constraints(
        "object_property",
        original,
        overrides,
        {
            str(SH["class"]): "override",
        },
    )

    assert effective[str(SH["class"])] == []


def test_default_mode_suppresses_stale_profile_only_constraint():
    original = {}
    overrides = {
        str(SH.minCount): 2,
    }

    effective = main._resolve_effective_profile_constraints(
        "object_property",
        original,
        overrides,
        {
            str(SH.minCount): "default",
        },
    )

    assert effective[str(SH.minCount)] is None


def test_multiple_default_range_values_are_preserved():
    original = {
        str(SH["class"]): [
            str(EX.Person),
            str(EX.Agent),
        ],
    }

    effective = main._resolve_effective_profile_constraints(
        "object_property",
        original,
        {},
        {
            str(SH["class"]): "default",
        },
    )

    assert effective[str(SH["class"])] == [
        str(EX.Person),
        str(EX.Agent),
    ]


@pytest.mark.asyncio
async def test_datatype_resolution_respects_explicit_empty_override(
    monkeypatch,
):
    profile = main.SHACLProfile(store=AsyncMock())
    profile._shapes_cache = Graph()

    monkeypatch.setattr(
        main,
        "get_entity_constraints",
        AsyncMock(return_value={
            "type": "datatype_property",
            "original": {
                str(SH.datatype): [str(XSD.integer)],
            },
            "overrides": {},
            "field_modes": {
                str(SH.datatype): "override",
            },
            "effective": {
                str(SH.datatype): [],
                str(SH["class"]): [],
            },
        }),
    )

    # The explicit empty override wins over the ontology default.
    assert await profile.get_property_datatype(
        str(EX.age)
    ) is None


@pytest.mark.asyncio
async def test_datatype_resolution_uses_effective_default(
    monkeypatch,
):
    profile = main.SHACLProfile(store=AsyncMock())
    profile._shapes_cache = Graph()

    monkeypatch.setattr(
        main,
        "get_entity_constraints",
        AsyncMock(return_value={
            "type": "datatype_property",
            "original": {
                str(SH.datatype): [str(XSD.integer)],
            },
            "overrides": {},
            "field_modes": {
                str(SH.datatype): "default",
            },
            "effective": {
                str(SH.datatype): [str(XSD.integer)],
                str(SH["class"]): [],
            },
        }),
    )

    assert await profile.get_property_datatype(
        str(EX.age)
    ) == str(XSD.integer)


@pytest.mark.asyncio
async def test_form_properties_use_effective_range_not_stale_shape_value(
    monkeypatch,
):
    profile = main.ApplicationProfile(store=AsyncMock())

    profile._list_active_properties = AsyncMock(
        return_value=[{
            "uri": str(EX.author),
            "order": None,
        }]
    )

    profile._get_property_constraints = AsyncMock(
        return_value={},
    )

    monkeypatch.setattr(
        main.shacl,
        "get_active_datatypes",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        main,
        "get_entity_constraints",
        AsyncMock(return_value={
            "type": "object_property",
            "original": {
                str(SH["class"]): [str(EX.LegacyAuthor)],
            },
            "overrides": {
                str(SH["class"]): [str(EX.NewAuthor)],
            },
            "field_modes": {
                str(SH["class"]): "override",
            },
            "effective": {
                str(SH["class"]): [str(EX.NewAuthor)],
                str(SH.datatype): [],
                "urn:domainClasses": [],
                str(SH.minCount): None,
                str(SH.maxCount): None,
            },
        }),
    )
    monkeypatch.setattr(
        main,
        "get_instance_suggestions",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        main,
        "get_property_cardinality",
        lambda *_: {
            "minCardinality": None,
            "maxCardinality": None,
        },
    )

    result = await profile.get_properties_for_class(
        str(EX.Book)
    )

    assert len(result) == 1
    assert result[0]["type"] == "object"
    assert result[0]["ranges"] == [str(EX.NewAuthor)]