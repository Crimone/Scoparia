"""Email sending functionality."""

import base64
import os

from O365 import Account, EnvTokenBackend, MSGraphProtocol

from .github_storage import set_github_variable


class GitHubActionTokenBackend(EnvTokenBackend):
    """A token backend that saves tokens to GitHub Actions environment variables.

    This backend extends EnvTokenBackend to automatically persist token updates
    to GitHub Actions environment variables using set_github_variable.
    """

    def save_token(self, force: bool = False) -> bool:
        """Save the token and update GitHub Actions environment variable.

        Args:
            force: Force save even when state has not changed.

        Returns:
            True if token was saved successfully, False otherwise.
        """
        if not self._cache:
            return False

        if force is False and self._has_state_changed is False:
            return True

        token_str = self.serialize()

        if isinstance(token_str, bytes):
            token_str = base64.b64encode(token_str).decode("utf-8")

        os.environ[self.token_env_name] = token_str

        set_github_variable(self.token_env_name, token_str)

        return True


def _mask_email(email: str) -> str:
    """Mask email address for logging, keeping first 3 chars and @domain part.

    Args:
        email: Email address to mask.

    Returns:
        Masked email address.

    Example:
        >>> _mask_email("user@example.com")
        "use***@example.com"
        >>> _mask_email("ab@test.com")
        "ab***@test.com"
    """
    if "@" not in email:
        return "***"

    local, domain = email.split("@", 1)
    if len(local) <= 3:
        return f"{local}***@{domain}"
    else:
        return f"{local[:3]}***@{domain}"


# O365 credentials from environment variables
_CLIENT_ID = os.getenv("O365_CLIENT_ID")
_CLIENT_SECRET = os.getenv("O365_CLIENT_SECRET")

# Global account instance (cached to avoid re-authentication)
_account: Account | None = None


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
    # Refreshed tokens are written to env var and persisted to GitHub Actions
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
        # Re-raise with more context using masked email address
        raise RuntimeError(
            f"Failed to send email to {_mask_email(to_email)}: {e}"
        ) from e
