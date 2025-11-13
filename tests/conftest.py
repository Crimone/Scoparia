"""Pytest configuration and fixtures for Scoparia tests."""

import os
from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scoparia.api import RSSForumPost
from scoparia.config import MentionLevel, UserInfo


@pytest.fixture
def mock_env_vars() -> Generator[dict[str, str], None, None]:
    """Fixture to mock environment variables for testing."""
    env_vars = {
        "WIKIDOT_USERNAME": "test_user",
        "WIKIDOT_PASSWORD": "test_password",
        "RSS_SITE_URLS": '["https://scp-wiki.wikidot.com"]',
        "USERS_JSON": (
            '{"123": {"userid": 123, "username": "TestUser", "apprise_urls": [], '
            '"timezone": "UTC", "mention_level": "avatarhover", '
            '"email": "test@example.com", "enable_wikidot_pm": true, '
            '"enable_email": true, "enable_apprise": true}}'
        ),
    }
    with patch.dict(os.environ, env_vars, clear=False):
        yield env_vars


@pytest.fixture
def sample_user_info() -> UserInfo:
    """Fixture providing sample user information."""
    return UserInfo(
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


@pytest.fixture
def sample_users_dict(sample_user_info: UserInfo) -> dict[int, UserInfo]:
    """Fixture providing a dictionary of sample users."""
    return {sample_user_info.userid: sample_user_info}


@pytest.fixture
def sample_rss_post() -> RSSForumPost:
    """Fixture providing a sample RSS forum post."""
    return RSSForumPost(
        post_id=123,
        thread_id=456,
        site_url="https://scp-wiki.wikidot.com",
        author_name="TestAuthor",
        title="Test Post Title",
        content="<p>Test post content</p>",
        link="https://scp-wiki.wikidot.com/forum/t-456/test-post-title#post-123",
        publish_time=datetime.now(UTC),
        parents=[],
    )


@pytest.fixture
def mock_wikidot_client() -> AsyncMock:
    """Fixture providing a mocked Wikidot API client."""
    client = AsyncMock()
    client.get_contacts.return_value = []
    client.fetch_rss_posts.return_value = ([], datetime.now(UTC))
    client.send_private_message.return_value = True
    return client


@pytest.fixture
def mock_mongodb() -> AsyncMock:
    """Fixture providing a mocked MongoDB client."""
    db = AsyncMock()
    db.get_all_users.return_value = {}
    db.get_metadata.return_value = None
    db.set_metadata.return_value = None
    db.upsert_contacts.return_value = None
    db.upsert_users.return_value = None
    return db


@pytest.fixture
def sample_html_with_mentions() -> str:
    """Fixture providing sample HTML with user mentions."""
    return """
    <div>
        <p>This is a test post.</p>
        <span class="printuser avatarhover"><a href="/user:info/User1">User1</a></span>
        <span class="printuser"><a href="/user:info/User2">User2</a></span>
        <p>More content here.</p>
    </div>
    """


@pytest.fixture
def sample_forum_post() -> MagicMock:
    """Fixture providing a mocked ForumPost object."""
    post = MagicMock()
    post.id = 123
    post.text = (
        '<p>Test content with <span class="printuser avatarhover">'
        '<a href="/user:info/123">TestUser</a></span></p>'
    )
    post.parents = []
    post.created_by = MagicMock()
    post.created_by.id = 789
    return post


@pytest.fixture
def sample_forum_thread() -> MagicMock:
    """Fixture providing a mocked ForumThread object."""
    thread = MagicMock()
    thread.id = 456
    thread.title = "Test Thread"
    thread.created_by = MagicMock()
    thread.created_by.id = 999
    thread.page_fullname = None
    thread.site_url = "https://scp-wiki.wikidot.com"
    thread.category = MagicMock()
    thread.category.id = 1
    thread.category.title = "Test Category"
    return thread


@pytest.fixture
def mock_apprise_notification() -> AsyncMock:
    """Fixture providing a mocked Apprise notification."""
    notification = AsyncMock()
    notification.async_notify.return_value = True
    notification.service_name = "TestService"
    notification.notify_format = MagicMock()
    notification.notify_format.value = "text"
    return notification
