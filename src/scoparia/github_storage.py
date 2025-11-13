"""GitHub Variables storage module for no-database mode.

This module provides functionality to store metadata using
GitHub Variables when running in GitHub Actions without a database.
"""

import os

from . import logger


def set_github_variable(variable_name: str, value: str) -> None:
    """Set a GitHub variable to the GitHub environment file.

    In GitHub Actions, this writes to $GITHUB_ENV to update the variable
    for subsequent workflow steps and to persist via GitHub Variables API.

    Args:
        variable_name: The name of the GitHub variable to set.
        value: The string value to set.
    """
    # Get GitHub environment file path
    github_env = os.getenv("GITHUB_ENV")

    if not github_env:
        logger.warning(
            "GITHUB_ENV not set, cannot persist %s. "
            "This is expected when running locally.",
            variable_name,
        )
        return

    try:
        # Append to GitHub environment file
        with open(github_env, "a", encoding="utf-8") as env_file:
            env_file.write(f"{variable_name}={value}\n")
        logger.info("Set %s in GitHub environment", variable_name)
    except OSError as e:
        logger.error("Failed to write to GITHUB_ENV file: %s", e)
        raise
