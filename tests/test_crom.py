"""Tests for Scoparia CROM API module."""

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from scoparia.crom import get_page_author_id_from_crom


class TestGetPageAuthorIdFromCrom:
    """Test get_page_author_id_from_crom function."""

    @pytest.mark.asyncio
    async def test_get_page_author_id_success(self) -> None:
        """Test successfully getting page author ID from CROM API."""
        # Mock response data
        # Base64 encoded JSON: {"type":"WikidotUser","id":"1234567"}
        encoded_id = "eyJ0eXBlIjogIldpa2lkb3RVc2VyIiwgImlkIjogIjEyMzQ1NjcifQ=="

        # Mock the response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.read = AsyncMock(
            return_value=f'{{"data":{{"wikidotPage":{{"createdBy":{{"id":"{encoded_id}"}}}}}}}}'.encode()
        )

        # Mock the retry client
        mock_retry_client = AsyncMock()
        mock_retry_client.__aenter__ = AsyncMock(return_value=mock_response)
        mock_retry_client.__aexit__ = AsyncMock(return_value=None)
        mock_retry_client.post = MagicMock(return_value=mock_retry_client)

        with (
            patch("scoparia.crom.RetryClient") as mock_retry_client_class,
            patch("scoparia.crom.aiohttp.ClientSession") as mock_session_class,
        ):
            mock_retry_client_class.return_value = mock_retry_client
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await get_page_author_id_from_crom(
                "https://scp-wiki.wikidot.com", "scp-173"
            )

            assert result == 1234567

    @pytest.mark.asyncio
    async def test_get_page_author_id_deleted_account(self) -> None:
        """Test getting page author ID when account is deleted."""
        # Mock response with null createdBy
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.read = AsyncMock(
            return_value=b'{"data":{"wikidotPage":{"createdBy":null}}}'
        )

        # Mock the retry client
        mock_retry_client = AsyncMock()
        mock_retry_client.__aenter__ = AsyncMock(return_value=mock_response)
        mock_retry_client.__aexit__ = AsyncMock(return_value=None)
        mock_retry_client.post = MagicMock(return_value=mock_retry_client)

        with (
            patch("scoparia.crom.RetryClient") as mock_retry_client_class,
            patch("scoparia.crom.aiohttp.ClientSession") as mock_session_class,
        ):
            mock_retry_client_class.return_value = mock_retry_client
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await get_page_author_id_from_crom(
                "https://scp-wiki.wikidot.com", "scp-173"
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_get_page_author_id_http_client_error(self) -> None:
        """Test handling HTTP client errors."""
        # Mock the retry client to raise ClientError
        mock_retry_client = AsyncMock()
        mock_retry_client.__aenter__ = AsyncMock(
            side_effect=aiohttp.ClientError("Connection error")
        )
        mock_retry_client.__aexit__ = AsyncMock(return_value=None)
        mock_retry_client.post = MagicMock(return_value=mock_retry_client)

        with (
            patch("scoparia.crom.RetryClient") as mock_retry_client_class,
            patch("scoparia.crom.aiohttp.ClientSession") as mock_session_class,
        ):
            mock_retry_client_class.return_value = mock_retry_client
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            with pytest.raises(aiohttp.ClientError):
                await get_page_author_id_from_crom(
                    "https://scp-wiki.wikidot.com", "scp-173"
                )

    @pytest.mark.asyncio
    async def test_get_page_author_id_key_error(self) -> None:
        """Test handling KeyError when response structure is invalid."""
        # Mock response with missing data
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.read = AsyncMock(return_value=b'{"data":{}}')

        # Mock the retry client
        mock_retry_client = AsyncMock()
        mock_retry_client.__aenter__ = AsyncMock(return_value=mock_response)
        mock_retry_client.__aexit__ = AsyncMock(return_value=None)
        mock_retry_client.post = MagicMock(return_value=mock_retry_client)

        with (
            patch("scoparia.crom.RetryClient") as mock_retry_client_class,
            patch("scoparia.crom.aiohttp.ClientSession") as mock_session_class,
        ):
            mock_retry_client_class.return_value = mock_retry_client
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            with pytest.raises((KeyError, TypeError)):
                await get_page_author_id_from_crom(
                    "https://scp-wiki.wikidot.com", "scp-173"
                )

    @pytest.mark.asyncio
    async def test_get_page_author_id_https_to_http(self) -> None:
        """Test that HTTPS URLs are converted to HTTP for CROM API."""
        # Mock response
        # Base64 encoded JSON: {"type":"WikidotUser","id":"1234567"}
        encoded_id = "eyJ0eXBlIjogIldpa2lkb3RVc2VyIiwgImlkIjogIjEyMzQ1NjcifQ=="

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.read = AsyncMock(
            return_value=f'{{"data":{{"wikidotPage":{{"createdBy":{{"id":"{encoded_id}"}}}}}}}}'.encode()
        )

        # Mock the retry client
        mock_retry_client = AsyncMock()
        mock_retry_client.__aenter__ = AsyncMock(return_value=mock_response)
        mock_retry_client.__aexit__ = AsyncMock(return_value=None)
        mock_post_call = MagicMock(return_value=mock_retry_client)
        mock_retry_client.post = mock_post_call

        with (
            patch("scoparia.crom.RetryClient") as mock_retry_client_class,
            patch("scoparia.crom.aiohttp.ClientSession") as mock_session_class,
        ):
            mock_retry_client_class.return_value = mock_retry_client
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            await get_page_author_id_from_crom(
                "https://scp-wiki.wikidot.com", "scp-173"
            )

            # Verify that the URL was converted to HTTP
            call_args = mock_post_call.call_args
            assert call_args is not None
            json_data = call_args[1]["json"]
            variables = json_data["variables"]
            assert "http://scp-wiki.wikidot.com" in variables["url"]
            assert "https://scp-wiki.wikidot.com" not in variables["url"]
