from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path


FUSEKI_VERSION = "6.2.0"
JAVA_FEATURE_VERSION = "21"

PROJECT_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_DIR / "runtime"

FUSEKI_DIR = RUNTIME_DIR / "fuseki"
JAVA_DIR = RUNTIME_DIR / "java"
MANIFEST_FILE = RUNTIME_DIR / "manifest.json"


def platform_name() -> str:
    system = platform.system()

    if system == "Linux":
        return "linux"

    if system == "Windows":
        return "windows"

    if system == "Darwin":
        return "mac"

    raise RuntimeError(
        f"Unsupported operating system: {system}"
    )


def architecture_name() -> str:
    machine = platform.machine().lower()

    mapping = {
        "x86_64": "x64",
        "amd64": "x64",
        "aarch64": "aarch64",
        "arm64": "aarch64",
    }

    try:
        return mapping[machine]
    except KeyError:
        raise RuntimeError(
            f"Unsupported CPU architecture: {machine}"
        )


def download(
    url: str,
    destination: Path,
) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(f"Downloading: {url}")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Semantta build system",
        },
    )

    with urllib.request.urlopen(request) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for block in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def sha512(path: Path) -> str:
    digest = hashlib.sha512()

    with path.open("rb") as file:
        for block in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def download_fuseki(
    target: Path,
    os_name: str,
) -> dict:
    extension = "zip" if os_name == "windows" else "tar.gz"

    filename = (
        f"apache-jena-fuseki-"
        f"{FUSEKI_VERSION}.{extension}"
    )

    base_url = (
        "https://dlcdn.apache.org/"
        "jena/binaries/"
    )

    archive_url = (
        f"{base_url}{filename}"
    )

    checksum_url = f"{archive_url}.sha512"

    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)

        archive = temp_dir / filename
        checksum_file = (
            temp_dir / f"{filename}.sha512"
        )

        download(
            archive_url,
            archive,
        )

        download(
            checksum_url,
            checksum_file,
        )

        expected = (
            checksum_file.read_text(
                encoding="utf-8"
            )
            .split()[0]
            .lower()
        )

        actual = sha512(archive)

        if actual != expected:
            raise RuntimeError(
                "Fuseki SHA-512 verification failed."
            )

        extracted = temp_dir / "extracted"
        extracted.mkdir()

        if extension == "zip":
            with zipfile.ZipFile(archive) as archive_file:
                archive_file.extractall(extracted)
        else:
            with tarfile.open(
                archive,
                "r:gz",
            ) as archive_file:
                archive_file.extractall(
                    extracted,
                    filter="data",
                )

        candidates = list(
            extracted.glob(
                "apache-jena-fuseki-*"
            )
        )

        if len(candidates) != 1:
            raise RuntimeError(
                "Could not identify the extracted "
                "Fuseki distribution."
            )

        source = candidates[0]

        if target.exists():
            shutil.rmtree(target)

        shutil.copytree(
            source,
            target,
        )

    return {
        "version": FUSEKI_VERSION,
        "archive": filename,
        "url": archive_url,
        "sha512": expected,
    }


def download_java(
    target: Path,
    os_name: str,
    architecture: str,
) -> dict:
    api_url = (
        "https://api.adoptium.net/v3/assets/"
        f"latest/{JAVA_FEATURE_VERSION}/hotspot"
        f"?architecture={architecture}"
        f"&image_type=jre"
        f"&os={os_name}"
        "&vendor=eclipse"
        "&project=jdk"
    )

    print(f"Resolving Temurin JRE: {api_url}")

    request = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": "Semantta build system",
        },
    )

    with urllib.request.urlopen(request) as response:
        assets = json.load(response)

    if not assets:
        raise RuntimeError(
            "No compatible Temurin JRE was found."
        )

    package = assets[0]["binary"]["package"]

    download_url = package["link"]
    expected = package["checksum"].lower()
    filename = package["name"]

    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        archive = temp_dir / filename

        download(
            download_url,
            archive,
        )

        actual = sha256(archive)

        if actual != expected:
            raise RuntimeError(
                "Temurin JRE SHA-256 verification failed."
            )

        extracted = temp_dir / "extracted"
        extracted.mkdir()

        if filename.lower().endswith(".zip"):
            with zipfile.ZipFile(archive) as archive_file:
                archive_file.extractall(extracted)
        else:
            with tarfile.open(
                archive,
                "r:gz",
            ) as archive_file:
                archive_file.extractall(
                    extracted,
                    filter="data",
                )

        java_candidates = list(
            extracted.rglob("bin/java")
        ) + list(
            extracted.rglob("bin/java.exe")
        )

        if len(java_candidates) != 1:
            raise RuntimeError(
                "Could not identify the extracted "
                "Temurin Java runtime."
            )

        java_root = java_candidates[0].parent.parent

        if target.exists():
            shutil.rmtree(target)

        shutil.copytree(
            java_root,
            target,
        )

    return {
        "major_version": JAVA_FEATURE_VERSION,
        "filename": filename,
        "url": download_url,
        "sha256": expected,
    }


def runtime_is_current(
    os_name: str,
    architecture: str,
) -> bool:
    if not MANIFEST_FILE.exists():
        return False

    try:
        manifest = json.loads(
            MANIFEST_FILE.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return False

    return (
        manifest.get("fuseki", {}).get("version")
        == FUSEKI_VERSION
        and manifest.get("java", {}).get("major_version")
        == JAVA_FEATURE_VERSION
        and manifest.get("platform") == os_name
        and manifest.get("architecture") == architecture
        and FUSEKI_DIR.is_dir()
        and JAVA_DIR.is_dir()
    )


def main() -> None:
    os_name = platform_name()
    architecture = architecture_name()

    RUNTIME_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if runtime_is_current(
        os_name,
        architecture,
    ):
        print("Bundled runtime is already prepared.")
        return

    if FUSEKI_DIR.exists():
        shutil.rmtree(FUSEKI_DIR)

    if JAVA_DIR.exists():
        shutil.rmtree(JAVA_DIR)

    fuseki = download_fuseki(
        FUSEKI_DIR,
        os_name,
    )

    java = download_java(
        JAVA_DIR,
        os_name,
        architecture,
    )

    manifest = {
        "platform": os_name,
        "architecture": architecture,
        "fuseki": fuseki,
        "java": java,
    }

    MANIFEST_FILE.write_text(
        json.dumps(
            manifest,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("Bundled runtime prepared successfully.")


if __name__ == "__main__":
    main()