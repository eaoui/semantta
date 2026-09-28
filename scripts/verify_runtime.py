from __future__ import annotations

import platform
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

BACKEND_DIST = BACKEND_DIR / "dist"

if platform.system() == "Windows":
    backend_name = "SemanttaBackend.exe"
else:
    backend_name = "SemanttaBackend"

backend_executable = BACKEND_DIST / backend_name

if not backend_executable.is_file():
    raise SystemExit(
        f"Missing backend executable: {backend_executable}"
    )

runtime_dir = FRONTEND_DIR / "runtime"

fuseki_dir = runtime_dir / "fuseki"
java_dir = runtime_dir / "java"

if not fuseki_dir.is_dir():
    raise SystemExit(
        f"Missing Fuseki runtime: {fuseki_dir}"
    )

if not java_dir.is_dir():
    raise SystemExit(
        f"Missing Java runtime: {java_dir}"
    )

print("Backend executable:", backend_executable)
print("Fuseki runtime:", fuseki_dir)
print("Java runtime:", java_dir)
print("Runtime validation succeeded.")