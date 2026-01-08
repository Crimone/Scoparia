"""GitHub Variables storage module for no-database mode.

This module provides functionality to store metadata using
GitHub Variables when running in GitHub Actions without a database.
"""

import base64
import os

from githubkit import GitHub
from githubkit.exception import RequestError, RequestFailed
from nacl import encoding, public
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from . import logger

GH_TOKEN = os.getenv("GH_TOKEN")
REPO = os.getenv("REPO")


def _encrypt_secret(public_key: str, secret_value: str) -> str:
    """Encrypt a secret using the repository's public key.

    Args:
        public_key: The repository's public key (base64 encoded).
        secret_value: The secret value to encrypt.

    Returns:
        The encrypted secret value (base64 encoded).
    """
    public_key_obj = public.PublicKey(
        public_key.encode("utf-8"), encoding.Base64Encoder
    )
    sealed_box = public.SealedBox(public_key_obj)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


@retry(
    stop=stop_after_attempt(10),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type(RequestError),
    reraise=True,
)
async def set_github_variable(variable_name: str, value: str) -> None:
    """Set a GitHub repository variable using GitHub Actions Variables API.

    This function uses the GitHub REST API to create or update a repository
    variable. It requires GH_TOKEN, REPO environment variables to be set.

    Args:
        variable_name: The name of the GitHub variable to set.
        value: The string value to set.

    Raises:
        RuntimeError: If required environment variables are missing or API call fails.
    """
    if not REPO:
        logger.warning(
            "REPO not set, cannot persist %s. This is expected when running locally.",
            variable_name,
        )
        return

    # Parse owner and repo from REPO (format: "owner/repo")
    try:
        owner, repo = REPO.split("/", 1)
    except ValueError:
        logger.error("Invalid REPO format: %s", REPO)
        raise RuntimeError(f"Invalid REPO format: {REPO}") from None

    # Initialize GitHub client with token
    async with GitHub(GH_TOKEN) as github:
        try:
            await github.rest.actions.async_update_repo_variable(
                owner=owner,
                repo=repo,
                name=variable_name,
                data={"name": variable_name, "value": value},
            )
            logger.info(
                "Updated GitHub variable %s in repository %s/%s",
                variable_name,
                owner,
                repo,
            )
        except RequestFailed as e:
            logger.error("Failed to update GitHub variable %s: %s", variable_name, e)
            raise RuntimeError(
                f"Failed to update GitHub variable {variable_name}: {e}"
            ) from e


@retry(
    stop=stop_after_attempt(10),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type(RequestError),
    reraise=True,
)
async def set_github_secret(secret_name: str, value: str) -> None:
    """Set a GitHub repository secret using GitHub Actions Secrets API.

    This function uses the GitHub REST API to create or update a repository
    secret. It requires GH_TOKEN, REPO environment variables to be set.

    Args:
        secret_name: The name of the GitHub secret to set.
        value: The string value to set.

    Raises:
        RuntimeError: If required environment variables are missing or API call fails.
    """
    if not REPO:
        logger.warning(
            "REPO not set, cannot persist %s. This is expected when running locally.",
            secret_name,
        )
        return

    # Parse owner and repo from REPO (format: "owner/repo")
    try:
        owner, repo = REPO.split("/", 1)
    except ValueError:
        logger.error("Invalid REPO format: %s", REPO)
        raise RuntimeError(f"Invalid REPO format: {REPO}") from None

    # Initialize GitHub client with token
    async with GitHub(GH_TOKEN) as github:
        try:
            # Get the repository's public key
            public_key_response = await github.rest.actions.async_get_repo_public_key(
                owner=owner,
                repo=repo,
            )
            public_key = public_key_response.parsed_data.key
            key_id = public_key_response.parsed_data.key_id

            # Encrypt the secret value
            encrypted_value = _encrypt_secret(public_key, value)

            # Update the secret
            await github.rest.actions.async_create_or_update_repo_secret(
                owner=owner,
                repo=repo,
                secret_name=secret_name,
                data={
                    "encrypted_value": encrypted_value,
                    "key_id": key_id,
                },
            )
            logger.info(
                "Updated GitHub secret %s in repository %s/%s",
                secret_name,
                owner,
                repo,
            )
        except RequestFailed as e:
            logger.error("Failed to update GitHub secret %s: %s", secret_name, e)
            raise RuntimeError(
                f"Failed to update GitHub secret {secret_name}: {e}"
            ) from e
