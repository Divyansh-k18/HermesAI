"""Start the Hermes API: `python run.py` (add `--no-reload` to turn off auto-reload).

Same as `uvicorn app.main:create_app --factory --reload`, with one important difference: idle
connections are kept open for 75 seconds instead of uvicorn's 5. The Next.js proxy keeps idle
connections for about 5 seconds too, and when both sides time out together a request can be sent on
a closing connection and fail with ECONNRESET. Keeping the server side open longer means the proxy
always closes first.

Environment: HERMES_PORT (default 8000), HERMES_HOST (default 127.0.0.1), plus the HERMES_* settings
read by app/config.py.
"""

import os
import socket
import sys

import uvicorn

KEEP_ALIVE_SECONDS = 75


def port_in_use(host: str, port: int) -> bool:
    """True if some program already accepts connections on host:port."""
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def main() -> None:
    host = os.environ.get("HERMES_HOST", "127.0.0.1")
    port = int(os.environ.get("HERMES_PORT", "8000"))

    # Without this check another program on the port keeps answering, and the website shows
    # "Hermes can't reach its server (HTTP 404)" with no clue why.
    if port_in_use(host, port):
        other = port + 10
        print(
            f"\nPort {port} is already used by another program, so the Hermes API cannot start.\n\n"
            f"Either stop that program, or run Hermes on another port:\n"
            f"  Windows (cmd):  set HERMES_PORT={other}  then  .venv\\Scripts\\python run.py\n"
            f"  macOS/Linux:    HERMES_PORT={other} .venv/bin/python run.py\n\n"
            f"Then start the website pointing at it, in the web folder:\n"
            f"  Windows (cmd):  set HERMES_API_URL=http://127.0.0.1:{other}  then  npm run dev\n"
            f"  macOS/Linux:    HERMES_API_URL=http://127.0.0.1:{other} npm run dev\n",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Hermes API starting on http://{host}:{port}  (check: http://{host}:{port}/healthz)")
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=host,
        port=port,
        reload="--no-reload" not in sys.argv,
        timeout_keep_alive=KEEP_ALIVE_SECONDS,
    )


if __name__ == "__main__":
    main()
