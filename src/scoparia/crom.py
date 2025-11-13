"""CROM API client for fetching page author information."""

import base64

import aiohttp
import msgspec
from aiohttp_retry import ExponentialRetry, RetryClient

from . import logger

CROM_API_URL = "https://apiv2.crom.avn.sh/graphql"


class CROMRetryOptions(ExponentialRetry):
    """Custom retry options that respect Retry-After header for rate limiting."""

    def get_timeout(
        self, attempt: int, response: aiohttp.ClientResponse | None = None
    ) -> float:
        """Get timeout for next retry, respecting Retry-After header.

        Args:
            attempt: Current attempt number (1-indexed).
            response: The response object, if available.

        Returns:
            Timeout in seconds before next retry.
        """
        # Check if response has Retry-After header (for 429 rate limiting)
        if response is not None and response.status == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    # Retry-After can be either seconds or HTTP date
                    # Try to parse as integer (seconds) first
                    wait_time = float(retry_after)
                    logger.info(
                        "Rate limited, respecting Retry-After: %ss",
                        wait_time,
                    )
                    return wait_time
                except ValueError:
                    # If not a number, it might be an HTTP date
                    # For simplicity, fall back to exponential backoff
                    logger.warning(
                        "Retry-After header contains date format: %s, "
                        "using exponential backoff instead",
                        retry_after,
                    )

        # Fall back to exponential backoff
        return super().get_timeout(attempt, response)


async def get_page_author_id_from_crom(site_url: str, page_fullname: str) -> int | None:
    """Get page author ID from CROM API.

    Args:
        site_url: The site URL (e.g., "https://scp-wiki-cn.wikidot.com").
        page_fullname: The full name of the page.

    Returns:
        The author's user ID if found, None otherwise.

    Raises:
        aiohttp.ClientError: If the HTTP request fails.
    """
    # Construct the canonical Wikidot URL
    # CROM stores all wikidot URLs as "http://" regardless of HTTPS support
    canonical_url = f"{site_url.replace('https://', 'http://')}/{page_fullname}"

    # GraphQL query to fetch page author using wikidotPage query
    query = """
    query GetPageAuthor($url: URL!) {
        wikidotPage(url: $url) {
            createdBy {
                id
            }
        }
    }
    """

    variables = {"url": canonical_url}

    # Configure retry strategy with exponential backoff and Retry-After support
    retry_options = CROMRetryOptions(
        attempts=10,
        start_timeout=0.4,
        statuses={429, 500, 502, 503, 504},
    )

    try:
        async with aiohttp.ClientSession() as session:
            retry_client = RetryClient(
                client_session=session, retry_options=retry_options
            )
            async with retry_client.post(
                CROM_API_URL,
                json={"query": query, "variables": variables},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                response.raise_for_status()
                response_content = await response.read()

            data = msgspec.json.decode(response_content)

            created_by = data["data"]["wikidotPage"]["createdBy"]
            # Returns null if the account was deleted
            if created_by is None:
                return None
            # Extract author ID from response
            # The id field is Base64-encoded JSON
            # Format: base64({"type":"WikidotUser","id":"8366274"})
            user_id_encoded = created_by["id"]

            # Decode Base64 and parse JSON to extract wikidot ID
            decoded_bytes = base64.b64decode(user_id_encoded)
            user_data = msgspec.json.decode(decoded_bytes)
            wikidot_id = user_data["id"]

            logger.info(
                "Retrieved author ID %s for %s from CROM",
                wikidot_id,
                canonical_url,
            )
            return int(wikidot_id)

    except (
        aiohttp.ClientError,
        aiohttp.ClientResponseError,
        KeyError,
        TypeError,
        ValueError,
    ) as e:
        logger.debug(
            "Failed to fetch page author from CROM for %s: %s",
            canonical_url,
            e,
        )
        raise
    except Exception as e:
        logger.error(
            "Unexpected error fetching page author from CROM for %s: %s",
            canonical_url,
            e,
            exc_info=True,
        )
        raise
