import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main


@pytest.mark.parametrize(
    "name",
    [
        "../secret",
        "..",
        "/etc/passwd",
        r"..\secret",
        "subdir/file.ttl",
    ],
)
def test_path_component_rejects_traversal(name):
    with pytest.raises(HTTPException) as error:
        main._require_safe_path_component(name, "filename")

    assert error.value.status_code == 400


def test_path_within_directory_accepts_child_file(tmp_path):
    child = tmp_path / "ontology.ttl"
    child.write_text("test", encoding="utf-8")

    resolved = main._path_within_directory(
        tmp_path,
        "ontology.ttl",
    )

    assert resolved == child.resolve()
    assert resolved.is_file()


def test_path_within_directory_rejects_traversal(tmp_path):
    outside = tmp_path.parent / "outside.ttl"
    outside.write_text("private", encoding="utf-8")

    with pytest.raises(HTTPException) as error:
        main._path_within_directory(
            tmp_path,
            "../outside.ttl",
        )

    assert error.value.status_code == 400


def test_path_within_directory_rejects_symlink_escape(tmp_path):
    managed_dir = tmp_path / "managed"
    managed_dir.mkdir()

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "private.ttl").write_text(
        "private",
        encoding="utf-8",
    )

    link = managed_dir / "escape"
    try:
        link.symlink_to(outside_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are unavailable")

    with pytest.raises(HTTPException) as error:
        main._path_within_directory(
            managed_dir,
            "escape",
        )

    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_raw_ontology_download_rejects_unregistered_file(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "unregistered.ttl").write_text(
        "private",
        encoding="utf-8",
    )

    monkeypatch.setattr(main, "ONTOLOGY_DIR", tmp_path)

    original_ontologies = main.state["ontologies"]
    main.state["ontologies"] = []

    try:
        with pytest.raises(HTTPException) as error:
            await main.get_raw_ontology("unregistered.ttl")

        assert error.value.status_code == 404
    finally:
        main.state["ontologies"] = original_ontologies


@pytest.mark.asyncio
async def test_set_active_theme_rejects_traversal():
    with pytest.raises(HTTPException) as error:
        await main.set_active_theme_endpoint({
            "theme": "../outside",
        })

    assert error.value.status_code == 400