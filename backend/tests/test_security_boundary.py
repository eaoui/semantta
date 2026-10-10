import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main
import run as backend_run
from config import is_loopback_host


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "localhost",
        "::1",
        "::ffff:127.0.0.1",
    ],
)
def test_loopback_hosts_are_allowed(host):
    assert is_loopback_host(host)


@pytest.mark.parametrize(
    "host",
    [
        "0.0.0.0",
        "::",
        "192.168.1.10",
        "example.com",
    ],
)
def test_non_loopback_hosts_are_rejected(host):
    assert not is_loopback_host(host)


def test_runner_refuses_non_loopback_binding(monkeypatch):
    monkeypatch.setenv("SEMANTTA_HOST", "0.0.0.0")

    with pytest.raises(SystemExit, match="no authentication"):
        backend_run.main()


def test_api_rejects_non_loopback_clients():
    client = TestClient(
        main.app,
        base_url="http://localhost",
        client=("192.0.2.10", 12345),
    )

    response = client.get("/api/settings")

    assert response.status_code == 403
    assert "localhost only" in response.json()["detail"]


def test_api_allows_loopback_clients():
    client = TestClient(
        main.app,
        base_url="http://localhost",
        client=("127.0.0.1", 12345),
    )

    response = client.get("/api/settings")

    assert response.status_code == 200