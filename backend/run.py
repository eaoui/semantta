"""
Semantta production backend entry point.

Starts the FastAPI application without development reload/watch behavior.
"""

from __future__ import annotations

import os

import uvicorn

from main import app


def main() -> None:
    host = os.getenv("SEMANTTA_HOST", "127.0.0.1")
    port = int(os.getenv("SEMANTTA_PORT", "8000"))

    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()