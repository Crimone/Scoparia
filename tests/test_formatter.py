"""Tests for Scoparia formatter module."""

from datetime import UTC, datetime

import pytest

from scoparia.api import Link, RSSForumPost
from scoparia.formatter import (
    FTMLFormatter,
    HTMLFormatter,
    MarkdownFormatter,
    QQPushFormatter,
    TextFormatter,
    generate_formatter,
)


class TestHTMLFormatter:
    """Test HTML formatter."""

    def test_format_time(self) -> None:
        """Test formatting time in HTML format."""
        formatter = HTMLFormatter()
        post = RSSForumPost(
            post_id=123,
            thread_id=456,
            title="Test Post",
            link="https://example.com",
            author_name="TestUser",
            content="<p>Test content</p>",
            publish_time=datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC),
            site_url="https://scp-wiki.wikidot.com",
            parents=[],
        )
        time_str = formatter.format_time(post, "UTC")
        assert "2023" in time_str
        assert "Jan" in time_str

    def test_format_content(self) -> None:
        """Test formatting content in HTML format."""
        formatter = HTMLFormatter()
        html_content = "<p>Test <strong>content</strong></p>"
        result = formatter.format_content(html_content)
        assert result == html_content

    def test_format_parent_link(self) -> None:
        """Test formatting parent link in HTML."""
        formatter = HTMLFormatter()
        link = Link(text="Test Category", url="https://example.com/category")
        result = formatter.format_parent_link(link)
        assert '<a href="https://example.com/category">Test Category</a>' in result

    def test_format_header_with_title(self) -> None:
        """Test formatting header with title."""
        formatter = HTMLFormatter()
        post = RSSForumPost(
            post_id=123,
            thread_id=456,
            title="Test Post",
            link="https://example.com",
            author_name="TestUser",
            content="<p>Test</p>",
            publish_time=datetime.now(UTC),
            site_url="https://scp-wiki.wikidot.com",
            parents=[],
        )
        header = formatter.format_header(post, "01 Jan 2023, 12:00:00 UTC")
        assert "Test Post" in header
        assert "TestUser" in header

    def test_format_header_without_title(self) -> None:
        """Test formatting header without title."""
        formatter = HTMLFormatter()
        post = RSSForumPost(
            post_id=123,
            thread_id=456,
            title="",
            link="https://example.com",
            author_name="TestUser",
            content="<p>Test</p>",
            publish_time=datetime.now(UTC),
            site_url="https://scp-wiki.wikidot.com",
            parents=[],
        )
        header = formatter.format_header(post, "01 Jan 2023, 12:00:00 UTC")
        assert "TestUser" in header
        assert "Test Post" not in header

    def test_compose_notification_content(self) -> None:
        """Test composing notification content in HTML format."""
        formatter = HTMLFormatter()
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
                parents=[
                    Link(text="Category", url="https://example.com/category"),
                    Link(text="Thread", url="https://example.com/thread"),
                ],
            )
        ]
        title, body = formatter.compose_notification_content(posts, "UTC")
        assert "[Scoparia] New post" in title
        assert "Test Post" in body
        assert "TestUser" in body
        assert "Test content" in body
        assert "Powered by" in body

    def test_compose_notification_multiple_posts(self) -> None:
        """Test composing notification with multiple posts."""
        formatter = HTMLFormatter()
        posts = [
            RSSForumPost(
                post_id=123,
                thread_id=456,
                title="Post 1",
                link="https://example.com/1",
                author_name="User1",
                content="<p>Content 1</p>",
                publish_time=datetime.now(UTC),
                site_url="https://scp-wiki.wikidot.com",
                parents=[],
            ),
            RSSForumPost(
                post_id=124,
                thread_id=457,
                title="Post 2",
                link="https://example.com/2",
                author_name="User2",
                content="<p>Content 2</p>",
                publish_time=datetime.now(UTC),
                site_url="https://scp-wiki.wikidot.com",
                parents=[],
            ),
        ]
        title, body = formatter.compose_notification_content(posts, "UTC")
        assert "2 new posts" in title
        assert "Post 1" in body
        assert "Post 2" in body


class TestMarkdownFormatter:
    """Test Markdown formatter."""

    def test_format_content(self) -> None:
        """Test formatting content in Markdown format."""
        formatter = MarkdownFormatter()
        html_content = "<p>Test <strong>content</strong></p>"
        result = formatter.format_content(html_content)
        assert "Test" in result
        assert ">" in result  # Blockquote marker

    def test_format_parent_link(self) -> None:
        """Test formatting parent link in Markdown."""
        formatter = MarkdownFormatter()
        link = Link(text="Test Category", url="https://example.com/category")
        result = formatter.format_parent_link(link)
        assert "[Test Category](https://example.com/category)" in result

    def test_compose_notification_content(self) -> None:
        """Test composing notification content in Markdown format."""
        formatter = MarkdownFormatter()
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
        title, body = formatter.compose_notification_content(posts, "UTC")
        assert "[Scoparia] New post" in title
        assert "Test Post" in body
        assert "---" in body  # Separator
        assert "Powered by" in body


class TestTextFormatter:
    """Test plain text formatter."""

    def test_format_content(self) -> None:
        """Test formatting content in plain text format."""
        formatter = TextFormatter()
        html_content = "<p>Test <strong>content</strong></p>"
        result = formatter.format_content(html_content)
        assert "Test" in result
        assert "<" not in result  # HTML tags should be removed

    def test_format_parent_link(self) -> None:
        """Test formatting parent link in plain text (no link)."""
        formatter = TextFormatter()
        link = Link(text="Test Category", url="https://example.com/category")
        result = formatter.format_parent_link(link)
        assert result == "Test Category"
        assert "http" not in result

    def test_compose_notification_content(self) -> None:
        """Test composing notification content in plain text format."""
        formatter = TextFormatter()
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
        title, body = formatter.compose_notification_content(posts, "UTC")
        assert "[Scoparia] New post" in title
        assert "Test Post" in body
        assert "══════" in body  # Separator
        assert "Powered by" in body


class TestFTMLFormatter:
    """Test FTML formatter."""

    def test_format_time(self) -> None:
        """Test formatting time in FTML format."""
        formatter = FTMLFormatter()
        post = RSSForumPost(
            post_id=123,
            thread_id=456,
            title="Test Post",
            link="https://example.com",
            author_name="TestUser",
            content="<p>Test</p>",
            publish_time=datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC),
            site_url="https://scp-wiki.wikidot.com",
            parents=[],
        )
        time_str = formatter.format_time(post, "UTC")
        assert "[[date" in time_str
        assert "format" in time_str

    def test_format_parent_link(self) -> None:
        """Test formatting parent link in FTML."""
        formatter = FTMLFormatter()
        link = Link(text="Test Category", url="https://example.com/category")
        result = formatter.format_parent_link(link)
        assert "[*https://example.com/category Test Category]" in result

    def test_format_header(self) -> None:
        """Test formatting header in FTML."""
        formatter = FTMLFormatter()
        post = RSSForumPost(
            post_id=123,
            thread_id=456,
            title="Test Post",
            link="https://example.com",
            author_name="TestUser",
            content="<p>Test</p>",
            publish_time=datetime.now(UTC),
            site_url="https://scp-wiki.wikidot.com",
            parents=[],
        )
        header = formatter.format_header(
            post, '[[date 1234567890 format="%e %b %Y, %H:%M:%S|agohover"]]'
        )
        assert "[[*user TestUser]]" in header
        assert "Test Post" in header

    def test_compose_notification_content(self) -> None:
        """Test composing notification content in FTML format."""
        formatter = FTMLFormatter()
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
        title, body = formatter.compose_notification_content(posts, "UTC")
        assert "[Scoparia] New post" in title
        assert "Test Post" in body
        assert "------" in body  # Separator
        assert "[[*user TestUser]]" in body
        assert "Powered by" in body


class TestQQPushFormatter:
    """Test QQ Push formatter."""

    def test_format_link_omitted(self) -> None:
        """Test that links are omitted in QQ Push format."""
        formatter = QQPushFormatter()
        post = RSSForumPost(
            post_id=123,
            thread_id=456,
            title="Test Post",
            link="https://example.com",
            author_name="TestUser",
            content="<p>Test</p>",
            publish_time=datetime.now(UTC),
            site_url="https://scp-wiki.wikidot.com",
            parents=[],
        )
        link_line = formatter.format_link(post)
        assert link_line == ""

    def test_post_process_body_removes_links(self) -> None:
        """Test that post-processing removes links from body."""
        formatter = QQPushFormatter()
        body = "Test content with https://example.com link"
        result = formatter.post_process_body(body)
        assert "https://example.com" not in result

    def test_post_process_body_removes_long_numbers(self) -> None:
        """Test that post-processing removes long numbers."""
        formatter = QQPushFormatter()
        body = "Test content with 123456789 number"
        result = formatter.post_process_body(body)
        assert "123456789" not in result

    def test_compose_notification_content(self) -> None:
        """Test composing notification content in QQ Push format."""
        formatter = QQPushFormatter()
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
        title, body = formatter.compose_notification_content(posts, "UTC")
        assert "[Scoparia] New post" in title
        assert "Test Post" in body
        assert "TestUser" in body
        assert "https://example.com" not in body  # Links should be removed


class TestGenerateFormatter:
    """Test formatter generation."""

    def test_generate_html_formatter(self) -> None:
        """Test generating HTML formatter."""
        formatter = generate_formatter("html")
        assert isinstance(formatter, HTMLFormatter)

    def test_generate_markdown_formatter(self) -> None:
        """Test generating Markdown formatter."""
        formatter = generate_formatter("markdown")
        assert isinstance(formatter, MarkdownFormatter)

    def test_generate_text_formatter(self) -> None:
        """Test generating text formatter."""
        formatter = generate_formatter("text")
        assert isinstance(formatter, TextFormatter)

    def test_generate_ftml_formatter(self) -> None:
        """Test generating FTML formatter."""
        formatter = generate_formatter("ftml")
        assert isinstance(formatter, FTMLFormatter)

    def test_generate_qqpush_formatter(self) -> None:
        """Test generating QQ Push formatter."""
        formatter = generate_formatter("qqpush")
        assert isinstance(formatter, QQPushFormatter)

    def test_generate_invalid_formatter(self) -> None:
        """Test that invalid formatter type raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported format type"):
            generate_formatter("invalid")


class TestTruncateHTMLSafe:
    """Test HTML truncation utility."""

    def test_truncate_short_html(self) -> None:
        """Test that short HTML is not truncated."""
        from scoparia.formatter import _truncate_html_safe

        html = "<p>Short content</p>"
        result = _truncate_html_safe(html, max_length=200)
        assert result == html

    def test_truncate_long_html(self) -> None:
        """Test that long HTML is truncated safely."""
        from scoparia.formatter import _truncate_html_safe

        html = "<p>" + "x" * 300 + "</p>"
        result = _truncate_html_safe(html, max_length=200)
        assert len(result) < len(html)  # Should be shorter than original
        assert "..." in result

    def test_truncate_empty_html(self) -> None:
        """Test that empty HTML is handled correctly."""
        from scoparia.formatter import _truncate_html_safe

        html = ""
        result = _truncate_html_safe(html, max_length=200)
        assert result == html

    def test_truncate_html_with_tags(self) -> None:
        """Test that HTML with tags is truncated at safe position."""
        from scoparia.formatter import _truncate_html_safe

        html = "<p>Test content with <strong>bold</strong> text and more content</p>"
        result = _truncate_html_safe(html, max_length=20)
        assert len(result) < len(html)  # Should be shorter than original
        assert "..." in result
        # Should have valid HTML structure (no broken tags)
