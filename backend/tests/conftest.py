
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest
import pytest_asyncio
from rdflib import URIRef
from collections.abc import AsyncGenerator, Generator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
PREPARE_RUNTIME = (
    PROJECT_ROOT / "frontend" / "scripts" / "prepare_runtime.py"
)
RUNTIME_DIR = PROJECT_ROOT / "frontend" / "runtime"
FUSEKI_DIR = RUNTIME_DIR / "fuseki"
JAVA_DIR = RUNTIME_DIR / "java"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fuseki_store import FusekiStore


@pytest.fixture(scope="session")
def fuseki_runtime() -> tuple[Path, Path]:
    """Prepare the project's pinned Fuseki and Java runtime."""
    subprocess.run(
        [sys.executable, str(PREPARE_RUNTIME)],
        cwd=PROJECT_ROOT,
        check=True,
    )

    executable = FUSEKI_DIR / (
        "fuseki-server.bat"
        if os.name == "nt"
        else "fuseki-server"
    )

    java_executable = JAVA_DIR / "bin" / (
        "java.exe" if os.name == "nt" else "java"
    )

    if not executable.is_file() or not java_executable.is_file():
        pytest.fail("Fuseki or Java runtime preparation failed.")

    return executable, FUSEKI_DIR


@pytest.fixture(scope="session")
def fuseki_server(
    tmp_path_factory: pytest.TempPathFactory,
    fuseki_runtime: tuple[Path, Path],
) -> Generator[str, None, None]:
    """Start one isolated Fuseki server for the entire test session."""
    executable, fuseki_dir = fuseki_runtime
    java_home = JAVA_DIR

    server_dir = tmp_path_factory.mktemp("semantta-fuseki")
    database_dir = server_dir / "tdb2"
    fuseki_base = server_dir / "fuseki-base"
    log_path = server_dir / "fuseki.log"

    database_dir.mkdir()
    fuseki_base.mkdir()

    # Allocate a free loopback port.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    dataset_url = f"http://127.0.0.1:{port}/semantta-test"
    ping_url = f"http://127.0.0.1:{port}/$/ping"

    env = os.environ.copy()
    env.update({
        "JAVA_HOME": str(java_home),
        "FUSEKI_HOME": str(fuseki_dir),
        "FUSEKI_BASE": str(fuseki_base),
    })
    env["PATH"] = (
        str(java_home / "bin")
        + os.pathsep
        + env.get("PATH", "")
    )

    process: subprocess.Popen | None = None

    try:
        with log_path.open("w", encoding="utf-8") as log_file:
            process = subprocess.Popen(
                [
                    str(executable),
                    "--tdb2",
                    f"--loc={database_dir}",
                    "--update",
                    "--localhost",
                    f"--port={port}",
                    "/semantta-test",
                ],
                cwd=fuseki_dir,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )

        deadline = time.monotonic() + 45
        ready = False

        while time.monotonic() < deadline:
            if process.poll() is not None:
                break

            try:
                with urlopen(ping_url, timeout=1) as response:
                    if response.status == 200:
                        ready = True
                        break
            except (OSError, URLError, TimeoutError):
                pass

            time.sleep(0.25)

        if not ready:
            details = log_path.read_text(
                encoding="utf-8",
                errors="replace",
            )
            raise RuntimeError(
                "Fuseki did not become ready.\n"
                f"Process exit code: {process.poll()}\n"
                f"Fuseki log:\n{details[-6000:]}"
            )

        # Pytest will use this URL for all tests in the session.
        yield dataset_url

    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


async def clear_test_dataset(store: FusekiStore) -> None:
    """Clear the isolated temporary Fuseki test dataset."""
    await store.update("CLEAR ALL")


@pytest_asyncio.fixture
async def fuseki_store(
    fuseki_server: str,
) -> AsyncGenerator[FusekiStore, None]:
    """Provide a clean dataset and a separate HTTP client for each test."""
    store = FusekiStore(dataset_url=fuseki_server)

    try:
        await store.healthcheck()
        await clear_test_dataset(store)

        yield store

    finally:
        try:
            await clear_test_dataset(store)
        finally:
            await store.close()
