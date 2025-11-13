"""Tests for Scoparia emailer module."""

import os
from unittest.mock import MagicMock, patch

import pytest

from scoparia.emailer import _get_account, send_email


class TestGetAccount:
    """Test _get_account function."""

    def test_get_account_missing_credentials(self) -> None:
        """Test that missing credentials raise ValueError."""
        with (
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(ValueError, match="O365_CLIENT_ID and O365_CLIENT_SECRET"),
        ):
            _get_account()

    def test_get_account_missing_client_id(self) -> None:
        """Test that missing O365_CLIENT_ID raises ValueError."""
        with (
            patch.dict(os.environ, {"O365_CLIENT_SECRET": "secret"}, clear=True),
            pytest.raises(ValueError, match="O365_CLIENT_ID and O365_CLIENT_SECRET"),
        ):
            _get_account()

    def test_get_account_missing_client_secret(self) -> None:
        """Test that missing O365_CLIENT_SECRET raises ValueError."""
        with (
            patch.dict(os.environ, {"O365_CLIENT_ID": "client_id"}, clear=True),
            pytest.raises(ValueError, match="O365_CLIENT_ID and O365_CLIENT_SECRET"),
        ):
            _get_account()

    @patch("scoparia.emailer.Account")
    @patch("scoparia.emailer.EnvTokenBackend")
    @patch("scoparia.emailer.MSGraphProtocol")
    @patch("scoparia.emailer._CLIENT_ID", "client_id")
    @patch("scoparia.emailer._CLIENT_SECRET", "client_secret")
    def test_get_account_success(
        self,
        mock_protocol: MagicMock,
        mock_token_backend: MagicMock,
        mock_account: MagicMock,
    ) -> None:
        """Test successful account creation."""
        with patch.dict(
            os.environ,
            {
                "O365_TOKEN": "token",
            },
        ):
            # Mock account instance
            mock_account_instance = MagicMock()
            mock_account_instance.is_authenticated = True
            mock_account.return_value = mock_account_instance

            # Mock protocol
            mock_protocol_instance = MagicMock()
            mock_protocol_instance.get_scopes_for.return_value = ["message_send"]
            mock_protocol.return_value = mock_protocol_instance

            # Mock token backend
            mock_token_backend_instance = MagicMock()
            mock_token_backend.return_value = mock_token_backend_instance

            result = _get_account()

            assert result == mock_account_instance
            mock_account.assert_called_once()

    @patch("scoparia.emailer.Account")
    @patch("scoparia.emailer.EnvTokenBackend")
    @patch("scoparia.emailer.MSGraphProtocol")
    @patch("scoparia.emailer._CLIENT_ID", "client_id")
    @patch("scoparia.emailer._CLIENT_SECRET", "client_secret")
    @patch("scoparia.emailer._account", None)  # Reset global account
    def test_get_account_authentication_failure(
        self,
        mock_protocol: MagicMock,
        mock_token_backend: MagicMock,
        mock_account: MagicMock,
    ) -> None:
        """Test that authentication failure raises RuntimeError."""
        with patch.dict(
            os.environ,
            {
                "O365_TOKEN": "token",
            },
        ):
            # Mock account instance that fails authentication
            mock_account_instance = MagicMock()
            mock_account_instance.is_authenticated = False
            mock_account_instance.authenticate.return_value = False
            mock_account.return_value = mock_account_instance

            # Mock protocol
            mock_protocol_instance = MagicMock()
            mock_protocol_instance.get_scopes_for.return_value = ["message_send"]
            mock_protocol.return_value = mock_protocol_instance

            # Mock token backend
            mock_token_backend_instance = MagicMock()
            mock_token_backend.return_value = mock_token_backend_instance

            with pytest.raises(RuntimeError, match="O365 authentication failed"):
                _get_account()


class TestSendEmail:
    """Test send_email function."""

    @patch("scoparia.emailer._get_account")
    def test_send_email_success(self, mock_get_account: MagicMock) -> None:
        """Test successfully sending an email."""
        # Mock account and mailbox
        mock_message = MagicMock()
        mock_message.send.return_value = True

        mock_mailbox = MagicMock()
        mock_mailbox.new_message.return_value = mock_message

        mock_account = MagicMock()
        mock_account.mailbox.return_value = mock_mailbox
        mock_get_account.return_value = mock_account

        result = send_email(
            title="Test Subject",
            body="Test Body",
            to_email="test@example.com",
        )

        assert result is True
        mock_message.to.add.assert_called_once_with("test@example.com")
        assert mock_message.subject == "Test Subject"
        assert mock_message.body == "Test Body"
        mock_message.send.assert_called_once()

    @patch("scoparia.emailer._get_account")
    def test_send_email_failure(self, mock_get_account: MagicMock) -> None:
        """Test email sending failure."""
        # Mock account and mailbox
        mock_message = MagicMock()
        mock_message.send.return_value = False

        mock_mailbox = MagicMock()
        mock_mailbox.new_message.return_value = mock_message

        mock_account = MagicMock()
        mock_account.mailbox.return_value = mock_mailbox
        mock_get_account.return_value = mock_account

        result = send_email(
            title="Test Subject",
            body="Test Body",
            to_email="test@example.com",
        )

        assert result is False

    @patch("scoparia.emailer._get_account")
    def test_send_email_none_return(self, mock_get_account: MagicMock) -> None:
        """Test email sending when send() returns None."""
        # Mock account and mailbox
        mock_message = MagicMock()
        mock_message.send.return_value = None

        mock_mailbox = MagicMock()
        mock_mailbox.new_message.return_value = mock_message

        mock_account = MagicMock()
        mock_account.mailbox.return_value = mock_mailbox
        mock_get_account.return_value = mock_account

        result = send_email(
            title="Test Subject",
            body="Test Body",
            to_email="test@example.com",
        )

        assert result is False

    @patch("scoparia.emailer._get_account")
    def test_send_email_exception(self, mock_get_account: MagicMock) -> None:
        """Test that email sending exceptions are handled."""
        # Mock account that raises exception
        mock_account = MagicMock()
        mock_account.mailbox.side_effect = Exception("Connection error")
        mock_get_account.return_value = mock_account

        with pytest.raises(RuntimeError, match="Failed to send email"):
            send_email(
                title="Test Subject",
                body="Test Body",
                to_email="test@example.com",
            )
