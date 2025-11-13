"""Scoparia configuration processing module."""

import os
import re
from enum import Enum

import msgspec


class LogLevel(Enum):
    """Log level enumeration."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


def validate_and_normalize_wikidot_url(url: str) -> str:
    """Validate and normalize a Wikidot site URL.

    Validates that the URL is in the format http[s]://xxx.wikidot.com,
    and strips trailing slash.

    Args:
        url: The URL to validate and normalize.

    Returns:
        Normalized URL without trailing slash.

    Raises:
        ValueError: If URL format is invalid.
    """
    # Strip trailing slash
    normalized_url = url.rstrip("/")

    # Validate format: http[s]://xxx.wikidot.com
    pattern = r"^https?://[\w\-]+\.wikidot\.com$"
    if not re.match(pattern, normalized_url):
        raise ValueError(
            f"Invalid Wikidot URL format: {url}. "
            f"Expected format: http[s]://xxx.wikidot.com"
        )

    return normalized_url


class MentionLevel(str, Enum):
    """Enumeration of mention notification levels.

    Attributes
    ----------
    DISABLED : str
        Do not receive mention notifications
    AVATARHOVER : str
        Only receive notifications for [[*user]] syntax mentions
        (span.printuser.avatarhover elements only)
    ALL : str
        Receive notifications for both [[*user]] and [[user]] syntax
        (all span.printuser elements)
    """

    DISABLED = "disabled"
    AVATARHOVER = "avatarhover"
    ALL = "all"


class UserInfo(msgspec.Struct):
    """User information from MongoDB.

    Attributes
    ----------
    userid : int
        Wikidot user ID
    username : str
        Username of the user
    apprise_urls : list[str]
        List of Apprise notification URLs
    timezone : str
        User's timezone (IANA format). Defaults to "UTC"
    mention_level : MentionLevel
        Level of mention notifications to receive. Defaults to ALL
    email : str | None
        User's email address. Defaults to None
    enable_wikidot_pm : bool
        Whether to enable Wikidot private message notifications. Defaults to True
    enable_email : bool
        Whether to enable email notifications. Defaults to True
    enable_apprise : bool
        Whether to enable Apprise notifications. Defaults to True
    """

    userid: int
    username: str
    apprise_urls: list[str]
    timezone: str = "UTC"
    mention_level: MentionLevel = MentionLevel.AVATARHOVER
    email: str | None = None
    enable_wikidot_pm: bool = True
    enable_email: bool = True
    enable_apprise: bool = True


class ScopariaConfig(msgspec.Struct):
    """Scoparia main configuration class - GitHub Actions optimized.

    Database mode is automatically determined:
    - If mongodb_uri is set: MongoDB mode (full-featured)
    - If mongodb_uri is None: No-database mode (uses environment variables)
    """

    # Wikidot credentials (from environment variables)
    wikidot_username: str
    wikidot_password: str

    # MongoDB connection (optional - if not set, runs in no-database mode)
    mongodb_uri: str | None

    # RSS site URLs to monitor (from environment variable as JSON)
    rss_site_urls: list[str]

    # Users configuration (required in no-database mode, optional in MongoDB mode)
    users: dict[int, UserInfo]


def load_config_from_env() -> ScopariaConfig:
    """Load configuration from environment variables.

    Returns:
        ScopariaConfig instance.

    Raises:
        ValueError: If required environment variables are missing.
    """
    # Required environment variables
    wikidot_username = os.getenv("WIKIDOT_USERNAME")
    wikidot_password = os.getenv("WIKIDOT_PASSWORD")
    rss_site_urls_str = os.getenv("RSS_SITE_URLS")

    if not wikidot_username:
        raise ValueError("WIKIDOT_USERNAME environment variable is required")
    if not wikidot_password:
        raise ValueError("WIKIDOT_PASSWORD environment variable is required")
    if not rss_site_urls_str:
        raise ValueError("RSS_SITE_URLS environment variable is required")

    # MongoDB URI (optional - if not set, runs in no-database mode)
    mongodb_uri = os.getenv("MONGODB_URI") or None

    # Parse RSS site URLs from JSON using msgspec
    try:
        rss_site_urls = msgspec.json.decode(rss_site_urls_str, type=list[str])
    except msgspec.DecodeError:
        raise ValueError(
            "RSS_SITE_URLS must be a valid JSON array of strings"
        ) from None

    # Validate and normalize each URL
    try:
        rss_site_urls = [
            validate_and_normalize_wikidot_url(url) for url in rss_site_urls
        ]
    except ValueError:
        raise ValueError("Invalid RSS site URL format") from None

    # Users JSON (required in no-database mode, optional in mongodb mode)
    users_json_str = os.getenv("USERS_JSON")
    users: dict[int, UserInfo] = {}

    # In no-database mode (mongodb_uri is None), USERS_JSON is required
    if mongodb_uri is None and not users_json_str:
        raise ValueError(
            "USERS_JSON environment variable is required when MONGODB_URI is not set "
            "(no-database mode)"
        )

    if users_json_str:
        try:
            users = msgspec.json.decode(users_json_str, type=dict[int, UserInfo])
        except (msgspec.DecodeError, ValueError, TypeError):
            raise ValueError(
                "USERS_JSON must be a valid JSON object mapping userid to UserInfo"
            ) from None

    return ScopariaConfig(
        wikidot_username=wikidot_username,
        wikidot_password=wikidot_password,
        mongodb_uri=mongodb_uri,
        rss_site_urls=rss_site_urls,
        users=users,
    )


# Global configuration object
cfg: ScopariaConfig | None = None


def init_config() -> None:
    """Initialize global configuration object from environment variables.

    Raises:
        ValueError: Raised when configuration loading fails.
    """
    global cfg
    cfg = load_config_from_env()


def get_config() -> ScopariaConfig:
    """Get global configuration object.

    Returns:
        ScopariaConfig instance.

    Raises:
        RuntimeError: If config has not been initialized.
    """
    if cfg is None:
        raise RuntimeError("Config not initialized. Call init_config() first.")
    return cfg
