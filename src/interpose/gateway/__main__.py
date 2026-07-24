"""Run the gateway locally: `uv run python -m interpose.gateway`."""

import logging

import uvicorn

from interpose.config import get_settings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    uvicorn.run(
        "interpose.gateway.app:create_app",
        factory=True,
        host=settings.gateway_host,
        port=settings.gateway_port,
    )


if __name__ == "__main__":
    main()
