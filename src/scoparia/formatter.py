import re
from abc import ABC, abstractmethod
from zoneinfo import ZoneInfo

import html2text
from bs4 import BeautifulSoup

from . import logger
from .api import (
    Link,
    RSSForumPost,
)

LOGO_URL = "https://cdn.jsdelivr.net/gh/Crimone/Scoparia@main/src/scoparia/static/scoparia.webp"


def _truncate_html_safe(html_text: str, max_length: int = 200) -> str:
    """Truncate HTML text to specified length without breaking tags.

    First truncates the HTML string at a safe position (not inside tags),
    then uses BeautifulSoup to parse and automatically close any unclosed tags.
    BeautifulSoup can handle unclosed HTML tags and will fix them automatically.

    Args:
        html_text: HTML text to truncate.
        max_length: Maximum length of the truncated HTML string. Defaults to 200.

    Returns:
        Truncated HTML text with all tags properly closed.
    """
    if len(html_text.strip()) == 0:
        return html_text

    # Quick check: if HTML length is already under limit, return as-is
    if len(html_text) <= max_length:
        return html_text

    # Find a safe truncation point (not inside a tag)
    truncate_pos = max_length
    tag_start = html_text.rfind("<", 0, truncate_pos)
    if tag_start != -1:
        tag_end = html_text.find(">", tag_start, truncate_pos + 100)
        if tag_end == -1 or tag_end >= truncate_pos:
            # We're inside a tag, truncate before the tag starts
            truncate_pos = tag_start

    # Truncate at safe position
    truncated_html = html_text[:truncate_pos] + "..."

    try:
        # BeautifulSoup will automatically close any unclosed tags
        soup = BeautifulSoup(truncated_html, "lxml")
        result = soup.body.decode_contents() if soup.body else soup.decode_contents()

        return result
    except Exception:
        # Fallback: if parsing fails, return simple truncation
        logger.debug("BeautifulSoup parsing failed, using fallback truncation")
        return html_text[:truncate_pos] if truncate_pos > 0 else html_text[:max_length]


def _generate_title(posts: list[RSSForumPost]) -> str:
    """Generate notification title based on number of posts.

    Args:
        posts: List of forum posts triggering the notification.

    Returns:
        Notification title string.
    """
    if len(posts) == 1:
        return "[Scoparia] New post"
    return f"[Scoparia] {len(posts)} new posts"


class NotificationFormatter(ABC):
    """Abstract base class for notification content formatters."""

    # Class attributes that must be defined by subclasses
    separator: str
    footer: str

    @abstractmethod
    def format_time(self, post: RSSForumPost, timezone: str) -> str:
        """Format post publish time.

        Args:
            post: The RSS forum post.
            timezone: User's timezone (IANA format).

        Returns:
            Formatted time string.
        """
        pass

    @abstractmethod
    def format_content(self, html_content: str) -> str:
        """Format post content from HTML.

        Args:
            html_content: HTML content to format.

        Returns:
            Formatted content string.
        """
        pass

    @abstractmethod
    def format_parent_link(self, parent: Link) -> str:
        """Format a parent link.

        Args:
            parent: The parent link to format.

        Returns:
            Formatted parent link string.
        """
        pass

    @abstractmethod
    def format_header(self, post: RSSForumPost, publish_time_str: str) -> str:
        """Format post header line.

        Args:
            post: The RSS forum post.
            publish_time_str: Formatted publish time string.

        Returns:
            Formatted header line.
        """
        pass

    @abstractmethod
    def format_link(self, post: RSSForumPost) -> str:
        """Format post link line.

        Args:
            post: The RSS forum post.

        Returns:
            Formatted link line, or empty string if links should be omitted.
        """
        pass

    @abstractmethod
    def format_post_section(
        self,
        post: RSSForumPost,
        content: str,
        header_line: str,
        parents_line: str,
        link_line: str,
    ) -> str:
        """Format a complete post section.

        Args:
            post: The RSS forum post.
            content: Formatted content.
            header_line: Formatted header line.
            parents_line: Formatted parents line.
            link_line: Formatted link line.

        Returns:
            Complete formatted post section.
        """
        pass

    def post_process_body(self, body: str) -> str:
        """Post-process the final body text (optional).

        Args:
            body: The final body text.

        Returns:
            Post-processed body text.
        """
        return body

    def compose_notification_content(
        self, posts: list[RSSForumPost], timezone: str
    ) -> tuple[str, str]:
        """Compose notification title and body using this formatter.

        This is the unified function that handles all notification formats
        by delegating format-specific logic to the formatter.

        Args:
            posts: List of forum posts triggering the notification.
            timezone: User's timezone (IANA format).

        Returns:
            Tuple of (title, body) for the notification.
        """
        title = _generate_title(posts)

        # Format posts
        post_sections: list[str] = []
        for post in posts:
            # Format time
            publish_time_str = self.format_time(post, timezone)

            # Truncate and format content
            truncated_html = _truncate_html_safe(post.content, max_length=200)
            content = self.format_content(truncated_html)

            # Build parents line
            parent_links = [self.format_parent_link(parent) for parent in post.parents]
            parents_line = f"ℹ️ {' » '.join(parent_links)}"

            # Format header
            header_line = self.format_header(post, publish_time_str)

            # Format link
            link_line = self.format_link(post)

            # Format complete post section
            post_section = self.format_post_section(
                post, content, header_line, parents_line, link_line
            )
            post_sections.append(post_section)

        # Combine all posts
        post_sections.append(self.footer)
        body = self.separator.join(post_sections)

        # Apply post-processing if needed
        body = self.post_process_body(body)

        return title, body


class HTMLFormatter(NotificationFormatter):
    """Formatter for HTML format notifications."""

    separator: str = "\n\n<hr>\n\n"
    footer: str = (
        f'<img src="{LOGO_URL}" height="14" alt="⚡" '
        'style="height: 1em; vertical-align: middle;"> '
        '<em>Powered by <a href="https://github.com/Crimone/Scoparia">'
        "Scoparia</a></em>"
    )

    def format_time(self, post: RSSForumPost, timezone: str) -> str:
        """Format post publish time in HTML format.

        Args:
            post: The RSS forum post.
            timezone: User's timezone (IANA format).

        Returns:
            Formatted time string.
        """
        user_tz = ZoneInfo(timezone)
        local_time = post.publish_time.astimezone(user_tz)
        return local_time.strftime("%d %b %Y, %H:%M:%S %Z")

    def format_content(self, html_content: str) -> str:
        """Format post content from HTML (keep as HTML).

        Args:
            html_content: HTML content to format.

        Returns:
            HTML content string.
        """
        return html_content

    def format_parent_link(self, parent: Link) -> str:
        """Format a parent link in HTML.

        Args:
            parent: The parent link to format.

        Returns:
            HTML formatted parent link.
        """
        return f'<a href="{parent.url}">{parent.text}</a>'

    def format_header(self, post: RSSForumPost, publish_time_str: str) -> str:
        """Format post header line in HTML.

        Args:
            post: The RSS forum post.
            publish_time_str: Formatted publish time string.

        Returns:
            HTML formatted header line.
        """
        if post.title:
            return (
                f"💬 <strong>{post.title}</strong> - "
                f"👤 <strong>{post.author_name}</strong> - "
                f"🕐 {publish_time_str}"
            )
        return f"👤 <strong>{post.author_name}</strong> - 🕐 {publish_time_str}"

    def format_link(self, post: RSSForumPost) -> str:
        """Format post link line in HTML.

        Args:
            post: The RSS forum post.

        Returns:
            HTML formatted link line.
        """
        return f'🔗 <a href="{post.link}">{post.link}</a>'

    def format_post_section(
        self,
        post: RSSForumPost,
        content: str,
        header_line: str,
        parents_line: str,
        link_line: str,
    ) -> str:
        """Format a complete post section in HTML.

        Args:
            post: The RSS forum post.
            content: Formatted content.
            header_line: Formatted header line.
            parents_line: Formatted parents line.
            link_line: Formatted link line.

        Returns:
            Complete HTML formatted post section.
        """
        return f"""
<p style="margin-bottom: 0.5em;">{link_line}</p>
<p style="margin-bottom: 0.5em;">{header_line}</p>
<blockquote>{content}</blockquote>
<p style="margin-top: 0.5em;">{parents_line}</p>
"""


class MarkdownFormatter(NotificationFormatter):
    """Formatter for Markdown format notifications."""

    separator: str = "\n\n---\n\n"
    footer: str = "⚡ *Powered by [Scoparia](https://github.com/Crimone/Scoparia)*"

    def format_time(self, post: RSSForumPost, timezone: str) -> str:
        """Format post publish time in Markdown format.

        Args:
            post: The RSS forum post.
            timezone: User's timezone (IANA format).

        Returns:
            Formatted time string.
        """
        user_tz = ZoneInfo(timezone)
        local_time = post.publish_time.astimezone(user_tz)
        return local_time.strftime("%d %b %Y, %H:%M:%S %Z")

    def format_content(self, html_content: str) -> str:
        """Format post content from HTML to Markdown.

        Args:
            html_content: HTML content to format.

        Returns:
            Markdown formatted content.
        """
        h = html2text.HTML2Text()
        h.body_width = 0  # Don't wrap lines
        content = h.handle(html_content).strip()
        return "\n".join([f"> {line}" for line in content.split("\n")])

    def format_parent_link(self, parent: Link) -> str:
        """Format a parent link in Markdown.

        Args:
            parent: The parent link to format.

        Returns:
            Markdown formatted parent link.
        """
        return f"[{parent.text}]({parent.url})"

    def format_header(self, post: RSSForumPost, publish_time_str: str) -> str:
        """Format post header line in Markdown.

        Args:
            post: The RSS forum post.
            publish_time_str: Formatted publish time string.

        Returns:
            Markdown formatted header line.
        """
        if post.title:
            return (
                f"💬 **{post.title}** - "
                f"👤 **{post.author_name}** - "
                f"🕐 {publish_time_str}"
            )
        return f"👤 **{post.author_name}** - 🕐 {publish_time_str}"

    def format_link(self, post: RSSForumPost) -> str:
        """Format post link line in Markdown.

        Args:
            post: The RSS forum post.

        Returns:
            Markdown formatted link line.
        """
        return f"🔗 <{post.link}>"

    def format_post_section(
        self,
        post: RSSForumPost,
        content: str,
        header_line: str,
        parents_line: str,
        link_line: str,
    ) -> str:
        """Format a complete post section in Markdown.

        Args:
            post: The RSS forum post.
            content: Formatted content.
            header_line: Formatted header line.
            parents_line: Formatted parents line.
            link_line: Formatted link line.

        Returns:
            Complete Markdown formatted post section.
        """
        return f"""
{link_line}

{header_line}

{content}

{parents_line}
"""


class TextFormatter(NotificationFormatter):
    """Formatter for plain text format notifications."""

    separator: str = "\n\n══════\n\n"
    footer: str = "⚡ Powered by Scoparia | https://github.com/Crimone/Scoparia"

    def format_time(self, post: RSSForumPost, timezone: str) -> str:
        """Format post publish time in plain text format.

        Args:
            post: The RSS forum post.
            timezone: User's timezone (IANA format).

        Returns:
            Formatted time string.
        """
        user_tz = ZoneInfo(timezone)
        local_time = post.publish_time.astimezone(user_tz)
        return local_time.strftime("%d %b %Y, %H:%M:%S %Z")

    def format_content(self, html_content: str) -> str:
        """Format post content from HTML to plain text.

        Args:
            html_content: HTML content to format.

        Returns:
            Plain text formatted content.
        """
        h = html2text.HTML2Text()
        h.ignore_links = True
        h.body_width = 0  # Don't wrap lines
        return h.handle(html_content).strip()

    def format_parent_link(self, parent: Link) -> str:
        """Format a parent link in plain text (no link).

        Args:
            parent: The parent link to format.

        Returns:
            Plain text (just the text, no link).
        """
        return parent.text

    def format_header(self, post: RSSForumPost, publish_time_str: str) -> str:
        """Format post header line in plain text.

        Args:
            post: The RSS forum post.
            publish_time_str: Formatted publish time string.

        Returns:
            Plain text formatted header line.
        """
        if post.title:
            return f"💬 {post.title} - 👤 {post.author_name} - 🕐 {publish_time_str}"
        return f"👤 {post.author_name} - 🕐 {publish_time_str}"

    def format_link(self, post: RSSForumPost) -> str:
        """Format post link line in plain text.

        Args:
            post: The RSS forum post.

        Returns:
            Plain text formatted link line.
        """
        return f"🔗 {post.link}"

    def format_post_section(
        self,
        post: RSSForumPost,
        content: str,
        header_line: str,
        parents_line: str,
        link_line: str,
    ) -> str:
        """Format a complete post section in plain text.

        Args:
            post: The RSS forum post.
            content: Formatted content.
            header_line: Formatted header line.
            parents_line: Formatted parents line.
            link_line: Formatted link line.

        Returns:
            Complete plain text formatted post section.
        """
        return f"{link_line}\n{header_line}\n{content}\n{parents_line}"


class FTMLFormatter(NotificationFormatter):
    """Formatter for Wikidot FTML format notifications."""

    separator: str = "\n\n------\n\n"
    footer: str = (
        f'[[image {LOGO_URL} style="height:1em"]] '
        "//Powered by [*https://github.com/Crimone/Scoparia Scoparia]//"
    )

    def format_time(self, post: RSSForumPost, timezone: str) -> str:
        """Format post publish time in FTML format (Unix timestamp).

        Args:
            post: The RSS forum post.
            timezone: User's timezone (not used, FTML uses Unix timestamp).

        Returns:
            FTML formatted time string.
        """
        timestamp = int(post.publish_time.timestamp())
        return f'[[date {timestamp} format="%e %b %Y, %H:%M:%S|agohover"]]'

    def format_content(self, html_content: str) -> str:
        """Format post content from HTML to FTML (markdown-like).

        Args:
            html_content: HTML content to format.

        Returns:
            FTML formatted content (markdown-like with blockquote).
        """
        h = html2text.HTML2Text()
        h.ignore_links = True
        h.body_width = 0  # Don't wrap lines
        content = h.handle(html_content).strip()
        return "\n".join([f"> {line}" for line in content.split("\n")])

    def format_parent_link(self, parent: Link) -> str:
        """Format a parent link in FTML.

        Args:
            parent: The parent link to format.

        Returns:
            FTML formatted parent link.
        """
        return f"[*{parent.url} {parent.text}]"

    def format_header(self, post: RSSForumPost, publish_time_str: str) -> str:
        """Format post header line in FTML.

        Args:
            post: The RSS forum post.
            publish_time_str: Formatted publish time string (FTML format).

        Returns:
            FTML formatted header line.
        """
        if post.title:
            return (
                f"💬 **{post.title}** - "
                f"[[*user {post.author_name}]] - "
                f"🕐 {publish_time_str}"
            )
        return f"[[*user {post.author_name}]] - 🕐 {publish_time_str}"

    def format_link(self, post: RSSForumPost) -> str:
        """Format post link line in FTML.

        Args:
            post: The RSS forum post.

        Returns:
            FTML formatted link line.
        """
        return f"🔗 {post.link}"

    def format_post_section(
        self,
        post: RSSForumPost,
        content: str,
        header_line: str,
        parents_line: str,
        link_line: str,
    ) -> str:
        """Format a complete post section in FTML.

        Args:
            post: The RSS forum post.
            content: Formatted content.
            header_line: Formatted header line.
            parents_line: Formatted parents line.
            link_line: Formatted link line.

        Returns:
            Complete FTML formatted post section.
        """
        return f"""
{link_line}

{header_line}

{content}

{parents_line}
"""


class QQPushFormatter(TextFormatter):
    """Formatter for QQ Push format notifications (plain text without links).

    Inherits from TextFormatter and customizes footer, link handling,
    and post-processing.
    """

    footer: str = "⚡ Powered by Scoparia"

    def format_link(self, post: RSSForumPost) -> str:
        """Format post link line for QQ Push (omitted).

        Args:
            post: The RSS forum post.

        Returns:
            Empty string (links are omitted in QQ Push).
        """
        return ""

    def format_post_section(
        self,
        post: RSSForumPost,
        content: str,
        header_line: str,
        parents_line: str,
        link_line: str,
    ) -> str:
        """Format a complete post section for QQ Push.

        Args:
            post: The RSS forum post.
            content: Formatted content.
            header_line: Formatted header line.
            parents_line: Formatted parents line.
            link_line: Formatted link line (ignored for QQ Push).

        Returns:
            Complete QQ Push formatted post section.
        """
        return f"{header_line}\n{content}\n{parents_line}"

    def post_process_body(self, body: str) -> str:
        """Post-process the final body text for QQ Push (remove links and long numbers).

        Args:
            body: The final body text.

        Returns:
            Post-processed body text with links and long numbers removed.
        """
        # Remove any remaining links from the final body
        body = re.sub(r"https?://[^\s]+", "", body)
        body = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", body)
        # Remove all numbers with length 5 or more
        body = re.sub(r"\d{5,}", "", body)
        return body


def generate_formatter(format_type: str) -> NotificationFormatter:
    """Generate a formatter instance based on the format type.

    Args:
        format_type: The format type string (e.g., 'html', 'markdown', 'text').

    Returns:
        An instance of the appropriate NotificationFormatter subclass.

    Raises:
        ValueError: If the format type is not supported.
    """
    if format_type == "html":
        return HTMLFormatter()
    elif format_type == "markdown":
        return MarkdownFormatter()
    elif format_type == "text":
        return TextFormatter()
    elif format_type == "qqpush":
        return QQPushFormatter()
    elif format_type == "ftml":
        return FTMLFormatter()
    else:
        raise ValueError(f"Unsupported format type: {format_type}")
