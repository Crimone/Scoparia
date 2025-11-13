"""Main entry point for Scoparia."""

import argparse
import sys

from . import api, config, core, logger, mongodb


def setup_argument_parser() -> argparse.ArgumentParser:
    """Set up command line argument parser.

    Returns:
        argparse.ArgumentParser: Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description="Scoparia - SCP forum activity notifier",
        prog="scoparia",
    )

    parser.add_argument(
        "--loglevel",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="Log level (default: info)",
    )

    return parser


async def _async_main() -> None:
    """Main async entry point."""
    parser = setup_argument_parser()
    args = parser.parse_args()

    # Set log level
    logger.set_level(args.loglevel)

    logger.info("Initializing Scoparia...")

    try:
        # Initialize config and core
        config.init_config()
        core.init_core()

        # Get config to check database mode
        cfg = config.get_config()

        # Initialize MongoDB (skipped in no-database mode)
        await mongodb.init_mongodb()

        # Initialize Wikidot client
        await api.init_client(
            username=cfg.wikidot_username,
            password=cfg.wikidot_password,
        )

        core_instance = core.get_core()
        await core_instance.initialize()

        # Sync operations only in MongoDB mode
        if cfg.mongodb_uri is not None:
            # Sync contacts from Wikidot
            await core_instance.sync_contacts()

            # Sync user configs from config wiki
            await core_instance.sync_user_configs()
        else:
            logger.info(
                "Running in no-database mode, skipping contacts and "
                "user config synchronization"
            )

        # Process RSS feed
        logger.info("Processing RSS feed...")
        await core_instance.process_rss_feed()

        # Cleanup
        await core_instance.cleanup()
        await api.cleanup_client()
        await mongodb.cleanup_mongodb()

        logger.info("Run completed successfully")
        sys.exit(0)

    except Exception as e:
        logger.error("Run failed: %s", e, exc_info=True)
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    try:
        if sys.platform == "win32":
            import winloop  # type: ignore[import]

            winloop.run(_async_main())
        else:
            import uvloop  # type: ignore[import]

            uvloop.run(_async_main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=True)
        sys.exit(1)
