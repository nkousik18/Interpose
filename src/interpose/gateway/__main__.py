"""Run the gateway locally: `uv run python -m interpose.gateway`."""

import logging

import uvicorn


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    uvicorn.run("interpose.gateway.app:create_app", factory=True, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
