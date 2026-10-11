from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn


FUSEKI_VERSION = "6.2.0"
JAVA_FEATURE_VERSION = "21"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

BACKEND_DIST = BACKEND_DIR / "dist"
RUNTIME_DIR = FRONTEND_DIR / "runtime"

FUSEKI_DIR = RUNTIME_DIR / "fuseki"
JAVA_DIR = RUNTIME_DIR / "java"
MANIFEST_FILE = RUNTIME_DIR / "manifest.json"


def fail(message: str) -> NoReturn:
    print(
        f"ERROR: {message}",
        file=sys.stderr,
    )
    raise SystemExit(1)


def current_platform_name() -> str:
    platforms = {
        "Linux": "linux",
        "Windows": "windows",
        "Darwin": "mac",
    }

    try:
        return platforms[platform.system()]
    except KeyError:
        fail(
            f"Unsupported operating system: "
            f"{platform.system()}"
        )


def current_architecture_name() -> str:
    architectures = {
        "x86_64": "x64",
        "amd64": "x64",
        "aarch64": "aarch64",
        "arm64": "aarch64",
    }

    machine = platform.machine().lower()

    try:
        return architectures[machine]
    except KeyError:
        fail(
            f"Unsupported CPU architecture: "
            f"{platform.machine()}"
        )


def verify_manifest(
    os_name: str,
    architecture: str,
) -> None:
    if not MANIFEST_FILE.is_file():
        fail(
            f"Missing runtime manifest: "
            f"{MANIFEST_FILE}"
        )

    try:
        manifest = json.loads(
            MANIFEST_FILE.read_text(
                encoding="utf-8",
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        fail(
            f"Could not read runtime manifest: {exc}"
        )

    if not isinstance(manifest, dict):
        fail(
            "Runtime manifest must contain a JSON object."
        )

    fuseki = manifest.get("fuseki")
    java = manifest.get("java")

    if (
        not isinstance(fuseki, dict)
        or not isinstance(java, dict)
    ):
        fail(
            "Runtime manifest is missing Fuseki "
            "or Java metadata."
        )

    if manifest.get("platform") != os_name:
        fail(
            "Runtime platform does not match the "
            f"current operating system: {os_name}"
        )

    if manifest.get("architecture") != architecture:
        fail(
            "Runtime architecture does not match "
            f"the current architecture: {architecture}"
        )

    if fuseki.get("version") != FUSEKI_VERSION:
        fail(
            f"Expected Fuseki {FUSEKI_VERSION}; "
            f"found {fuseki.get('version')}."
        )

    if java.get("major_version") != JAVA_FEATURE_VERSION:
        fail(
            f"Expected Java {JAVA_FEATURE_VERSION}; "
            f"found {java.get('major_version')}."
        )

    fuseki_checksum = fuseki.get("sha512")
    java_checksum = java.get("sha256")

    if (
        not isinstance(fuseki_checksum, str)
        or not re.fullmatch(
            r"[0-9a-f]{128}",
            fuseki_checksum,
        )
    ):
        fail(
            "Runtime manifest contains an invalid "
            "Fuseki SHA-512 checksum."
        )

    if (
        not isinstance(java_checksum, str)
        or not re.fullmatch(
            r"[0-9a-f]{64}",
            java_checksum,
        )
    ):
        fail(
            "Runtime manifest contains an invalid "
            "Java SHA-256 checksum."
        )


def verify_executable(
    executable: Path,
    description: str,
) -> None:
    if not executable.is_file():
        fail(
            f"Missing {description}: {executable}"
        )

    if (
        os.name != "nt"
        and not os.access(
            executable,
            os.X_OK,
        )
    ):
        fail(
            f"{description} is not executable: "
            f"{executable}"
        )


def verify_java(
    java_executable: Path,
) -> None:
    try:
        result = subprocess.run(
            [
                str(java_executable),
                "--version",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        fail(
            f"Bundled Java could not run: {exc}"
        )

    version_output = (
        f"{result.stdout}\n{result.stderr}"
    )

    if re.search(
        rf"\b(?:openjdk|java)\s+"
        rf"(?:version\s+)?[\"']?"
        rf"{JAVA_FEATURE_VERSION}(?:[.\s+-]|$)",
        version_output,
        re.IGNORECASE,
    ) is None:
        fail(
            "Bundled Java does not report the "
            f"expected Java {JAVA_FEATURE_VERSION} version."
        )

    print(
        "Java runtime:",
        version_output.strip().splitlines()[0],
    )


def main() -> None:
    if platform.system() == "Windows":
        backend_name = "SemanttaBackend.exe"
        fuseki_name = "fuseki-server.bat"
        java_name = "java.exe"
    else:
        backend_name = "SemanttaBackend"
        fuseki_name = "fuseki-server"
        java_name = "java"

    backend_executable = (
        BACKEND_DIST / backend_name
    )

    fuseki_executable = (
        FUSEKI_DIR / fuseki_name
    )

    java_executable = (
        JAVA_DIR / "bin" / java_name
    )

    os_name = current_platform_name()
    architecture = current_architecture_name()

    verify_manifest(
        os_name,
        architecture,
    )

    verify_executable(
        backend_executable,
        "backend executable",
    )

    verify_executable(
        fuseki_executable,
        "Fuseki launcher",
    )

    verify_executable(
        java_executable,
        "Java executable",
    )

    verify_java(java_executable)

    print(
        "Backend executable:",
        backend_executable,
    )
    print(
        "Fuseki runtime:",
        FUSEKI_DIR,
    )
    print(
        "Java runtime:",
        JAVA_DIR,
    )
    print(
        "Runtime validation succeeded."
    )


if __name__ == "__main__":
    main()