"""Scoparia core notification logic."""

import os
from collections import defaultdict
from datetime import UTC, datetime

import apprise
import msgspec
from bs4 import BeautifulSoup

from . import logger
from .api import (
    ForumPost,
    ForumThread,
    Link,
    Page,
    RSSForumPost,
    get_client,
    sync_user_configs_from_wiki,
    user_parse,
)
from .config import MentionLevel, UserInfo, get_config
from .crom import get_page_author_id_from_crom
from .emailer import send_email
from .formatter import generate_formatter
from .github_storage import set_github_variable
from .mongodb import get_mongodb


class ScopariaCore:
    """Main Scoparia core class for RSS monitoring and notifications."""

    def __init__(self) -> None:
        """Initialize ScopariaCore instance."""
        # Temporary state for processing RSS feed notifications
        # This is reset at the start of each process_rss_feed call
        self.all_user_notifications: defaultdict[int, list[RSSForumPost]] = defaultdict[
            int, list[RSSForumPost]
        ](list)

    async def initialize(self) -> None:
        """Initialize core components."""
        logger.info("Scoparia core initialized")

    async def cleanup(self) -> None:
        """Cleanup resources."""
        logger.info("Scoparia core cleaned up")

    async def sync_contacts(self) -> None:
        """Sync contacts from Wikidot to database.

        Retrieves back contacts from Wikidot and upserts them into the database.
        This preserves existing user configuration (apprise_urls, timezone,
        mention_level) while updating username and email information.
        """
        logger.info("Starting contacts synchronization...")

        # Get contacts from Wikidot
        contacts = await get_client().get_contacts()

        # Bulk upsert contacts to database
        await get_mongodb().upsert_contacts(contacts)

        logger.info("Synchronized %s contacts to database", len(contacts))

    async def sync_user_configs(self) -> None:
        """Sync user configurations from config wiki to database.

        Fetches user configurations from the config wiki and updates the database.
        """
        logger.info("Starting user configs synchronization...")

        config_wiki_url = os.getenv("CONFIG_WIKI_URL", "https://scoparia.wikidot.com")
        user_config_category = os.getenv("USER_CONFIG_CATEGORY", "secret-notify")

        if not config_wiki_url or not user_config_category:
            logger.warning(
                "CONFIG_WIKI_URL or USER_CONFIG_CATEGORY not set, "
                "skipping user config sync"
            )
            return

        # Fetch user configs from wiki
        user_infos = await sync_user_configs_from_wiki(
            config_wiki_url=config_wiki_url,
            user_config_category=user_config_category,
        )

        # Bulk upsert user configs to database
        await get_mongodb().upsert_users(user_infos)

        logger.info("Synchronized %s user configs to database", len(user_infos))

    def _check_mentions(
        self,
        target_post: ForumPost,
        users: dict[int, UserInfo],
        users_to_notify: set[int],
    ) -> None:
        """Check for @mentions in post content and add to notification list.

        Args:
            target_post: The forum post from API
            users: Dictionary of monitored users
            users_to_notify: Set to add notified users to
        """
        # Parse HTML and find all user mentions (span.printuser elements)
        post_html = BeautifulSoup(target_post.text, "lxml")
        mentioned_user_elements = post_html.select("span.printuser")

        for user_elem in mentioned_user_elements:
            try:
                # Parse the user element to get user info
                mentioned_user = user_parse(user_elem)
                userid = mentioned_user.id

                # Skip if invalid, not monitored, or already notified
                if not userid or userid not in users or userid in users_to_notify:
                    continue

                # Check user's mention notification level preference
                user_info = users[userid]
                mention_level = user_info.mention_level

                # Skip if user disabled mention notifications
                if mention_level == MentionLevel.DISABLED:
                    logger.debug(
                        "User %s has disabled mention notifications",
                        user_info.username,
                    )
                    continue

                # Check if element has avatarhover class
                elem_classes = user_elem.get("class")
                has_avatarhover = (
                    isinstance(elem_classes, list) and "avatarhover" in elem_classes
                )

                # Skip if user only wants avatarhover but this isn't one
                if mention_level == MentionLevel.AVATARHOVER and not has_avatarhover:
                    logger.debug(
                        "User %s requires avatarhover, but mention doesn't have it",
                        user_info.username,
                    )
                    continue

                # User should be notified
                users_to_notify.add(userid)
                logger.debug(
                    "Post %s mentions %s%s",
                    target_post.id,
                    user_info.username,
                    " (avatarhover)" if has_avatarhover else "",
                )
            except Exception as e:
                logger.debug("Failed to parse mentioned user element: %s", e)

    async def _check_reply(
        self,
        target_post: ForumPost,
        thread: ForumThread,
        users: dict[int, UserInfo],
        users_to_notify: set[int],
    ) -> None:
        """Check for reply notifications.

        Checks if the post replies to any monitored user's post, or is in a
        thread/page created by a monitored user.

        Args:
            target_post: The forum post from API
            thread: The forum thread object
            users: Dictionary of monitored users
            users_to_notify: Set to add notified users to
        """
        # Check if post replies to any monitored user
        for parent_post in target_post.parents:
            userid = parent_post.created_by.id
            if userid and userid in users:
                users_to_notify.add(userid)
                logger.debug(
                    "Post %s replies to %s's post",
                    target_post.id,
                    users[userid].username,
                )

        # Check thread creator
        thread_creator_id = thread.created_by.id
        if thread_creator_id and thread_creator_id in users:
            users_to_notify.add(thread_creator_id)
            logger.debug(
                "Post %s in %s's thread",
                target_post.id,
                users[thread_creator_id].username,
            )

        # Check page author (if thread is associated with a page)
        if thread.page_fullname:
            page_author_id = None

            # Try to get page author from CROM API first (faster and more reliable)
            try:
                page_author_id = await get_page_author_id_from_crom(
                    thread.site_url, thread.page_fullname
                )
            except Exception as e:
                # If CROM API fails, try Wikidot API as fallback
                logger.debug(
                    "Failed to fetch page author from CROM API for %s: %s, "
                    "trying Wikidot API",
                    thread.page_fullname,
                    e,
                )
                try:
                    page = await Page.get_from_fullname(
                        thread.site_url, thread.page_fullname
                    )
                    if page:
                        page_author_id = page.created_by.id
                except Exception as fallback_error:
                    logger.debug(
                        "Failed to fetch page author from Wikidot API for %s: %s",
                        thread.page_fullname,
                        fallback_error,
                    )

            # Notify if page author is a monitored user
            if page_author_id and page_author_id in users:
                users_to_notify.add(page_author_id)
                logger.debug(
                    "Post %s in thread for page created by %s",
                    target_post.id,
                    users[page_author_id].username,
                )

    async def check_post_for_users(
        self, post: RSSForumPost, users: dict[int, UserInfo]
    ) -> None:
        """Check if a post mentions any monitored users.

        Checks if the post replies to, or is in a thread/page created by
        any monitored users. Adds the post to self.all_user_notifications for
        each user that should be notified.

        Args:
            post: Post dictionary from RSS feed.
            users: Dictionary mapping userid to UserInfo.
        """
        try:
            logger.debug("Getting post details for post %s", post.post_id)
            logger.debug("Getting site for post %s", post.post_id)
            site_url = post.site_url

            logger.debug("Getting thread %s for post %s", post.thread_id, post.post_id)
            # Get thread
            thread = await ForumThread.get_from_id(site_url, post.thread_id)
            logger.debug("Got thread %s, title: %s", post.thread_id, thread.title)

            # Get specific post
            target_post = await thread.get_post_by_id(post.post_id)

            if target_post is None:
                logger.warning(
                    "Could not find post %s in thread %s", post.post_id, post.thread_id
                )
                return

            # Collect all users that should be notified (using set for deduplication)
            users_to_notify = set[int]()

            # Check for reply notifications
            await self._check_reply(target_post, thread, users, users_to_notify)

            # Check for mentions in post content
            self._check_mentions(target_post, users, users_to_notify)

            # Build parent links
            post.parents = [
                Link(
                    text=thread.category.title,
                    url=f"{site_url}/forum/c-{thread.category.id}",
                ),
                Link(text=thread.title, url=f"{site_url}/forum/t-{thread.id}"),
            ] + [
                Link(
                    text=parent.title,
                    url=f"{site_url}/forum/t-{parent.thread_id}#post-{parent.id}",
                )
                for parent in target_post.parents
            ]

            # Add post to notification list for each user
            for userid in users_to_notify:
                self.all_user_notifications[userid].append(post)

        except Exception as e:
            logger.error("Error checking post %s: %s", post.post_id, e, exc_info=True)

    async def _send_apprise_notification(
        self, user_info: UserInfo, posts: list[RSSForumPost]
    ) -> None:
        """Send notification via Apprise asynchronously.

        Args:
            user_info: User information with Apprise URLs.
            posts: List of forum posts to notify about.
        """
        if not user_info.apprise_urls:
            logger.warning("User %s has no apprise_urls configured", user_info.username)
            return

        if not posts:
            logger.warning("Notification for %s has no posts", user_info.username)
            return

        # Create Apprise instance and add URLs
        servers = apprise.AppriseConfig(user_info.apprise_urls)
        apobj = apprise.Apprise(servers=servers)

        # Send notification to each service with appropriate format
        try:
            for server in apobj.servers:
                if not isinstance(server, apprise.NotifyBase):
                    continue

                formatter = (
                    generate_formatter("qqpush")
                    if str(server.service_name) == "QQ Push"
                    else generate_formatter(server.notify_format.value)
                )

                title, body = formatter.compose_notification_content(
                    posts, user_info.timezone
                )

                # Send to this specific server
                success = await server.async_notify(title=title, body=body)

                if success:
                    logger.info(
                        "Sent %s post(s) notification to %s via %s (format: %s)",
                        len(posts),
                        user_info.username,
                        server.service_name,
                        server.notify_format,
                    )
                else:
                    logger.warning(
                        "Failed to send notification to %s via %s",
                        user_info.username,
                        server.service_name,
                    )
        except Exception as e:
            logger.error("Failed to send notification to %s: %s", user_info.username, e)

    def _send_email_notification(
        self, user_info: UserInfo, posts: list[RSSForumPost]
    ) -> None:
        """Send notification via email.

        Args:
            user_info: User information with email address.
            posts: List of forum posts to notify about.
        """
        if not user_info.email:
            logger.warning(
                "User %s has no email address configured", user_info.username
            )
            return

        if not posts:
            logger.warning("Notification for %s has no posts", user_info.username)
            return

        try:
            # Compose notification with HTML format
            formatter = generate_formatter("html")
            title, body = formatter.compose_notification_content(
                posts, user_info.timezone
            )

            # Send email
            success = send_email(title=title, body=body, to_email=user_info.email)

            if success:
                logger.info(
                    "Sent %s post(s) notification to %s via email",
                    len(posts),
                    user_info.username,
                )
            else:
                logger.warning(
                    "Failed to send email notification to %s",
                    user_info.username,
                )
        except Exception as e:
            logger.error(
                "Failed to send email notification to %s: %s",
                user_info.username,
                e,
                exc_info=True,
            )

    async def _send_wikidot_pm_notification(
        self, user_info: UserInfo, posts: list[RSSForumPost]
    ) -> None:
        """Send notification via Wikidot private message.

        Args:
            user_info: User information with userid.
            posts: List of forum posts to notify about.
        """
        if not posts:
            logger.warning("Notification for %s has no posts", user_info.username)
            return

        try:
            # Compose notification with FTML format
            formatter = generate_formatter("ftml")
            title, body = formatter.compose_notification_content(
                posts, timezone=user_info.timezone
            )

            # Send Wikidot private message
            success = await get_client().send_private_message(
                to_user_id=user_info.userid,
                subject=title,
                body=body,
            )

            if success:
                logger.info(
                    "Sent %s post(s) notification to %s via Wikidot PM (user %s)",
                    len(posts),
                    user_info.username,
                    user_info.userid,
                )
            else:
                logger.warning(
                    "Failed to send Wikidot PM notification to %s (user %s)",
                    user_info.username,
                    user_info.userid,
                )
        except Exception as e:
            logger.error(
                "Failed to send Wikidot PM notification to %s (user %s): %s",
                user_info.username,
                user_info.userid,
                e,
                exc_info=True,
            )

    async def send_all_notifications(
        self, user_info: UserInfo, posts: list[RSSForumPost]
    ) -> None:
        """Send notifications via all enabled channels.

        Automatically sends notifications to all channels that are enabled
        in the user's settings. This is the main entry point for sending
        notifications to a user.

        Args:
            user_info: User information with notification settings.
            posts: List of forum posts to notify about.
        """
        if not posts:
            logger.warning("Notification for %s has no posts", user_info.username)
            return

        # Send Apprise notification if enabled and URLs are configured
        if user_info.enable_apprise:
            if user_info.apprise_urls:
                await self._send_apprise_notification(user_info, posts)
            else:
                logger.debug(
                    "Skipping Apprise notification for %s (no apprise_urls configured)",
                    user_info.username,
                )
        else:
            logger.debug(
                "Skipping Apprise notification for %s (disabled by user)",
                user_info.username,
            )

        # Send Wikidot private message notification if enabled
        if user_info.enable_wikidot_pm:
            await self._send_wikidot_pm_notification(user_info, posts)
        else:
            logger.debug(
                "Skipping Wikidot PM notification for %s (disabled by user)",
                user_info.username,
            )

        # Send email notification if enabled and email is configured
        if user_info.enable_email:
            if user_info.email:
                self._send_email_notification(user_info, posts)
            else:
                logger.debug(
                    "Skipping email notification for %s (no email configured)",
                    user_info.username,
                )
        else:
            logger.debug(
                "Skipping email notification for %s (disabled by user)",
                user_info.username,
            )

    async def process_rss_feed(self) -> None:
        """Process RSS feed and send notifications.

        This is the main entry point for cron execution.
        """
        logger.info("Starting RSS feed processing")

        cfg = get_config()

        # Get users based on database mode
        if cfg.mongodb_uri is None:
            # No-database mode: use users from environment variable
            if not cfg.users:
                logger.error("No users configured in USERS_JSON for no-database mode")
                return
            users = cfg.users
            logger.info("Using %s users from USERS_JSON (no-database mode)", len(users))
        else:
            # MongoDB mode: get users from database
            users = await get_mongodb().get_all_users()
            if not users:
                logger.warning("No users found in database")
                return
            logger.info("Monitoring %s users from database", len(users))

        # Get RSS site URLs from configuration
        rss_site_urls = cfg.rss_site_urls

        # Fetch RSS posts from all sites with per-site timestamps
        new_posts: list[RSSForumPost] = []
        site_timestamps: dict[str, datetime] = {}
        is_first_run = False

        # Get last check timestamps (per-site dictionary)
        # Always use GitHub Variables for last_rss_check
        last_rss_check_dict: dict[str, datetime]
        last_check_json = os.getenv("LAST_RSS_CHECK")
        if not last_check_json:
            logger.info("LAST_RSS_CHECK not set, treating as first run")
            last_rss_check_dict = {}
        else:
            try:
                # Parse JSON directly to dict[str, datetime] using msgspec
                last_rss_check_dict = msgspec.json.decode(
                    last_check_json, type=dict[str, datetime]
                )
            except msgspec.DecodeError:
                logger.warning("Failed to parse LAST_RSS_CHECK. Treating as first run")
                last_rss_check_dict = {}

        for site_url in rss_site_urls:
            # Get last check timestamp for this specific site
            last_check = last_rss_check_dict.get(site_url)

            if last_check is None:
                is_first_run = True
                logger.info("First run for %s, will record timestamp", site_url)
                # Use current time as placeholder for first run
                site_timestamps[site_url] = datetime.now(UTC)
                continue

            # Ensure last_check has timezone info
            if last_check.tzinfo is None:
                last_check = last_check.replace(tzinfo=UTC)

            logger.debug("Last check time for %s: %s", site_url, last_check.isoformat())

            try:
                site_posts, build_date = await get_client().fetch_rss_posts(
                    site_url, since=last_check
                )
                new_posts.extend(site_posts)
                logger.info("Fetched %s posts from %s", len(site_posts), site_url)

                site_timestamps[site_url] = build_date
            except Exception as e:
                logger.error(
                    "Failed to fetch RSS from %s: %s", site_url, e, exc_info=True
                )
                # Don't update LAST_RSS_CHECK for failed sites
                continue

        # Update timestamps after successful fetch
        # Only update timestamps for successfully fetched sites
        # Failed sites will keep their previous timestamps
        if site_timestamps:
            # Merge successful site timestamps with existing ones
            # This preserves timestamps for sites that failed to fetch
            updated_timestamps = last_rss_check_dict.copy()
            # Ensure all timestamps are in UTC before storing
            for site_url, timestamp in site_timestamps.items():
                if timestamp.tzinfo is None:
                    updated_timestamps[site_url] = timestamp.replace(tzinfo=UTC)
                else:
                    updated_timestamps[site_url] = timestamp
            # Convert datetime objects to strings for GitHub variable
            updated_timestamps_str = msgspec.json.encode(updated_timestamps).decode(
                "utf-8"
            )
            set_github_variable("LAST_RSS_CHECK", updated_timestamps_str)

        # Handle first run
        if is_first_run and not new_posts:
            logger.info("First run detected for some sites, skipping processing")
            return

        if not new_posts:
            logger.info("No new posts found since last check")
            return

        logger.info(
            f"Processing {len(new_posts)} new posts from {len(rss_site_urls)} sites"
        )

        # Reset notification state for this processing run
        self.all_user_notifications.clear()

        # Process each new post
        for post in new_posts:
            logger.debug("Processing post %s by %s", post.post_id, post.author_name)

            # Check if any users should be notified for this post
            await self.check_post_for_users(post, users)

        # Send notifications (one per user)
        for userid, posts_list in self.all_user_notifications.items():
            user_info = users[userid]
            # Send all notifications via enabled channels
            await self.send_all_notifications(user_info, posts_list)

        logger.info("RSS feed processing complete. Processed %s posts", len(new_posts))


# Global core instance
_core_instance: ScopariaCore | None = None


def init_core() -> None:
    """Initialize global Scoparia core instance.

    Raises:
        RuntimeError: If already initialized.
    """
    global _core_instance
    if _core_instance is not None:
        raise RuntimeError("Core already initialized.")

    _core_instance = ScopariaCore()


def get_core() -> ScopariaCore:
    """Get global Scoparia core instance.

    Returns:
        ScopariaCore instance.

    Raises:
        RuntimeError: If core has not been initialized.
    """
    if _core_instance is None:
        raise RuntimeError("Core not initialized. Call init_core() first.")
    return _core_instance
