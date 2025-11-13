"""Tests for Scoparia MongoDB module."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scoparia.config import MentionLevel, UserInfo
from scoparia.mongodb import MongoDBClient, get_mongodb, init_mongodb


class TestMongoDBClient:
    """Test MongoDBClient class."""

    @pytest.fixture
    def mock_mongo_client(self) -> AsyncMock:
        """Create a mock MongoDB client."""
        client = AsyncMock()
        client.__getitem__ = MagicMock(return_value=AsyncMock())
        return client

    @pytest.fixture
    def mongodb_client(self, mock_mongo_client: AsyncMock) -> MongoDBClient:
        """Create a MongoDBClient instance with mocked client."""
        with patch("scoparia.mongodb.AsyncMongoClient", return_value=mock_mongo_client):
            client = MongoDBClient("mongodb://localhost:27017")
            client.client = mock_mongo_client
            client.db = mock_mongo_client["db_scoparia"]
            return client

    @pytest.mark.asyncio
    async def test_get_all_users(self, mongodb_client: MongoDBClient) -> None:
        """Test getting all users from database."""
        # Mock user documents
        mock_users = [
            {
                "userid": 123,
                "username": "TestUser",
                "apprise_urls": ["json://localhost"],
                "timezone": "UTC",
                "mention_level": "avatarhover",
                "email": "test@example.com",
                "enable_wikidot_pm": True,
                "enable_email": True,
                "enable_apprise": True,
            },
            {
                "userid": 456,
                "username": "AnotherUser",
                "apprise_urls": [],
                "timezone": "Asia/Shanghai",
                "mention_level": "all",
                "email": None,
                "enable_wikidot_pm": True,
                "enable_email": False,
                "enable_apprise": False,
            },
        ]

        # Create a proper async iterator mock
        class AsyncIterator:
            def __init__(self, items):
                self.items = items
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.items):
                    raise StopAsyncIteration
                item = self.items[self.index]
                self.index += 1
                return item

        mock_cursor = AsyncIterator(mock_users)
        mongodb_client.db["t_users"].find = MagicMock(return_value=mock_cursor)

        users = await mongodb_client.get_all_users()

        assert len(users) == 2
        assert 123 in users
        assert 456 in users
        assert users[123].username == "TestUser"
        assert users[123].mention_level == MentionLevel.AVATARHOVER
        assert users[456].mention_level == MentionLevel.ALL

    @pytest.mark.asyncio
    async def test_get_all_users_defaults(self, mongodb_client: MongoDBClient) -> None:
        """Test getting users with default values."""
        mock_users = [
            {
                "userid": 123,
                "username": "TestUser",
                "apprise_urls": [],
            }
        ]

        # Create a proper async iterator mock
        class AsyncIterator:
            def __init__(self, items):
                self.items = items
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.items):
                    raise StopAsyncIteration
                item = self.items[self.index]
                self.index += 1
                return item

        mock_cursor = AsyncIterator(mock_users)
        mongodb_client.db["t_users"].find = MagicMock(return_value=mock_cursor)

        users = await mongodb_client.get_all_users()

        assert len(users) == 1
        assert users[123].timezone == "UTC"
        assert users[123].mention_level == MentionLevel.AVATARHOVER
        assert users[123].email is None
        assert users[123].enable_wikidot_pm is True
        assert users[123].enable_email is True
        assert users[123].enable_apprise is True

    @pytest.mark.asyncio
    async def test_get_user(self, mongodb_client: MongoDBClient) -> None:
        """Test getting a specific user."""
        mock_user = {
            "userid": 123,
            "username": "TestUser",
            "apprise_urls": [],
            "timezone": "UTC",
        }

        mongodb_client.db["t_users"].find_one = AsyncMock(return_value=mock_user)

        user = await mongodb_client.get_user(123)

        assert user is not None
        assert user["userid"] == 123
        assert user["username"] == "TestUser"

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, mongodb_client: MongoDBClient) -> None:
        """Test getting a user that doesn't exist."""
        mongodb_client.db["t_users"].find_one = AsyncMock(return_value=None)

        user = await mongodb_client.get_user(999)

        assert user is None

    @pytest.mark.asyncio
    async def test_remove_user(self, mongodb_client: MongoDBClient) -> None:
        """Test removing a user."""
        mongodb_client.db["t_users"].delete_one = AsyncMock()

        await mongodb_client.remove_user(123)

        mongodb_client.db["t_users"].delete_one.assert_called_once_with({"userid": 123})

    @pytest.mark.asyncio
    async def test_upsert_contacts(self, mongodb_client: MongoDBClient) -> None:
        """Test upserting contacts."""
        contacts = [
            {"userid": 123, "username": "TestUser", "email": "test@example.com"},
            {"userid": 456, "username": "AnotherUser", "email": "another@example.com"},
        ]

        mongodb_client.db["t_users"].bulk_write = AsyncMock()

        await mongodb_client.upsert_contacts(contacts)

        mongodb_client.db["t_users"].bulk_write.assert_called_once()
        call_args = mongodb_client.db["t_users"].bulk_write.call_args
        operations = call_args[0][0]
        assert len(operations) == 2

    @pytest.mark.asyncio
    async def test_upsert_contacts_empty(self, mongodb_client: MongoDBClient) -> None:
        """Test upserting empty contacts list."""
        mongodb_client.db["t_users"].bulk_write = AsyncMock()

        await mongodb_client.upsert_contacts([])

        mongodb_client.db["t_users"].bulk_write.assert_not_called()

    @pytest.mark.asyncio
    async def test_upsert_users(self, mongodb_client: MongoDBClient) -> None:
        """Test upserting users."""
        users = [
            UserInfo(
                userid=123,
                username="TestUser",
                apprise_urls=["json://localhost"],
                timezone="UTC",
                mention_level=MentionLevel.AVATARHOVER,
                email="test@example.com",
                enable_wikidot_pm=True,
                enable_email=True,
                enable_apprise=True,
            )
        ]

        mongodb_client.db["t_users"].bulk_write = AsyncMock()

        await mongodb_client.upsert_users(users)

        mongodb_client.db["t_users"].bulk_write.assert_called_once()
        call_args = mongodb_client.db["t_users"].bulk_write.call_args
        operations = call_args[0][0]
        assert len(operations) == 1

    @pytest.mark.asyncio
    async def test_upsert_users_empty(self, mongodb_client: MongoDBClient) -> None:
        """Test upserting empty users list."""
        mongodb_client.db["t_users"].bulk_write = AsyncMock()

        await mongodb_client.upsert_users([])

        mongodb_client.db["t_users"].bulk_write.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_metadata(self, mongodb_client: MongoDBClient) -> None:
        """Test getting metadata."""
        mock_metadata = {"key": "last_rss_check", "value": {"site1": datetime.now(UTC)}}

        mongodb_client.db["t_metadata"].find_one = AsyncMock(return_value=mock_metadata)

        value = await mongodb_client.get_metadata("last_rss_check")

        assert value is not None
        assert isinstance(value, dict)

    @pytest.mark.asyncio
    async def test_get_metadata_not_found(self, mongodb_client: MongoDBClient) -> None:
        """Test getting metadata that doesn't exist."""
        mongodb_client.db["t_metadata"].find_one = AsyncMock(return_value=None)

        value = await mongodb_client.get_metadata("nonexistent")

        assert value is None

    @pytest.mark.asyncio
    async def test_set_metadata(self, mongodb_client: MongoDBClient) -> None:
        """Test setting metadata."""
        mongodb_client.db["t_metadata"].update_one = AsyncMock()

        metadata_value = {"site1": datetime.now(UTC)}
        await mongodb_client.set_metadata("last_rss_check", metadata_value)

        mongodb_client.db["t_metadata"].update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_close(self, mongodb_client: MongoDBClient) -> None:
        """Test closing MongoDB connection."""
        mongodb_client.client.close = AsyncMock()

        await mongodb_client.close()

        mongodb_client.client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_schema_validation_new_collections(
        self, mongodb_client: MongoDBClient
    ) -> None:
        """Test schema validation for new collections."""
        # Mock that collections don't exist
        mongodb_client.db.list_collection_names = AsyncMock(return_value=[])

        # Mock collection creation
        mongodb_client.db.create_collection = AsyncMock()
        mongodb_client.db["t_users"].create_index = AsyncMock()
        mongodb_client.db["t_metadata"].create_index = AsyncMock()

        await mongodb_client.ensure_schema_validation()

        # Should create both collections
        assert mongodb_client.db.create_collection.call_count == 2

    @pytest.mark.asyncio
    async def test_ensure_schema_validation_existing_collections(
        self, mongodb_client: MongoDBClient
    ) -> None:
        """Test schema validation when collections already exist."""
        # Mock that collections exist
        mongodb_client.db.list_collection_names = AsyncMock(
            return_value=["t_users", "t_metadata"]
        )

        mongodb_client.db.create_collection = AsyncMock()

        await mongodb_client.ensure_schema_validation()

        # Should not create collections
        mongodb_client.db.create_collection.assert_not_called()


class TestMongoDBGlobalFunctions:
    """Test global MongoDB functions."""

    @pytest.mark.asyncio
    async def test_init_mongodb_with_uri(self) -> None:
        """Test initializing MongoDB with URI."""
        with (
            patch("scoparia.mongodb.get_config") as mock_get_config,
            patch("scoparia.mongodb.MongoDBClient") as mock_client_class,
            patch("scoparia.mongodb.AsyncMongoClient"),
        ):
            mock_config = MagicMock()
            mock_config.mongodb_uri = "mongodb://localhost:27017"
            mock_get_config.return_value = mock_config

            mock_client_instance = AsyncMock()
            mock_client_instance.ensure_schema_validation = AsyncMock()
            mock_client_class.return_value = mock_client_instance

            await init_mongodb()

            mock_client_class.assert_called_once_with("mongodb://localhost:27017")
            mock_client_instance.ensure_schema_validation.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_mongodb_no_database_mode(self) -> None:
        """Test initializing MongoDB in no-database mode."""
        with (
            patch("scoparia.mongodb.get_config") as mock_get_config,
            patch("scoparia.mongodb.MongoDBClient") as mock_client_class,
            patch("scoparia.mongodb._mongodb_instance", None),
        ):
            mock_config = MagicMock()
            mock_config.mongodb_uri = None
            mock_get_config.return_value = mock_config

            await init_mongodb()

            mock_client_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_init_mongodb_already_initialized(self) -> None:
        """Test that initializing MongoDB twice raises RuntimeError."""
        with (
            patch("scoparia.mongodb.get_config") as mock_get_config,
            patch("scoparia.mongodb.MongoDBClient") as mock_client_class,
            patch("scoparia.mongodb._mongodb_lock") as mock_lock,
        ):
            mock_config = MagicMock()
            mock_config.mongodb_uri = "mongodb://localhost:27017"
            mock_get_config.return_value = mock_config

            mock_client_instance = AsyncMock()
            mock_client_instance.ensure_schema_validation = AsyncMock()
            mock_client_class.return_value = mock_client_instance

            # Mock lock to simulate already initialized
            async def lock_enter(self):
                raise RuntimeError("MongoDB already initialized.")

            mock_lock.__aenter__ = lock_enter

            with pytest.raises(RuntimeError, match="MongoDB already initialized"):
                await init_mongodb()

    def test_get_mongodb_not_initialized(self) -> None:
        """Test that getting MongoDB before initialization raises RuntimeError."""
        with (
            patch("scoparia.mongodb._mongodb_instance", None),
            pytest.raises(RuntimeError, match="MongoDB not initialized"),
        ):
            get_mongodb()

    def test_get_mongodb_initialized(self) -> None:
        """Test getting MongoDB after initialization."""
        mock_instance = MagicMock()
        with patch("scoparia.mongodb._mongodb_instance", mock_instance):
            result = get_mongodb()
            assert result == mock_instance
