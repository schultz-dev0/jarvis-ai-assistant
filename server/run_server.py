"""Entry point to run the VPS Brain bridge server."""

from __future__ import annotations

import os

import uvicorn


def main():
    host = os.environ.get("JARVIS_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("JARVIS_SERVER_PORT", "8765"))
    uvicorn.run("server.bridge:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
