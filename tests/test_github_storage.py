"""Tests for Scoparia GitHub storage module."""

import pytest

from scoparia.emailer import GitHubActionTokenBackend
from scoparia.github_storage import set_github_variable


class TestSetGitHubVariable:
    """Test set_github_variable function."""

    @pytest.mark.asyncio
    async def test_set_github_variable_no_repo(self) -> None:
        """Test that missing REPO doesn't raise an error, just logs warning."""
        # Should not raise an error, just log a warning
        await set_github_variable("TEST_VAR", "test_value")


class TestGitHubActionTokenBackend:
    """Test GitHubActionTokenBackend class."""

    def test_save_token_no_cache(self) -> None:
        """Test save_token returns False when no cache."""
        backend = GitHubActionTokenBackend(token_env_name="TEST_TOKEN")
        backend._cache = {}  # Empty dict instead of None

        result = backend.save_token()
        assert result is False

    def test_save_token_no_state_change(self) -> None:
        """Test save_token returns True when no state change and not forced."""
        backend = GitHubActionTokenBackend(token_env_name="TEST_TOKEN")
        backend._cache = {"access_token": "test_token"}
        backend._has_state_changed = False

        result = backend.save_token(force=False)
        assert result is True
