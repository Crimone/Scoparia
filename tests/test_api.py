"""Tests for Scoparia API module."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scoparia.api import (
    Contact,
    Link,
    RSSForumPost,
    get_client,
    init_client,
    normalize_post_url,
)


class TestRSSForumPost:
    """Test RSSForumPost struct."""

    def test_rss_forum_post_creation(self) -> None:
        """Test creating RSSForumPost."""
        post = RSSForumPost(
            post_id=123,
            thread_id=456,
            title="Test Post",
            link="https://example.com",
            author_name="TestUser",
            content="<p>Test content</p>",
            publish_time=datetime.now(UTC),
            site_url="https://scp-wiki.wikidot.com",
            parents=[],
        )
        assert post.post_id == 123
        assert post.thread_id == 456
        assert post.title == "Test Post"
        assert post.link == "https://example.com"
        assert post.author_name == "TestUser"
        assert post.content == "<p>Test content</p>"
        assert post.site_url == "https://scp-wiki.wikidot.com"
        assert post.parents == []

    def test_rss_forum_post_with_parents(self) -> None:
        """Test creating RSSForumPost with parents."""
        parents = [
            Link(text="Category", url="https://example.com/category"),
            Link(text="Thread", url="https://example.com/thread"),
        ]
        post = RSSForumPost(
            post_id=123,
            thread_id=456,
            title="Test Post",
            link="https://example.com",
            author_name="TestUser",
            content="<p>Test content</p>",
            publish_time=datetime.now(UTC),
            site_url="https://scp-wiki.wikidot.com",
            parents=parents,
        )
        assert len(post.parents) == 2
        assert post.parents[0].text == "Category"
        assert post.parents[1].text == "Thread"


class TestLink:
    """Test Link struct."""

    def test_link_creation(self) -> None:
        """Test creating Link."""
        link = Link(text="Test Link", url="https://example.com")
        assert link.text == "Test Link"
        assert link.url == "https://example.com"


class TestContact:
    """Test Contact struct."""

    def test_contact_creation(self) -> None:
        """Test creating Contact."""
        contact = Contact(userid=123, username="TestUser", email="test@example.com")
        assert contact.userid == 123
        assert contact.username == "TestUser"
        assert contact.email == "test@example.com"


class TestNormalizePostUrl:
    """Test normalize_post_url function."""

    def test_normalize_url_with_https(self) -> None:
        """Test normalizing URL with https prefix."""
        url = "https://scp-wiki-cn.wikidot.com/forum/t-123#post-456"
        result = normalize_post_url(url)
        assert result == "scp-wiki-cn.wikidot.com/forum/t-123#post-456"

    def test_normalize_url_with_http(self) -> None:
        """Test normalizing URL with http prefix."""
        url = "http://scp-wiki-cn.wikidot.com/forum/t-123#post-456"
        result = normalize_post_url(url)
        assert result == "scp-wiki-cn.wikidot.com/forum/t-123#post-456"

    def test_normalize_url_without_protocol(self) -> None:
        """Test normalizing URL without protocol prefix."""
        url = "scp-wiki-cn.wikidot.com/forum/t-123#post-456"
        result = normalize_post_url(url)
        assert result == "scp-wiki-cn.wikidot.com/forum/t-123#post-456"

    def test_normalize_url_with_extra_path(self) -> None:
        """Test normalizing URL with extra path segments."""
        url = "https://scp-wiki-cn.wikidot.com/forum/t-123/123#post-456"
        result = normalize_post_url(url)
        assert result == "scp-wiki-cn.wikidot.com/forum/t-123#post-456"

    def test_normalize_url_with_slash_in_anchor(self) -> None:
        """Test normalizing URL with slash before anchor."""
        url = "https://scp-wiki-cn.wikidot.com/forum/t-123/#post-456"
        result = normalize_post_url(url)
        assert result == "scp-wiki-cn.wikidot.com/forum/t-123#post-456"

    def test_normalize_thread_url_without_post(self) -> None:
        """Test normalizing thread URL without post ID."""
        url = "https://scp-wiki-cn.wikidot.com/forum/t-123"
        result = normalize_post_url(url)
        assert result == "scp-wiki-cn.wikidot.com/forum/t-123"

    def test_normalize_thread_url_with_extra_path(self) -> None:
        """Test normalizing thread URL with extra path but no post ID."""
        url = "https://scp-wiki-cn.wikidot.com/forum/t-123/some-title"
        result = normalize_post_url(url)
        assert result == "scp-wiki-cn.wikidot.com/forum/t-123"

    def test_normalize_url_invalid_format(self) -> None:
        """Test that invalid URL format returns None."""
        url = "https://example.com/invalid"
        result = normalize_post_url(url)
        assert result is None

    def test_normalize_url_non_wikidot_domain(self) -> None:
        """Test that non-wikidot.com domain returns None."""
        url = "https://example.com/forum/t-123#post-456"
        result = normalize_post_url(url)
        assert result is None

    def test_normalize_url_missing_thread_id(self) -> None:
        """Test that URL missing thread ID returns None."""
        url = "https://scp-wiki-cn.wikidot.com/forum/t-#post-456"
        result = normalize_post_url(url)
        assert result is None


class TestClientGlobalFunctions:
    """Test global client functions."""

    @pytest.mark.asyncio
    async def test_init_client(self) -> None:
        """Test initializing client."""
        with (
            patch("scoparia.api.Client") as mock_client_class,
            patch("scoparia.api.HTTPAuthentication") as mock_auth,
        ):
            mock_client_instance = AsyncMock()
            mock_client_instance.is_logged_in = False
            mock_client_class.return_value = mock_client_instance

            mock_auth.login = AsyncMock()

            await init_client("test_user", "test_password")

            mock_client_class.assert_called_once()
            mock_auth.login.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_client_already_initialized(self) -> None:
        """Test that initializing client twice raises RuntimeError."""
        with (
            patch("scoparia.api._client_instance", MagicMock()),
            patch("scoparia.api._client_lock") as mock_lock,
        ):

            async def lock_enter(self):
                raise RuntimeError("Client already initialized.")

            mock_lock.__aenter__ = lock_enter

            with pytest.raises(RuntimeError, match="Client already initialized"):
                await init_client("test_user", "test_password")

    def test_get_client_not_initialized(self) -> None:
        """Test that getting client before initialization raises RuntimeError."""
        with (
            patch("scoparia.api._client_instance", None),
            pytest.raises(RuntimeError, match="Client not initialized"),
        ):
            get_client()

    def test_get_client_initialized(self) -> None:
        """Test getting client after initialization."""
        mock_instance = MagicMock()
        with patch("scoparia.api._client_instance", mock_instance):
            result = get_client()
            assert result == mock_instance
