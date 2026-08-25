"""Worker entrypoint — campaigns and post-call retries."""
from __future__ import annotations

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("worker")


def main() -> None:
    logger.info("Voice Agent worker starting")
    try:
        from worker.dialer import run_loop

        run_loop()
    except KeyboardInterrupt:
        logger.info("worker stopped")
        sys.exit(0)


if __name__ == "__main__":
    main()
