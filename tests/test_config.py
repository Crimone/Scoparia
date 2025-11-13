"""Tests for Scoparia configuration module."""

import os
from unittest.mock import patch

import pytest

from scoparia.config import (
    MentionLevel,
    ScopariaConfig,
    UserInfo,
    load_config_from_env,
    validate_and_normalize_wikidot_url,
)


class TestValidateAndNormalizeWikidotUrl:
    """Test URL validation and normalization."""

    def test_valid_https_url(self) -> None:
        """Test validation of valid HTTPS URL."""
        url = "https://scp-wiki.wikidot.com/"
        result = validate_and_normalize_wikidot_url(url)
        assert result == "https://scp-wiki.wikidot.com"

    def test_valid_http_url(self) -> None:
        """Test validation of valid HTTP URL."""
        url = "http://test-site.wikidot.com"
        result = validate_and_normalize_wikidot_url(url)
        assert result == "http://test-site.wikidot.com"

    def test_url_with_trailing_slash(self) -> None:
        """Test that trailing slash is removed."""
        url = "https://scp-wiki.wikidot.com/"
        result = validate_and_normalize_wikidot_url(url)
        assert result == "https://scp-wiki.wikidot.com"

    def test_invalid_url_format(self) -> None:
        """Test that invalid URL format raises ValueError."""
        url = "not-a-url"
        with pytest.raises(ValueError, match="Invalid Wikidot URL format"):
            validate_and_normalize_wikidot_url(url)

    def test_invalid_domain(self) -> None:
        """Test that non-Wikidot domain raises ValueError."""
        url = "https://example.com"
        with pytest.raises(ValueError, match="Invalid Wikidot URL format"):
            validate_and_normalize_wikidot_url(url)


class TestMentionLevel:
    """Test MentionLevel enum."""

    def test_mention_level_values(self) -> None:
        """Test that MentionLevel has correct values."""
        assert MentionLevel.DISABLED == "disabled"
        assert MentionLevel.AVATARHOVER == "avatarhover"
        assert MentionLevel.ALL == "all"


class TestUserInfo:
    """Test UserInfo struct."""

    def test_user_info_creation(self) -> None:
        """Test creating UserInfo with all fields."""
        user = UserInfo(
            userid=123,
            username="TestUser",
            apprise_urls=["json://localhost"],
            timezone="UTC",
            mention_level=MentionLevel.AVATARHOVER,
            email="test@example.com",
            enable_wikidot_pm=True,
            enable_email=True,
            enable_apprise=True,
        )
        assert user.userid == 123
        assert user.username == "TestUser"
        assert user.apprise_urls == ["json://localhost"]
        assert user.timezone == "UTC"
        assert user.mention_level == MentionLevel.AVATARHOVER
        assert user.email == "test@example.com"
        assert user.enable_wikidot_pm is True
        assert user.enable_email is True
        assert user.enable_apprise is True

    def test_user_info_defaults(self) -> None:
        """Test UserInfo with default values."""
        user = UserInfo(
            userid=123,
            username="TestUser",
            apprise_urls=[],
        )
        assert user.timezone == "UTC"
        assert user.mention_level == MentionLevel.AVATARHOVER
        assert user.email is None
        assert user.enable_wikidot_pm is True
        assert user.enable_email is True
        assert user.enable_apprise is True


class TestLoadConfigFromEnv:
    """Test loading configuration from environment variables."""

    def test_load_config_with_mongodb(self) -> None:
        """Test loading config with MongoDB URI."""
        env_vars = {
            "WIKIDOT_USERNAME": "test_user",
            "WIKIDOT_PASSWORD": "test_password",
            "RSS_SITE_URLS": '["https://scp-wiki.wikidot.com"]',
            "MONGODB_URI": "mongodb://localhost:27017",
            "USERS_JSON": (
                '{"123": {"userid": 123, "username": "TestUser", "apprise_urls": [], '
                '"timezone": "UTC", "mention_level": "avatarhover", "email": null, '
                '"enable_wikidot_pm": true, "enable_email": true, '
                '"enable_apprise": true}}'
            ),
        }
        with patch.dict(os.environ, env_vars):
            config = load_config_from_env()
            assert config.wikidot_username == "test_user"
            assert config.wikidot_password == "test_password"
            assert config.mongodb_uri == "mongodb://localhost:27017"
            assert len(config.rss_site_urls) == 1
            assert config.rss_site_urls[0] == "https://scp-wiki.wikidot.com"
            assert 123 in config.users
            assert config.users[123].username == "TestUser"

    def test_load_config_no_database_mode(self) -> None:
        """Test loading config in no-database mode."""
        env_vars = {
            "WIKIDOT_USERNAME": "test_user",
            "WIKIDOT_PASSWORD": "test_password",
            "RSS_SITE_URLS": '["https://scp-wiki.wikidot.com"]',
            "USERS_JSON": (
                '{"123": {"userid": 123, "username": "TestUser", "apprise_urls": [], '
                '"timezone": "UTC", "mention_level": "avatarhover", "email": null, '
                '"enable_wikidot_pm": true, "enable_email": true, '
                '"enable_apprise": true}}'
            ),
        }
        with patch.dict(os.environ, env_vars):
            config = load_config_from_env()
            assert config.mongodb_uri is None
            assert len(config.users) == 1

    def test_load_config_missing_username(self) -> None:
        """Test that missing WIKIDOT_USERNAME raises ValueError."""
        env_vars = {
            "WIKIDOT_PASSWORD": "test_password",
            "RSS_SITE_URLS": '["https://scp-wiki.wikidot.com"]',
        }
        with (
            patch.dict(os.environ, env_vars, clear=True),
            pytest.raises(ValueError, match="WIKIDOT_USERNAME"),
        ):
            load_config_from_env()

    def test_load_config_missing_password(self) -> None:
        """Test that missing WIKIDOT_PASSWORD raises ValueError."""
        env_vars = {
            "WIKIDOT_USERNAME": "test_user",
            "RSS_SITE_URLS": '["https://scp-wiki.wikidot.com"]',
        }
        with (
            patch.dict(os.environ, env_vars, clear=True),
            pytest.raises(ValueError, match="WIKIDOT_PASSWORD"),
        ):
            load_config_from_env()

    def test_load_config_missing_rss_site_urls(self) -> None:
        """Test that missing RSS_SITE_URLS raises ValueError."""
        env_vars = {
            "WIKIDOT_USERNAME": "test_user",
            "WIKIDOT_PASSWORD": "test_password",
        }
        with (
            patch.dict(os.environ, env_vars, clear=True),
            pytest.raises(ValueError, match="RSS_SITE_URLS"),
        ):
            load_config_from_env()

    def test_load_config_invalid_rss_site_urls_json(self) -> None:
        """Test that invalid RSS_SITE_URLS JSON raises ValueError."""
        env_vars = {
            "WIKIDOT_USERNAME": "test_user",
            "WIKIDOT_PASSWORD": "test_password",
            "RSS_SITE_URLS": "not-valid-json",
        }
        with (
            patch.dict(os.environ, env_vars),
            pytest.raises(ValueError, match="RSS_SITE_URLS must be a valid JSON"),
        ):
            load_config_from_env()

    def test_load_config_invalid_rss_site_url(self) -> None:
        """Test that invalid RSS site URL raises ValueError."""
        env_vars = {
            "WIKIDOT_USERNAME": "test_user",
            "WIKIDOT_PASSWORD": "test_password",
            "RSS_SITE_URLS": '["not-a-valid-url"]',
        }
        with (
            patch.dict(os.environ, env_vars),
            pytest.raises(ValueError, match="Invalid RSS site URL"),
        ):
            load_config_from_env()

    def test_load_config_no_database_missing_users_json(self) -> None:
        """Test that missing USERS_JSON in no-database mode raises ValueError."""
        env_vars = {
            "WIKIDOT_USERNAME": "test_user",
            "WIKIDOT_PASSWORD": "test_password",
            "RSS_SITE_URLS": '["https://scp-wiki.wikidot.com"]',
        }
        with (
            patch.dict(os.environ, env_vars, clear=True),
            pytest.raises(
                ValueError, match="USERS_JSON environment variable is required"
            ),
        ):
            load_config_from_env()

    def test_load_config_multiple_rss_sites(self) -> None:
        """Test loading config with multiple RSS sites."""
        env_vars = {
            "WIKIDOT_USERNAME": "test_user",
            "WIKIDOT_PASSWORD": "test_password",
            "RSS_SITE_URLS": '["https://scp-wiki.wikidot.com", "https://scp-wiki-cn.wikidot.com"]',
            "USERS_JSON": (
                '{"123": {"userid": 123, "username": "TestUser", "apprise_urls": [], '
                '"timezone": "UTC", "mention_level": "avatarhover", "email": null, '
                '"enable_wikidot_pm": true, "enable_email": true, '
                '"enable_apprise": true}}'
            ),
        }
        with patch.dict(os.environ, env_vars):
            config = load_config_from_env()
            assert len(config.rss_site_urls) == 2
            assert "https://scp-wiki.wikidot.com" in config.rss_site_urls
            assert "https://scp-wiki-cn.wikidot.com" in config.rss_site_urls

    def test_load_config_invalid_users_json(self) -> None:
        """Test that invalid USERS_JSON raises ValueError."""
        env_vars = {
            "WIKIDOT_USERNAME": "test_user",
            "WIKIDOT_PASSWORD": "test_password",
            "RSS_SITE_URLS": '["https://scp-wiki.wikidot.com"]',
            "USERS_JSON": "not-valid-json",
        }
        with (
            patch.dict(os.environ, env_vars),
            pytest.raises(ValueError, match="USERS_JSON must be a valid JSON"),
        ):
            load_config_from_env()


class TestScopariaConfig:
    """Test ScopariaConfig struct."""

    def test_config_creation(self) -> None:
        """Test creating ScopariaConfig."""
        users = {
            123: UserInfo(
                userid=123,
                username="TestUser",
                apprise_urls=[],
            )
        }
        config = ScopariaConfig(
            wikidot_username="test_user",
            wikidot_password="test_password",
            mongodb_uri="mongodb://localhost:27017",
            rss_site_urls=["https://scp-wiki.wikidot.com"],
            users=users,
        )
        assert config.wikidot_username == "test_user"
        assert config.wikidot_password == "test_password"
        assert config.mongodb_uri == "mongodb://localhost:27017"
        assert len(config.rss_site_urls) == 1
        assert len(config.users) == 1

    def test_config_no_database_mode(self) -> None:
        """Test creating ScopariaConfig in no-database mode."""
        users = {
            123: UserInfo(
                userid=123,
                username="TestUser",
                apprise_urls=[],
            )
        }
        config = ScopariaConfig(
            wikidot_username="test_user",
            wikidot_password="test_password",
            mongodb_uri=None,
            rss_site_urls=["https://scp-wiki.wikidot.com"],
            users=users,
        )
        assert config.mongodb_uri is None
        assert len(config.users) == 1
