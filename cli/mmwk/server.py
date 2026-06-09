"""Command entrypoint for the local server helper.

This keeps the public command interface aligned with legacy `server.sh` while
exposing a Python-based runtime implementation in `server_runtime`.
"""

from mmwk.server_runtime import main


if __name__ == "__main__":
    raise SystemExit(main())
