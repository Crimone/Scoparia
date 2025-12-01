"""Email sending functionality."""

import base64
import os
import re

import msgspec
from O365 import Account, EnvTokenBackend, MSGraphProtocol

from .github_storage import set_github_secret


class GitHubActionTokenBackend(EnvTokenBackend):
    """A token backend that marks tokens for deferred persistence to GitHub secrets.

    This backend extends EnvTokenBackend to save tokens to environment variables
    and mark them for later persistence to GitHub Actions secrets. The actual
    GitHub secret update is deferred until flush_token_to_github() is called.
    """

    def serialize(self) -> bytes | str:
        """Serialize the current cache state into a single-line string."""
        with self._lock:
            self._has_state_changed = False
            token_str = msgspec.json.encode(self._cache).decode("utf-8")
            if self.cryptography_manager is not None:
                token_str = self.cryptography_manager.encrypt(token_str)
            return token_str

    def deserialize(self, token_cache_state: bytes | str) -> dict:
        """Deserialize the cache from a state previously obtained by serialize()"""
        with self._lock:
            self._has_state_changed = False
            if self.cryptography_manager is not None and isinstance(
                token_cache_state, bytes
            ):
                token_cache_state = self.cryptography_manager.decrypt(token_cache_state)
            return msgspec.json.decode(token_cache_state) if token_cache_state else {}

    def save_token(self, force: bool = False) -> bool:
        """Save the token to environment variable and mark for deferred GitHub update.

        The token is immediately saved to the environment variable but only marked
        for later persistence to GitHub secret. Call flush_token_to_github() to
        actually update the GitHub secret.

        Args:
            force: Force save even when state has not changed.

        Returns:
            True if token was saved successfully, False otherwise.
        """
        if not self._cache:
            return False

        if force is False and self._has_state_changed is False:
            return True

        global _token_updated

        token_str = self.serialize()

        if isinstance(token_str, bytes):
            token_str = base64.b64encode(token_str).decode("utf-8")

        os.environ[self.token_env_name] = token_str

        # Mark that token was updated
        _token_updated = True

        return True


def _mask_emails_in_text(text: str) -> str:
    """Mask all email addresses found in a text string.

    Args:
        text: Text that may contain email addresses.

    Returns:
        Text with all email addresses masked.

    Example:
        >>> _mask_emails_in_text("Error for user test@example.com")
        "Error for user tes***@example.com"
    """
    # Pattern to match email addresses with capture groups:
    # Group 1: First 1-3 characters of local part
    # Group 2: Domain part
    email_pattern = (
        r"\b([A-Za-z0-9._%+-]{1,3})[A-Za-z0-9._%+-]*@"
        r"([A-Za-z0-9.-]+\.[A-Z|a-z]{2,})\b"
    )

    # Replace with first 1-3 chars + *** + @ + domain
    return re.sub(email_pattern, r"\1***@\2", text)


# O365 credentials from environment variables
_CLIENT_ID = os.getenv("O365_CLIENT_ID")
_CLIENT_SECRET = os.getenv("O365_CLIENT_SECRET")

# Global account instance (cached to avoid re-authentication)
_account: Account | None = None
# Global flag to track if O365 token was updated
_token_updated = False


def _get_account() -> Account:
    """Get authenticated O365 Account instance.

    Returns:
        Authenticated Account instance.

    Raises:
        RuntimeError: If authentication fails.
    """
    global _account

    if _account is not None and _account.is_authenticated:
        return _account

    if not _CLIENT_ID or not _CLIENT_SECRET:
        raise ValueError(
            "O365_CLIENT_ID and O365_CLIENT_SECRET must be set. "
            "Get these from Microsoft Entra Admin Center."
        )

    # Configure token storage using GitHub Actions environment variable
    # Token is loaded from O365_TOKEN environment variable
    # Refreshed tokens are written to env var and marked for GitHub persistence
    token_backend = GitHubActionTokenBackend(token_env_name="O365_TOKEN")

    credentials = (_CLIENT_ID, _CLIENT_SECRET)

    # Create Account instance with authorization mode (supports personal accounts)
    protocol = MSGraphProtocol()
    scopes = protocol.get_scopes_for(["message_send"])
    _account = Account(
        credentials,
        auth_flow_type="authorization",
        scopes=scopes,
        tenant_id="common",
        token_backend=token_backend,
    )

    # Authenticate if needed
    if not _account.is_authenticated and not _account.authenticate():
        raise RuntimeError(
            "O365 authentication failed. Please check:\n"
            "1. O365_CLIENT_ID and O365_CLIENT_SECRET are correct\n"
            "2. O365_TOKEN environment variable contains valid token\n"
            "3. Token has not expired (update GitHub Secret if needed)"
        )

    return _account


def send_email(title: str, body: str, to_email: str) -> bool:
    """Send an email via Office 365.

    Args:
        title: Email subject/title.
        body: Email body content.
        to_email: Recipient email address.

    Returns:
        True if email was sent successfully, False otherwise.

    Raises:
        RuntimeError: If authentication fails.
        Exception: If there's an error sending the email.

    Example:
        >>> send_email(
        ...     title="Test Email",
        ...     body="This is a test email.",
        ...     to_email="recipient@example.com"
        ... )
        True
    """
    account = _get_account()

    try:
        # For authorization mode (personal accounts), use current user's mailbox
        # No need to specify user resource - uses the authenticated user
        mailbox = account.mailbox()

        # Create message
        message = mailbox.new_message()
        message.to.add(to_email)
        message.subject = title
        message.body = body

        # Send the message
        success = message.send()
        if success is None:
            return False
        return bool(success)

    except Exception as e:
        # Mask both the recipient email and any emails in the exception message
        raise RuntimeError(
            _mask_emails_in_text(f"Failed to send email to {to_email}: {e}")
        ) from None


async def flush_token_to_github() -> None:
    """Flush any pending O365 token updates to GitHub secret.

    This should be called at the end of RSS processing to persist
    any token refreshes that occurred during email sending.
    """
    global _token_updated

    if not _token_updated:
        return

    token_str = os.environ.get("O365_TOKEN")
    if token_str:
        await set_github_secret("O365_TOKEN", token_str)
        _token_updated = False
