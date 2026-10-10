"""
Semantta production backend entry point.

Starts the FastAPI application without development reload/watch behavior.
"""

from __future__ import annotations

import os

import uvicorn

from main import app
from config import is_loopback_host


def main() -> None:
    host = os.getenv(
        "SEMANTTA_HOST",
        "127.0.0.1",
    ).strip()

    if not is_loopback_host(host):
        raise SystemExit(
            "Unsafe SEMANTTA_HOST configuration. "
            "Semantta currently supports localhost-only access "
            "because its API has no authentication. "
            "Use 127.0.0.1 or ::1."
        )

    port = int(os.getenv("SEMANTTA_PORT", "8000"))

    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()