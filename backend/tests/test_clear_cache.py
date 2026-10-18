import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main


@pytest.mark.asyncio
async def test_clear_all_caches_removes_cache_files_and_invalidates(
    tmp_path,
    monkeypatch,
):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    (cache_dir / "reasoned.ttl").write_text(
        "cached graph",
        encoding="utf-8",
    )

    nested = cache_dir / "temporary"
    nested.mkdir()
    (nested / "data.json").write_text(
        "{}",
        encoding="utf-8",
    )

    monkeypatch.setattr(main, "CACHE_DIR", cache_dir)

    clear_stats = Mock()
    clear_count = Mock()
    invalidate = Mock()

    monkeypatch.setattr(
        main,
        "clear_metadata_graph_stats",
        clear_stats,
    )
    monkeypatch.setattr(
        main,
        "invalidate_instance_count",
        clear_count,
    )
    monkeypatch.setattr(
        main,
        "invalidate_everything",
        invalidate,
    )

    result = await main.clear_all_caches()

    assert result["status"] == "ok"
    assert cache_dir.is_dir()
    assert list(cache_dir.iterdir()) == []
    clear_stats.assert_called_once()
    clear_count.assert_called_once()
    invalidate.assert_called_once()