from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_DIR / "frontend" / "out"


def run(
    command: list[str],
    *,
    env: dict[str, str],
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    print(f"> {' '.join(command)}")

    return subprocess.run(
        command,
        env=env,
        check=check,
        text=True,
    )


def find_single(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.rglob(pattern))

    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one {pattern!r} under {directory}, "
            f"found {len(matches)}."
        )

    return matches[0]


def create_test_environment(root: Path) -> dict[str, str]:
    env = os.environ.copy()

    if sys.platform == "win32":
        env["APPDATA"] = str(root / "AppData")

    elif sys.platform == "darwin":
        env["HOME"] = str(root / "Home")

    else:
        env["XDG_DATA_HOME"] = str(root / "XDG")

    return env


def run_packaged_executable(
    executable: Path,
    env: dict[str, str],
) -> None:
    command = [str(executable)]

    if sys.platform == "linux":
        command.insert(0, str(executable))
        command.insert(0, "xvfb-run")
        command.insert(1, "-a")
        command.extend(["--no-sandbox", "--smoke-test"])
    else:
        command.append("--smoke-test")

    run(command, env=env)


def verify_windows(env: dict[str, str]) -> None:
    installer = find_single(
        OUT_DIR,
        "Semantta-*-win-x64.exe",
    )

    print(f"Windows installer: {installer}")

    with tempfile.TemporaryDirectory(
        prefix="semantta-install-"
    ) as temp:
        install_dir = Path(temp) / "Semantta"

        # NSIS requires /D= to be the final installer argument.
        run(
            [
                str(installer),
                "/S",
                f"/D={install_dir}",
            ],
            env=env,
        )

        executable = install_dir / "Semantta.exe"

        if not executable.is_file():
            raise RuntimeError(
                f"Installed executable not found: {executable}"
            )

        print(f"Installed executable: {executable}")

        run_packaged_executable(
            executable,
            env,
        )

    print("Windows installer test passed.")


def find_deb_executable(package_name: str) -> Path:
    result = subprocess.run(
        [
            "dpkg",
            "-L",
            package_name,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    candidates = [
        Path(line.strip())
        for line in result.stdout.splitlines()
        if line.strip()
        and line.strip().endswith("/semantta")
    ]

    candidates = [
        path
        for path in candidates
        if path.is_file()
    ]

    if len(candidates) != 1:
        raise RuntimeError(
            "Could not uniquely identify the installed "
            f"Semantta executable. Candidates: {candidates}"
        )

    return candidates[0]


def verify_linux(env: dict[str, str]) -> None:
    deb = find_single(
        OUT_DIR,
        "Semantta-*-linux-x64.deb",
    )

    print(f"Debian package: {deb}")

    package_name = subprocess.check_output(
        [
            "dpkg-deb",
            "-f",
            str(deb),
            "Package",
        ],
        text=True,
    ).strip()

    if not package_name:
        raise RuntimeError(
            "Could not determine Debian package name."
        )

    print(f"Debian package name: {package_name}")

    run(
        [
            "sudo",
            "apt-get",
            "install",
            "-y",
            str(deb),
        ],
        env=env,
    )

    executable = find_deb_executable(
        package_name
    )

    print(f"Installed executable: {executable}")

    run_packaged_executable(
        executable,
        env,
    )

    print("Debian package test passed.")


def find_mac_app(root: Path) -> Path:
    matches = sorted(
        root.rglob("Semantta.app")
    )

    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one Semantta.app under {root}, "
            f"found {len(matches)}."
        )

    return matches[0]


def run_mac_app(
    app: Path,
    env: dict[str, str],
) -> None:
    # Signing/notarization is intentionally deferred.
    subprocess.run(
        [
            "xattr",
            "-dr",
            "com.apple.quarantine",
            str(app),
        ],
        check=False,
        text=True,
    )

    executable = (
        app
        / "Contents"
        / "MacOS"
        / "Semantta"
    )

    if not executable.is_file():
        raise RuntimeError(
            f"macOS executable not found: {executable}"
        )

    run_packaged_executable(
        executable,
        env,
    )


def verify_macos(env: dict[str, str]) -> None:
    dmg = find_single(
        OUT_DIR,
        "Semantta-*-mac-*.dmg",
    )

    zip_file = find_single(
        OUT_DIR,
        "Semantta-*-mac-*.zip",
    )

    print(f"DMG: {dmg}")
    print(f"ZIP: {zip_file}")

    with tempfile.TemporaryDirectory(
        prefix="semantta-macos-install-"
    ) as temp:
        root = Path(temp)

        dmg_mount = root / "dmg-mount"
        dmg_install = root / "dmg-install"
        zip_extract = root / "zip-extract"

        dmg_mount.mkdir()
        dmg_install.mkdir()
        zip_extract.mkdir()

        try:
            run(
                [
                    "hdiutil",
                    "attach",
                    str(dmg),
                    "-nobrowse",
                    "-readonly",
                    "-mountpoint",
                    str(dmg_mount),
                ],
                env=env,
            )

            dmg_app = find_mac_app(
                dmg_mount
            )

            installed_dmg_app = (
                dmg_install / "Semantta.app"
            )

            run(
                [
                    "ditto",
                    str(dmg_app),
                    str(installed_dmg_app),
                ],
                env=env,
            )

            print(
                "Testing application copied from DMG..."
            )

            run_mac_app(
                installed_dmg_app,
                env,
            )

        finally:
            run(
                [
                    "hdiutil",
                    "detach",
                    str(dmg_mount),
                ],
                env=env,
                check=False,
            )

        run(
            [
                "ditto",
                "-x",
                "-k",
                str(zip_file),
                str(zip_extract),
            ],
            env=env,
        )

        zip_app = find_mac_app(
            zip_extract
        )

        print(
            "Testing application extracted from ZIP..."
        )

        run_mac_app(
            zip_app,
            env,
        )

    print("macOS DMG/ZIP tests passed.")


def main() -> None:
    if not OUT_DIR.is_dir():
        raise RuntimeError(
            f"Build output directory does not exist: {OUT_DIR}"
        )

    with tempfile.TemporaryDirectory(
        prefix="semantta-installer-test-"
    ) as temp:
        test_root = Path(temp)

        env = create_test_environment(
            test_root
        )

        if sys.platform == "win32":
            verify_windows(env)

        elif sys.platform == "darwin":
            verify_macos(env)

        elif sys.platform.startswith("linux"):
            verify_linux(env)

        else:
            raise RuntimeError(
                f"Unsupported platform: {platform.system()}"
            )

    print("Installer verification passed.")


if __name__ == "__main__":
    main()