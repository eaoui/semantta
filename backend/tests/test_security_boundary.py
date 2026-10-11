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


def test_env_list_parses_explicit_values(monkeypatch):
    monkeypatch.setenv(
        "SEMANTTA_ALLOWED_HOSTS",
        "semantta.example.com,localhost",
    )

    assert main._env_list(
        "SEMANTTA_ALLOWED_HOSTS",
        "localhost",
    ) == [
        "semantta.example.com",
        "localhost",
    ]


def test_env_list_rejects_wildcards():
    with pytest.raises(RuntimeError):
        main._env_list(
            "TEST_ALLOWED_HOSTS",
            "*",
        )

TRUSTED_TEST_ORIGINS = frozenset({
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "semantta://bundle",
})


def _origin_test_client():
    return TestClient(
        main.app,
        base_url="http://localhost",
        client=("127.0.0.1", 12345),
    )


@pytest.mark.parametrize(
    "method",
    ["POST", "PUT", "PATCH", "DELETE"],
)

@pytest.mark.parametrize(
    "origin",
    [
        "https://attacker.example",
        "null",
        "https://example.com.attacker.example",
    ],
)

def test_api_rejects_untrusted_origins_for_mutations(
    method,
    origin,
    monkeypatch,
):
    monkeypatch.setattr(
        main,
        "TRUSTED_REQUEST_ORIGINS",
        TRUSTED_TEST_ORIGINS,
    )

    response = _origin_test_client().request(
        method,
        "/api/instances/exists",
        headers={"Origin": origin},
        json={"uris": []},
    )

    assert response.status_code == 403

@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "semantta://bundle",
    ],
)
def test_api_accepts_trusted_origins(
    origin,
    monkeypatch,
):
    monkeypatch.setattr(
        main,
        "TRUSTED_REQUEST_ORIGINS",
        TRUSTED_TEST_ORIGINS,
    )

    response = _origin_test_client().post(
        "/api/instances/exists",
        headers={"Origin": origin},
        json={"uris": []},
    )

    assert response.status_code == 200
    assert response.json() == {"existing": []}

def test_api_accepts_trusted_referer_when_origin_is_absent(
    monkeypatch,
):
    monkeypatch.setattr(
        main,
        "TRUSTED_REQUEST_ORIGINS",
        TRUSTED_TEST_ORIGINS,
    )

    response = _origin_test_client().post(
        "/api/instances/exists",
        headers={
            "Referer": "http://localhost:3000/admin/settings"
        },
        json={"uris": []},
    )

    assert response.status_code == 200


def test_api_rejects_untrusted_referer_when_origin_is_absent(
    monkeypatch,
):
    monkeypatch.setattr(
        main,
        "TRUSTED_REQUEST_ORIGINS",
        TRUSTED_TEST_ORIGINS,
    )

    response = _origin_test_client().post(
        "/api/instances/exists",
        headers={
            "Referer": "https://attacker.example/page"
        },
        json={"uris": []},
    )

    assert response.status_code == 403

def test_api_rejects_mutations_without_origin_or_referer(
    monkeypatch,
):
    monkeypatch.setattr(
        main,
        "TRUSTED_REQUEST_ORIGINS",
        TRUSTED_TEST_ORIGINS,
    )

    response = _origin_test_client().post(
        "/api/instances/exists",
        json={"uris": []},
    )

    assert response.status_code == 403