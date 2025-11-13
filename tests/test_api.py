"""Tests for Scoparia API module."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scoparia.api import Link, RSSForumPost, get_client, init_client


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
