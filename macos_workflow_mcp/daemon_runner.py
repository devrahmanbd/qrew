"""
Daemon runner entrypoint for macOS Workflow Activity Monitor.
Suitable for running as a launchd agent or background service.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

from .activity_tracker import ActivityMonitorDaemon
from .db import ActivityDB

logger = logging.getLogger("macos_workflow_mcp.daemon")


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def run_daemon(
    poll_interval: float = 3.0,
    db_path: Optional[str] = None,
    min_duration: float = 0.5,
    verbose: bool = False,
) -> None:
    setup_logging(verbose)
    logger.info("Initializing ActivityMonitorDaemon...")
    db = ActivityDB(db_path=db_path) if db_path else None
    daemon = ActivityMonitorDaemon(
        db=db,
        poll_interval=poll_interval,
        min_duration_seconds=min_duration,
    )
    logger.info("Activity database location: %s", daemon.db.db_path)
    logger.info("Polling interval: %.1f seconds", poll_interval)
    logger.info("Minimum duration threshold: %.1f seconds", min_duration)

    daemon.run_forever()


def parse_args(args: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run background activity monitoring daemon for macOS.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=3.0,
        help="Polling interval in seconds between focus checks.",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Custom path to SQLite activity database (defaults to ~/.macos_workflow_mcp/activity.db).",
    )
    parser.add_argument(
        "--min-duration",
        type=float,
        default=0.5,
        help="Minimum focus duration (in seconds) required to log an activity event.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging output.",
    )
    return parser.parse_args(args)


def main() -> None:
    args = parse_args()
    try:
        run_daemon(
            poll_interval=args.poll_interval,
            db_path=args.db_path,
            min_duration=args.min_duration,
            verbose=args.verbose,
        )
    except KeyboardInterrupt:
        logger.info("Daemon interrupted by user. Exiting.")
        sys.exit(0)


if __name__ == "__main__":
    main()
