import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


@pytest.mark.asyncio
async def test_active_class_options_include_transitive_superclasses(
    monkeypatch,
):
    range_class = "http://example.org/Resource"
    middle_class = "http://example.org/ElectronicResource"
    child_class = "http://example.org/DigitalBook"
    unrelated_class = "http://example.org/Person"

    monkeypatch.setattr(
        main.ap,
        "get_active_classes",
        AsyncMock(return_value=[child_class, unrelated_class]),
    )
    monkeypatch.setattr(
        main,
        "_subclass_pairs",
        {
            (child_class, middle_class),
            (middle_class, range_class),
        },
    )
    monkeypatch.setattr(
        main,
        "get_label",
        lambda uri: uri.rsplit("/", 1)[-1],
    )

    result = await main.get_active_classes()
    options = {item["uri"]: item for item in result}

    assert set(options[child_class]["superClasses"]) == {
        middle_class,
        range_class,
    }
    assert options[unrelated_class]["superClasses"] == []

    # Range classes need not themselves be active to match an active
    # descendant. Only active classes are returned as selectable options.
    assert range_class not in options
    assert middle_class not in options