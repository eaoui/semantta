from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "frontend" / "out"

expected = json.loads(
    os.environ["EXPECTED_ARTIFACTS"]
)

platform_target = os.environ["PLATFORM_TARGET"]


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


if not OUTPUT_DIR.is_dir():
    fail(f"Build output directory does not exist: {OUTPUT_DIR}")


files = [
    path
    for path in OUTPUT_DIR.iterdir()
    if path.is_file()
]


if not files:
    fail("No files were generated in frontend/out.")


def find_extension(extension: str) -> list[Path]:
    extension = extension.lower().lstrip(".")
    return [
        path
        for path in files
        if path.suffix.lower() == f".{extension}"
    ]


for artifact_type in expected:
    matches = find_extension(artifact_type)

    if not matches:
        fail(
            f"Expected {artifact_type} artifact was not generated."
        )

    print(
        f"Found {artifact_type}: "
        f"{', '.join(path.name for path in matches)}"
    )


if platform_target not in {
    "linux",
    "win",
    "mac",
}:
    fail(
        f"Unknown platform target: {platform_target}"
    )


print(
    f"Build validation succeeded for {platform_target}."
)