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
import sys

import uvicorn

KEEP_ALIVE_SECONDS = 75


def main() -> None:
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=os.environ.get("HERMES_HOST", "127.0.0.1"),
        port=int(os.environ.get("HERMES_PORT", "8000")),
        reload="--no-reload" not in sys.argv,
        timeout_keep_alive=KEEP_ALIVE_SECONDS,
    )


if __name__ == "__main__":
    main()
