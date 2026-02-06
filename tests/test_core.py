"""Tests for Scoparia core module."""

from collections import defaultdict
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scoparia.api import RSSForumPost
from scoparia.config import MentionLevel, UserInfo
from scoparia.core import ScopariaCore


class TestScopariaCore:
    """Test ScopariaCore class."""

    @pytest.fixture
    def core(self) -> ScopariaCore:
        """Create a ScopariaCore instance for testing."""
        return ScopariaCore()

    @pytest.fixture
    def sample_users(self) -> dict[int, UserInfo]:
        """Create sample users for testing."""
        return {
            123: UserInfo(
                userid=123,
                username="TestUser",
                apprise_urls=["json://localhost"],
                timezone="UTC",
                mention_level=MentionLevel.AVATARHOVER,
                email="test@example.com",
                contact_email=None,
                enable_wikidot_pm=True,
                enable_email=True,
                enable_apprise=True,
            ),
            456: UserInfo(
                userid=456,
                username="AnotherUser",
                apprise_urls=[],
                timezone="UTC",
                mention_level=MentionLevel.ALL,
                email=None,
                contact_email=None,
                enable_wikidot_pm=True,
                enable_email=False,
                enable_apprise=False,
            ),
        }

    async def test_initialize(self, core: ScopariaCore) -> None:
        """Test core initialization."""
        await core.initialize()
        # Should not raise any exceptions

    async def test_cleanup(self, core: ScopariaCore) -> None:
        """Test core cleanup."""
        await core.cleanup()
        # Should not raise any exceptions

    async def test_check_mentions_avatarhover(self, core: ScopariaCore) -> None:
        """Test checking mentions with avatarhover level."""
        users = {
            123: UserInfo(
                userid=123,
                username="TestUser",
                apprise_urls=[],
                mention_level=MentionLevel.AVATARHOVER,
            )
        }
        users_to_notify = set[int]()

        # Create mock post with avatarhover mention
        post = MagicMock()
        post.text = (
            '<span class="printuser avatarhover">'
            '<a href="https://www.wikidot.com/user:info/testuser" '
            'onclick="WIKIDOT.page.listeners.userInfo(123); return false;">'
            "TestUser</a></span>"
        )

        core._check_mentions(post, users, users_to_notify)
        assert 123 in users_to_notify

    async def test_check_mentions_all_level(self, core: ScopariaCore) -> None:
        """Test checking mentions with ALL level."""
        users = {
            123: UserInfo(
                userid=123,
                username="TestUser",
                apprise_urls=[],
                mention_level=MentionLevel.ALL,
            )
        }
        users_to_notify = set[int]()

        # Create mock post with regular mention (no avatarhover)
        post = MagicMock()
        post.text = (
            '<span class="printuser">'
            '<a href="https://www.wikidot.com/user:info/testuser" '
            'onclick="WIKIDOT.page.listeners.userInfo(123); return false;">'
            "TestUser</a></span>"
        )

        core._check_mentions(post, users, users_to_notify)
        assert 123 in users_to_notify

    async def test_check_mentions_disabled(self, core: ScopariaCore) -> None:
        """Test that disabled mention level doesn't trigger notification."""
        users = {
            123: UserInfo(
                userid=123,
                username="TestUser",
                apprise_urls=[],
                mention_level=MentionLevel.DISABLED,
            )
        }
        users_to_notify = set[int]()

        post = MagicMock()
        post.text = (
            '<span class="printuser avatarhover">'
            '<a href="https://www.wikidot.com/user:info/testuser" '
            'onclick="WIKIDOT.page.listeners.userInfo(123); return false;">'
            "TestUser</a></span>"
        )

        core._check_mentions(post, users, users_to_notify)
        assert 123 not in users_to_notify

    async def test_check_mentions_avatarhover_requires_class(
        self, core: ScopariaCore
    ) -> None:
        """Test that avatarhover level requires avatarhover class."""
        users = {
            123: UserInfo(
                userid=123,
                username="TestUser",
                apprise_urls=[],
                mention_level=MentionLevel.AVATARHOVER,
            )
        }
        users_to_notify = set[int]()

        # Post with mention but no avatarhover class
        post = MagicMock()
        post.text = (
            '<span class="printuser">'
            '<a href="https://www.wikidot.com/user:info/testuser" '
            'onclick="WIKIDOT.page.listeners.userInfo(123); return false;">'
            "TestUser</a></span>"
        )

        core._check_mentions(post, users, users_to_notify)
        assert 123 not in users_to_notify

    async def test_check_reply_to_user_post(
        self, core: ScopariaCore, sample_users: dict[int, UserInfo]
    ) -> None:
        """Test checking reply to user's post."""
        users_to_notify = set[int]()

        # Create mock post that replies to user 123's post
        post = MagicMock()
        parent_post = MagicMock()
        parent_post.created_by = MagicMock()
        parent_post.created_by.id = 123
        post.parents = [parent_post]

        thread = MagicMock()
        thread.created_by = MagicMock()
        thread.created_by.id = 999  # Different user

        await core._check_reply(post, thread, sample_users, users_to_notify)
        assert 123 in users_to_notify

    async def test_check_reply_to_thread_creator(
        self, core: ScopariaCore, sample_users: dict[int, UserInfo]
    ) -> None:
        """Test checking reply in user's thread."""
        users_to_notify = set[int]()

        # Create mock post in thread created by user 123
        post = MagicMock()
        post.parents = []

        thread = MagicMock()
        thread.created_by = MagicMock()
        thread.created_by.id = 123
        thread.page_fullname = None

        await core._check_reply(post, thread, sample_users, users_to_notify)
        assert 123 in users_to_notify

    async def test_send_email_notification(
        self, core: ScopariaCore, sample_users: dict[int, UserInfo]
    ) -> None:
        """Test sending email notification."""
        user_info = sample_users[123]
        posts = [
            RSSForumPost(
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
        ]

        with patch("scoparia.core.send_email") as mock_send_email:
            mock_send_email.return_value = True
            await core._send_email_notification(user_info, posts)
            mock_send_email.assert_called_once()
            call_args = mock_send_email.call_args
            assert call_args.kwargs["to_email"] == "test@example.com"
            assert call_args.kwargs["title"] == "[Scoparia] New post from TestUser"

    async def test_send_email_notification_no_email(
        self, core: ScopariaCore, sample_users: dict[int, UserInfo]
    ) -> None:
        """Test that email notification is skipped when effective_email is None."""
        user_info = sample_users[456]  # This user has no email or contact_email
        posts = [
            RSSForumPost(
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
        ]

        with patch("scoparia.core.send_email") as mock_send_email:
            await core._send_email_notification(user_info, posts)
            mock_send_email.assert_not_called()

    async def test_send_email_notification_uses_contact_email(
        self, core: ScopariaCore
    ) -> None:
        """Test that email notification uses contact_email when email is None."""
        user_info = UserInfo(
            userid=789,
            username="ContactUser",
            apprise_urls=[],
            timezone="UTC",
            mention_level=MentionLevel.AVATARHOVER,
            email=None,
            contact_email="contact@example.com",
            enable_wikidot_pm=True,
            enable_email=True,
            enable_apprise=False,
        )
        posts = [
            RSSForumPost(
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
        ]

        with patch("scoparia.core.send_email") as mock_send_email:
            mock_send_email.return_value = True
            await core._send_email_notification(user_info, posts)
            mock_send_email.assert_called_once()
            call_args = mock_send_email.call_args
            assert call_args.kwargs["to_email"] == "contact@example.com"

    async def test_send_email_notification_error_notifies_admin(
        self, core: ScopariaCore, sample_users: dict[int, UserInfo]
    ) -> None:
        """Test that email error sends notification to admin via enabled channels."""
        user_info = sample_users[123]
        posts = [
            RSSForumPost(
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
        ]

        # Create admin UserInfo (username matches wikidot_username in config)
        admin_user = UserInfo(
            userid=999,
            username="admin_user",
            apprise_urls=[],
            timezone="UTC",
            mention_level=MentionLevel.AVATARHOVER,
            email=None,
            enable_wikidot_pm=True,
            enable_email=True,
            enable_apprise=False,
            subscriptions=set(),
            unsubscriptions=set(),
        )

        # Mock config to indicate database mode
        mock_config = MagicMock()
        mock_config.mongodb_uri = "mongodb://localhost"
        mock_config.wikidot_username = "admin_user"

        with (
            patch("scoparia.core.send_email") as mock_send_email,
            patch("scoparia.core.get_client") as mock_get_client,
            patch("scoparia.core.get_config", return_value=mock_config),
            patch("scoparia.core.get_mongodb") as mock_get_mongodb,
        ):
            mock_send_email.side_effect = RuntimeError("Email sending failed")
            mock_client = AsyncMock()
            mock_client.send_private_message.return_value = True
            mock_get_client.return_value = mock_client

            mock_db = AsyncMock()
            mock_db.get_user_by_username.return_value = admin_user
            mock_get_mongodb.return_value = mock_db

            await core._send_email_notification(user_info, posts)

            # Verify admin notification was sent via Wikidot PM
            mock_client.send_private_message.assert_called_once()
            call_args = mock_client.send_private_message.call_args
            assert call_args.kwargs["to_user_id"] == 999
            assert "Email sending failed" in call_args.kwargs["body"]

    async def test_send_wikidot_pm_notification(
        self, core: ScopariaCore, sample_users: dict[int, UserInfo]
    ) -> None:
        """Test sending Wikidot PM notification."""
        user_info = sample_users[123]
        posts = [
            RSSForumPost(
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
        ]

        with patch("scoparia.core.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.send_private_message.return_value = True
            mock_get_client.return_value = mock_client

            await core._send_wikidot_pm_notification(user_info, posts)
            mock_client.send_private_message.assert_called_once()
            call_args = mock_client.send_private_message.call_args
            assert call_args.kwargs["to_user_id"] == 123
            assert call_args.kwargs["subject"] == "[Scoparia] New post from TestUser"

    async def test_send_all_notifications(
        self, core: ScopariaCore, sample_users: dict[int, UserInfo]
    ) -> None:
        """Test sending notifications via all enabled channels."""
        user_info = sample_users[123]
        posts = [
            RSSForumPost(
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
        ]

        with (
            patch("scoparia.core.get_client") as mock_get_client,
            patch("scoparia.core.send_email") as mock_send_email,
            patch("scoparia.core.generate_formatter") as mock_formatter,
            patch("scoparia.core.apprise"),
            patch.object(core, "_send_apprise_notification") as mock_send_apprise,
        ):
            # Mock client
            mock_client = AsyncMock()
            mock_client.send_private_message.return_value = True
            mock_get_client.return_value = mock_client

            # Mock email
            mock_send_email.return_value = True

            # Mock apprise notification method
            mock_send_apprise.return_value = None

            # Mock formatter
            mock_formatter_instance = MagicMock()
            mock_formatter_instance.compose_notification_content.return_value = (
                "Title",
                "Body",
            )
            mock_formatter.return_value = mock_formatter_instance

            await core.send_all_notifications(user_info, posts)

            # Verify all channels were called
            mock_client.send_private_message.assert_called_once()
            mock_send_email.assert_called_once()
            mock_send_apprise.assert_called_once()

    async def test_send_all_notifications_disabled_channels(
        self, core: ScopariaCore, sample_users: dict[int, UserInfo]
    ) -> None:
        """Test that disabled notification channels are skipped."""
        # Create user with all channels disabled
        user_info = UserInfo(
            userid=789,
            username="DisabledUser",
            apprise_urls=[],
            enable_wikidot_pm=False,
            enable_email=False,
            enable_apprise=False,
        )
        posts = [
            RSSForumPost(
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
        ]

        with (
            patch("scoparia.core.get_client") as mock_get_client,
            patch("scoparia.core.send_email") as mock_send_email,
            patch("scoparia.core.apprise"),
        ):
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            await core.send_all_notifications(user_info, posts)

            # Verify no channels were called
            mock_client.send_private_message.assert_not_called()
            mock_send_email.assert_not_called()

    def test_all_user_notifications_initialization(self, core: ScopariaCore) -> None:
        """Test that all_user_notifications is initialized correctly."""
        assert isinstance(core.all_user_notifications, defaultdict)
        assert len(core.all_user_notifications) == 0

    def test_all_user_notifications_cleared(
        self, core: ScopariaCore, sample_users: dict[int, UserInfo]
    ) -> None:
        """Test that all_user_notifications can be cleared."""
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
        core.all_user_notifications[123].append(post)
        assert len(core.all_user_notifications[123]) == 1

        core.all_user_notifications.clear()
        assert len(core.all_user_notifications) == 0

    async def test_load_users_from_env(self, core: ScopariaCore) -> None:
        """Test _load_users returns users from environment variable."""
        cfg_users = {
            123: UserInfo(
                userid=123,
                username="EnvUser",
                apprise_urls=[],
                mention_level=MentionLevel.AVATARHOVER,
            )
        }
        mock_config = MagicMock()
        mock_config.mongodb_uri = None
        mock_config.users = cfg_users

        with patch("scoparia.core.get_config", return_value=mock_config):
            result = await core._load_users()
            assert result is not None
            assert 123 in result
            assert result[123].username == "EnvUser"

    async def test_load_users_no_users_in_env(self, core: ScopariaCore) -> None:
        """Test _load_users returns None when no users in environment."""
        mock_config = MagicMock()
        mock_config.mongodb_uri = None
        mock_config.users = {}

        with patch("scoparia.core.get_config", return_value=mock_config):
            result = await core._load_users()
            assert result is None

    async def test_load_users_from_mongodb(self, core: ScopariaCore) -> None:
        """Test _load_users returns users from MongoDB."""
        db_users = {
            456: UserInfo(
                userid=456,
                username="DbUser",
                apprise_urls=[],
                mention_level=MentionLevel.ALL,
            )
        }
        mock_config = MagicMock()
        mock_config.mongodb_uri = "mongodb://localhost"

        mock_db = AsyncMock()
        mock_db.get_all_users.return_value = db_users

        with (
            patch("scoparia.core.get_config", return_value=mock_config),
            patch("scoparia.core.get_mongodb", return_value=mock_db),
        ):
            result = await core._load_users()
            assert result is not None
            assert 456 in result
            assert result[456].username == "DbUser"

    async def test_load_users_empty_mongodb(self, core: ScopariaCore) -> None:
        """Test _load_users returns None when MongoDB has no users."""
        mock_config = MagicMock()
        mock_config.mongodb_uri = "mongodb://localhost"

        mock_db = AsyncMock()
        mock_db.get_all_users.return_value = {}

        with (
            patch("scoparia.core.get_config", return_value=mock_config),
            patch("scoparia.core.get_mongodb", return_value=mock_db),
        ):
            result = await core._load_users()
            assert result is None

    async def test_fetch_rss_posts_from_sites_first_run(
        self, core: ScopariaCore
    ) -> None:
        """Test _fetch_rss_posts_from_sites on first run (no last check)."""
        rss_site_urls = ["https://test-site.wikidot.com"]
        last_rss_check_dict: dict[str, datetime] = {}

        new_posts, site_timestamps = await core._fetch_rss_posts_from_sites(
            rss_site_urls, last_rss_check_dict
        )

        # First run should not fetch posts, just record timestamp
        assert new_posts == []
        assert site_timestamps.get("https://test-site.wikidot.com") is not None

    async def test_fetch_rss_posts_from_sites_with_posts(
        self, core: ScopariaCore
    ) -> None:
        """Test _fetch_rss_posts_from_sites fetches posts when last check exists."""
        rss_site_urls = ["https://test-site.wikidot.com"]
        last_check = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        last_rss_check_dict = {"https://test-site.wikidot.com": last_check}

        mock_post = RSSForumPost(
            post_id=123,
            thread_id=456,
            title="Test Post",
            link="https://test-site.wikidot.com/forum/t-456#post-123",
            author_name="TestUser",
            content="<p>Test content</p>",
            publish_time=datetime.now(UTC),
            site_url="https://test-site.wikidot.com",
            parents=[],
        )
        build_date = datetime.now(UTC)

        mock_client = AsyncMock()
        mock_client.fetch_rss_posts.return_value = ([mock_post], build_date)

        with patch("scoparia.core.get_client", return_value=mock_client):
            new_posts, site_timestamps = await core._fetch_rss_posts_from_sites(
                rss_site_urls, last_rss_check_dict
            )

            assert len(new_posts) == 1
            assert new_posts[0].post_id == 123
            assert site_timestamps.get("https://test-site.wikidot.com") is not None

    async def test_save_timestamps_updates_github(self, core: ScopariaCore) -> None:
        """Test _save_timestamps updates GitHub variable."""
        site_timestamps = {
            "https://test-site.wikidot.com": datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        }
        last_rss_check_dict: dict[str, datetime] = {}

        with patch("scoparia.core.set_github_variable") as mock_set_var:
            mock_set_var.return_value = None
            await core._save_timestamps(site_timestamps, last_rss_check_dict)

            mock_set_var.assert_called_once()
            call_args = mock_set_var.call_args
            assert call_args[0][0] == "LAST_RSS_CHECK"

    async def test_save_timestamps_empty_timestamps(self, core: ScopariaCore) -> None:
        """Test _save_timestamps does nothing when timestamps are empty."""
        site_timestamps: dict[str, datetime] = {}
        last_rss_check_dict: dict[str, datetime] = {}

        with patch("scoparia.core.set_github_variable") as mock_set_var:
            await core._save_timestamps(site_timestamps, last_rss_check_dict)

            mock_set_var.assert_not_called()

    async def test_save_timestamps_merges_existing(self, core: ScopariaCore) -> None:
        """Test _save_timestamps merges new timestamps with existing ones."""
        existing_time = datetime(2024, 1, 10, 12, 0, 0, tzinfo=UTC)
        new_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

        site_timestamps = {"https://new-site.wikidot.com": new_time}
        last_rss_check_dict = {"https://existing-site.wikidot.com": existing_time}

        with patch("scoparia.core.set_github_variable") as mock_set_var:
            mock_set_var.return_value = None
            await core._save_timestamps(site_timestamps, last_rss_check_dict)

            mock_set_var.assert_called_once()
            call_args = mock_set_var.call_args
            json_value = call_args[0][1]
            # Verify both timestamps are in the JSON
            assert "existing-site" in json_value
            assert "new-site" in json_value
