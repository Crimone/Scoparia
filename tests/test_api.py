"""Tests for Scoparia API module."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scoparia.api import (
    Contact,
    ForumThread,
    Link,
    NeedsSanitizationError,
    RSSForumPost,
    User,
    UserType,
    _parse_user_config_from_page,
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


class TestUserStruct:
    """Test User struct default values."""

    def test_user_default_values(self) -> None:
        """Test that User struct uses correct default values."""
        user = User(type=UserType.USER)
        assert user.id == 0
        assert user.name == ""
        assert user.unix_name == ""
        assert user.avatar_url == ""
        assert user.ip == ""

    def test_user_with_values(self) -> None:
        """Test User struct with explicit values."""
        user = User(
            type=UserType.USER,
            id=123,
            name="TestUser",
            unix_name="testuser",
            avatar_url="https://example.com/avatar.png",
        )
        assert user.id == 123
        assert user.name == "TestUser"
        assert user.unix_name == "testuser"
        assert user.avatar_url == "https://example.com/avatar.png"
        assert user.ip == ""

    def test_anonymous_user_with_ip(self) -> None:
        """Test anonymous user with IP address."""
        user = User(
            type=UserType.ANONYMOUS,
            name="Anonymous",
            unix_name="anonymous",
            ip="192.168.1.1",
        )
        assert user.type == UserType.ANONYMOUS
        assert user.ip == "192.168.1.1"


class TestForumThreadHelpers:
    """Test ForumThread static helper methods."""

    def test_parse_thread_category(self) -> None:
        """Test _parse_thread_category with valid breadcrumbs."""
        from bs4 import BeautifulSoup

        html = """
        <div class="forum-breadcrumbs">
            <a href="/forum/c-12345/category-name">Test Category</a>
            » Thread Title
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        bc_elem = soup.select_one("div.forum-breadcrumbs")
        assert bc_elem is not None

        category = ForumThread._parse_thread_category(bc_elem)
        assert category.id == 12345
        assert category.title == "Test Category"

    def test_parse_thread_category_missing_link(self) -> None:
        """Test _parse_thread_category raises exception when category link missing."""
        from bs4 import BeautifulSoup

        from scoparia.api import NoElementException

        html = """<div class="forum-breadcrumbs">No category link here</div>"""
        soup = BeautifulSoup(html, "lxml")
        bc_elem = soup.select_one("div.forum-breadcrumbs")
        assert bc_elem is not None

        with pytest.raises(NoElementException):
            ForumThread._parse_thread_category(bc_elem)

    def test_parse_thread_page_fullname(self) -> None:
        """Test _parse_thread_page_fullname with valid description block."""
        from bs4 import BeautifulSoup

        html = """
        <html>
        <div class="description-block">
            <a href="/scp-001">SCP-001</a>
            <a href="/forum/t-123">Forum Thread</a>
        </div>
        </html>
        """
        soup = BeautifulSoup(html, "lxml")

        result = ForumThread._parse_thread_page_fullname(soup)
        assert result == "scp-001"

    def test_parse_thread_page_fullname_no_description(self) -> None:
        """Test _parse_thread_page_fullname returns None when no description block."""
        from bs4 import BeautifulSoup

        html = """<html><div>No description block</div></html>"""
        soup = BeautifulSoup(html, "lxml")

        result = ForumThread._parse_thread_page_fullname(soup)
        assert result is None


class TestParseUserConfigFromPage:
    """Test _parse_user_config_from_page function."""

    def test_parse_user_config_missing_content(self) -> None:
        """Test that missing content element raises ValueError."""
        from bs4 import BeautifulSoup

        html = """<div class="page"><span class="query_name">test</span></div>"""
        soup = BeautifulSoup(html, "lxml")
        page_elem = soup.select_one("div.page")
        assert page_elem is not None

        creator = User(type=UserType.USER, id=123, name="TestUser")

        with pytest.raises(ValueError, match="missing content element"):
            _parse_user_config_from_page(page_elem, "test", creator)

    def test_parse_user_config_invalid_yaml(self) -> None:
        """Test that invalid YAML raises NeedsSanitizationError."""
        from bs4 import BeautifulSoup

        html = """
        <div class="page">
            <span class="query_content">invalid: yaml: content: :</span>
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        page_elem = soup.select_one("div.page")
        assert page_elem is not None

        creator = User(type=UserType.USER, id=123, name="TestUser")

        with pytest.raises(NeedsSanitizationError, match="Invalid YAML format"):
            _parse_user_config_from_page(page_elem, "test", creator)

    def test_parse_user_config_valid(self) -> None:
        """Test parsing valid user config from page element."""
        from bs4 import BeautifulSoup

        html = """
        <div class="page">
            <span class="query_content">
timezone: Asia/Shanghai
mention_level: all
enable_wikidot_pm: "1"
enable_email: "1"
enable_apprise: "0"
            </span>
            <span class="query_email">test@example.com</span>
            <span class="query_apprise_urls">json://localhost</span>
            <span class="query_subscriptions">scp-wiki.wikidot.com/forum/t-123</span>
            <span class="query_unsubscriptions">scp-wiki.wikidot.com/forum/t-456</span>
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        page_elem = soup.select_one("div.page")
        assert page_elem is not None

        creator = User(type=UserType.USER, id=123, name="TestUser")

        user_info = _parse_user_config_from_page(page_elem, "123", creator)

        assert user_info.userid == 123
        assert user_info.username == "TestUser"
        assert user_info.timezone == "Asia/Shanghai"
        assert user_info.email == "test@example.com"
        assert user_info.enable_wikidot_pm is True
        assert user_info.enable_email is True
        assert user_info.enable_apprise is False
