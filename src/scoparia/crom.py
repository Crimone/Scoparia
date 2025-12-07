"""CROM API client for fetching page author information."""

import base64

import aiohttp
import msgspec
from aiohttp.client_exceptions import ClientResponseError
from tenacity import RetryCallState, retry, retry_if_exception_type, stop_after_attempt

from . import logger

CROM_API_URL = "https://apiv2.crom.avn.sh/graphql"


def _wait_with_retry_after(retry_state: RetryCallState) -> float:
    """Custom wait function that respects Retry-After header.

    Falls back to exponential backoff if no Retry-After is available.
    """
    exc = retry_state.outcome.exception() if retry_state.outcome else None

    # Check Retry-After header from ClientResponseError (429 rate limiting)
    if isinstance(exc, ClientResponseError) and exc.status == 429:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        if retry_after:
            try:
                wait_time = float(retry_after)
                logger.info("Rate limited, respecting Retry-After: %ss", wait_time)
                return wait_time
            except ValueError:
                logger.warning(
                    "Retry-After header contains date format: %s", retry_after
                )

    # Exponential backoff: 0.4 * 2^attempt, max 60s
    attempt = retry_state.attempt_number
    return min(0.4 * (2**attempt), 60)


@retry(
    stop=stop_after_attempt(10),
    wait=_wait_with_retry_after,
    retry=retry_if_exception_type((TimeoutError, ClientResponseError)),
    reraise=True,
)
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

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
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
