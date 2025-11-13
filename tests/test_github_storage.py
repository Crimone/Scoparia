"""Tests for Scoparia GitHub storage module."""

import base64
import os
import tempfile
from unittest.mock import patch

from scoparia.emailer import GitHubActionTokenBackend
from scoparia.github_storage import set_github_variable


class TestSetGitHubVariable:
    """Test set_github_variable function."""

    def test_set_github_variable_success(self) -> None:
        """Test successfully setting a GitHub variable."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_file:
            github_env_path = tmp_file.name

        try:
            with patch.dict(os.environ, {"GITHUB_ENV": github_env_path}):
                set_github_variable("TEST_VAR", "test_value")

                # Verify the variable was written
                with open(github_env_path) as f:
                    content = f.read()
                    assert "TEST_VAR=" in content
                    assert "test_value" in content
        finally:
            # Clean up
            if os.path.exists(github_env_path):
                os.unlink(github_env_path)

    def test_set_github_variable_json_string(self) -> None:
        """Test setting a GitHub variable with a JSON string value."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_file:
            github_env_path = tmp_file.name

        try:
            with patch.dict(os.environ, {"GITHUB_ENV": github_env_path}):
                json_value = (
                    '{"site1": "2023-01-01T00:00:00Z", "site2": "2023-01-02T00:00:00Z"}'
                )
                set_github_variable("LAST_RSS_CHECK", json_value)

                # Verify the variable was written
                with open(github_env_path) as f:
                    content = f.read()
                    assert "LAST_RSS_CHECK=" in content
                    assert "site1" in content
                    assert "site2" in content
        finally:
            # Clean up
            if os.path.exists(github_env_path):
                os.unlink(github_env_path)

    def test_set_github_variable_no_github_env(self) -> None:
        """Test that missing GITHUB_ENV doesn't raise an error."""
        with patch.dict(os.environ, {}, clear=True):
            # Should not raise an error, just log a warning
            set_github_variable("TEST_VAR", "test_value")

    def test_set_github_variable_json_array_string(self) -> None:
        """Test setting a GitHub variable with a JSON array string."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_file:
            github_env_path = tmp_file.name

        try:
            with patch.dict(os.environ, {"GITHUB_ENV": github_env_path}):
                json_array = (
                    '["https://site1.wikidot.com", "https://site2.wikidot.com"]'
                )
                set_github_variable("RSS_SITE_URLS", json_array)

                # Verify the variable was written
                with open(github_env_path) as f:
                    content = f.read()
                    assert "RSS_SITE_URLS=" in content
                    assert "site1" in content
                    assert "site2" in content
        finally:
            # Clean up
            if os.path.exists(github_env_path):
                os.unlink(github_env_path)

    def test_set_github_variable_multiple_calls(self) -> None:
        """Test setting multiple GitHub variables."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_file:
            github_env_path = tmp_file.name

        try:
            with patch.dict(os.environ, {"GITHUB_ENV": github_env_path}):
                set_github_variable("VAR1", "value1")
                set_github_variable("VAR2", "value2")

                # Verify both variables were written
                with open(github_env_path) as f:
                    content = f.read()
                    assert "VAR1=" in content
                    assert "VAR2=" in content
                    assert "value1" in content
                    assert "value2" in content
        finally:
            # Clean up
            if os.path.exists(github_env_path):
                os.unlink(github_env_path)

    def test_set_github_variable_base64_string(self) -> None:
        """Test setting a GitHub variable with a base64 encoded string."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_file:
            github_env_path = tmp_file.name

        try:
            with patch.dict(os.environ, {"GITHUB_ENV": github_env_path}):
                # Simulate a base64 encoded token
                token_data = b'{"access_token": "test_token", "expires_in": 3600}'
                base64_token = base64.b64encode(token_data).decode("utf-8")
                set_github_variable("O365_TOKEN", base64_token)

                # Verify the variable was written
                with open(github_env_path) as f:
                    content = f.read()
                    assert "O365_TOKEN=" in content
                    assert base64_token in content
        finally:
            # Clean up
            if os.path.exists(github_env_path):
                os.unlink(github_env_path)


class TestGitHubActionTokenBackend:
    """Test GitHubActionTokenBackend class."""

    def test_save_token_success(self) -> None:
        """Test successfully saving a token."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_file:
            github_env_path = tmp_file.name

        try:
            with patch.dict(os.environ, {"GITHUB_ENV": github_env_path}):
                backend = GitHubActionTokenBackend(token_env_name="TEST_TOKEN")

                # Mock the cache and serialize method
                backend._cache = {"access_token": "test_token", "expires_in": 3600}
                backend._has_state_changed = True

                # Mock serialize to return bytes (simulating MSAL behavior)
                with patch.object(backend, "serialize") as mock_serialize:
                    mock_serialize.return_value = b'{"access_token": "test_token"}'

                    result = backend.save_token()

                    assert result is True
                    # Check that token was set in environment
                    assert "TEST_TOKEN" in os.environ
                    # Check that token was written to GitHub environment file
                    with open(github_env_path) as f:
                        content = f.read()
                        assert "TEST_TOKEN=" in content
        finally:
            # Clean up
            if os.path.exists(github_env_path):
                os.unlink(github_env_path)

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

    def test_save_token_string_serialize(self) -> None:
        """Test save_token when serialize returns string."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_file:
            github_env_path = tmp_file.name

        try:
            with patch.dict(os.environ, {"GITHUB_ENV": github_env_path}):
                backend = GitHubActionTokenBackend(token_env_name="TEST_TOKEN")
                backend._cache = {"access_token": "test_token"}
                backend._has_state_changed = True

                # Mock serialize to return string
                with patch.object(backend, "serialize") as mock_serialize:
                    mock_serialize.return_value = '{"access_token": "test_token"}'

                    result = backend.save_token()

                    assert result is True
                    assert "TEST_TOKEN" in os.environ
                    assert os.environ["TEST_TOKEN"] == '{"access_token": "test_token"}'
        finally:
            # Clean up
            if os.path.exists(github_env_path):
                os.unlink(github_env_path)
