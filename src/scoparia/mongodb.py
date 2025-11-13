"""MongoDB database layer for Scoparia."""

import asyncio
from typing import Any

from pymongo import AsyncMongoClient, UpdateOne

from . import logger
from .config import MentionLevel, UserInfo, get_config

DB_NAME = "db_scoparia"
COLLECTION_USERS = "t_users"
COLLECTION_METADATA = "t_metadata"


class MongoDBClient:
    """Simplified MongoDB client for Scoparia."""

    def __init__(self, mongodb_uri: str):
        """Initialize MongoDB client.

        Args:
            mongodb_uri: MongoDB connection URI.
        """
        self.client = AsyncMongoClient(mongodb_uri)
        self.db = self.client[DB_NAME]

    async def close(self) -> None:
        """Close MongoDB connection."""
        await self.client.close()

    # User management
    async def get_all_users(self) -> dict[int, UserInfo]:
        """Get all users from MongoDB.

        Returns:
            Dictionary mapping userid to UserInfo.
            Format: {
                userid: UserInfo(
                    username="...",
                    apprise_urls=[...],
                    timezone="...",
                    mention_level=...,
                    email="..."
                ),
                ...
            }
        """
        users: dict[int, UserInfo] = {}
        async for user in self.db[COLLECTION_USERS].find():
            userid = user["userid"]
            username = user["username"]
            apprise_urls = user["apprise_urls"]
            timezone = user.get("timezone", "UTC")  # Default to UTC if not set
            mention_level_str = user.get("mention_level", "avatarhover")
            email = user.get("email")  # Optional field
            # Get notification enable flags, default to True if not set
            # (backward compatibility)
            enable_wikidot_pm = user.get("enable_wikidot_pm", True)
            enable_email = user.get("enable_email", True)
            enable_apprise = user.get("enable_apprise", True)
            # Parse mention notification level
            try:
                mention_level = MentionLevel(mention_level_str)
            except ValueError:
                mention_level = MentionLevel.AVATARHOVER

            users[userid] = UserInfo(
                userid=userid,
                username=username,
                apprise_urls=apprise_urls,
                timezone=timezone,
                mention_level=mention_level,
                email=email,
                enable_wikidot_pm=enable_wikidot_pm,
                enable_email=enable_email,
                enable_apprise=enable_apprise,
            )
        return users

    async def get_user(self, userid: int) -> dict[str, Any] | None:
        """Get a specific user from MongoDB.

        Args:
            userid: Wikidot user ID.

        Returns:
            User document with userid, username, apprise_urls, and timezone fields,
            or None if user not found.
        """
        return await self.db[COLLECTION_USERS].find_one({"userid": userid})

    async def remove_user(self, userid: int) -> None:
        """Remove a user from MongoDB.

        Args:
            userid: Wikidot user ID to remove.
        """
        await self.db[COLLECTION_USERS].delete_one({"userid": userid})

    async def upsert_contacts(self, contacts: list[dict[str, Any]]) -> None:
        """Bulk upsert multiple contacts in MongoDB.

        This method is more efficient than calling upsert_contact multiple times
        as it performs all operations in a single database request.

        Args:
            contacts: List of contact dictionaries with keys:
                     userid (int), username (str), email (str).
        """
        if not contacts:
            return

        operations = [
            UpdateOne(
                {"userid": contact["userid"]},
                {
                    "$set": {
                        "username": contact["username"],
                        "email": contact["email"],
                    },
                    "$setOnInsert": {
                        "userid": contact["userid"],
                        "apprise_urls": [],
                        "timezone": "Asia/Shanghai",
                        "mention_level": MentionLevel.AVATARHOVER.value,
                        "enable_wikidot_pm": True,
                        "enable_email": True,
                        "enable_apprise": False,
                    },
                },
                upsert=True,
            )
            for contact in contacts
        ]

        await self.db[COLLECTION_USERS].bulk_write(operations)

    async def upsert_users(self, users: list[UserInfo]) -> None:
        """Bulk upsert multiple users in MongoDB.

        This method is more efficient than calling add_user multiple times
        as it performs all operations in a single database request.

        Args:
            users: List of UserInfo objects to upsert.
        """
        if not users:
            return

        operations = [
            UpdateOne(
                {"userid": user_info.userid},
                {
                    "$set": {
                        "userid": user_info.userid,
                        "username": user_info.username,
                        "email": user_info.email,
                        "apprise_urls": user_info.apprise_urls,
                        "timezone": user_info.timezone,
                        "mention_level": user_info.mention_level.value,
                        "enable_wikidot_pm": user_info.enable_wikidot_pm,
                        "enable_email": user_info.enable_email,
                        "enable_apprise": user_info.enable_apprise,
                    }
                },
                upsert=True,
            )
            for user_info in users
        ]

        await self.db[COLLECTION_USERS].bulk_write(operations)

    # Metadata management
    async def get_metadata(self, key: str) -> Any | None:
        """Get metadata value from MongoDB.

        Args:
            key: Metadata key to retrieve (stored as key field).

        Returns:
            Metadata value or None if not found.
        """
        result = await self.db[COLLECTION_METADATA].find_one({"key": key})
        return result["value"] if result else None

    async def set_metadata(self, key: str, value: Any) -> None:
        """Set metadata value in MongoDB.

        Args:
            key: Metadata key (stored as key field).
            value: Metadata value.
        """
        await self.db[COLLECTION_METADATA].update_one(
            {"key": key},
            {"$set": {"key": key, "value": value}},
            upsert=True,
        )

    async def ensure_schema_validation(self) -> None:
        """Set up schema validation for collections.

        Only creates collections with validation if they don't exist yet.
        If collections already exist, validation is not modified.
        """
        # Get existing collection names
        existing_collections = await self.db.list_collection_names()

        # Schema validation for users collection
        if COLLECTION_USERS not in existing_collections:
            users_validator = {
                "$jsonSchema": {
                    "bsonType": "object",
                    "required": ["userid", "username", "apprise_urls"],
                    "properties": {
                        "userid": {
                            "bsonType": "int",
                            "description": "User ID (unique identifier)",
                        },
                        "username": {
                            "bsonType": "string",
                            "description": "Username of the user",
                        },
                        "enable_wikidot_pm": {
                            "bsonType": "bool",
                            "description": (
                                "Whether to enable Wikidot private message "
                                "notifications"
                            ),
                        },
                        "email": {
                            "bsonType": ["string", "null"],
                            "description": "User's email address (optional)",
                        },
                        "enable_email": {
                            "bsonType": "bool",
                            "description": "Whether to enable email notifications",
                        },
                        "apprise_urls": {
                            "bsonType": "array",
                            "items": {"bsonType": "string"},
                            "description": "List of Apprise notification URLs",
                        },
                        "enable_apprise": {
                            "bsonType": "bool",
                            "description": "Whether to enable Apprise notifications",
                        },
                        "timezone": {
                            "bsonType": "string",
                            "description": (
                                "User timezone (IANA format, e.g., 'Asia/Shanghai')"
                            ),
                        },
                        "mention_level": {
                            "bsonType": "string",
                            "enum": ["disabled", "avatarhover", "all"],
                            "description": (
                                "Level of mention notifications: "
                                "disabled, avatarhover, or all"
                            ),
                        },
                    },
                }
            }
            await self.db.create_collection(COLLECTION_USERS, validator=users_validator)
            # Create indexes immediately after collection creation
            try:
                await self.db[COLLECTION_USERS].create_index(
                    [("userid", 1)],
                    unique=True,
                )
            except Exception as e:
                logger.debug("Index creation for users: %s", e)

        # Schema validation for metadata collection
        if COLLECTION_METADATA not in existing_collections:
            metadata_validator = {
                "$jsonSchema": {
                    "bsonType": "object",
                    "required": ["key", "value"],
                    "properties": {
                        "key": {
                            "description": "Metadata key (unique identifier)",
                        },
                        "value": {
                            "description": "Metadata value (any type)",
                        },
                    },
                }
            }
            await self.db.create_collection(
                COLLECTION_METADATA, validator=metadata_validator
            )
            # Create indexes immediately after collection creation
            try:
                await self.db[COLLECTION_METADATA].create_index(
                    [("key", 1)],
                    unique=True,
                )
            except Exception as e:
                logger.debug("Index creation for metadata: %s", e)


# Global MongoDB instance
_mongodb_instance: MongoDBClient | None = None
_mongodb_lock = asyncio.Lock()


async def init_mongodb() -> None:
    """Initialize global MongoDB instance.

    Should be called once during application startup.
    In no-database mode, this function does nothing.

    Raises:
        RuntimeError: If already initialized.
    """
    global _mongodb_instance
    async with _mongodb_lock:
        if _mongodb_instance is not None:
            raise RuntimeError("MongoDB already initialized.")

        cfg = get_config()

        # Skip initialization in no-database mode (mongodb_uri is None)
        if cfg.mongodb_uri is None:
            logger.info("Running in no-database mode, skipping MongoDB initialization")
            return

        # MongoDB mode: create instance and set up schema
        _mongodb_instance = MongoDBClient(cfg.mongodb_uri)

        # Set up schema validation (includes index creation for new collections)
        await _mongodb_instance.ensure_schema_validation()


def get_mongodb() -> MongoDBClient:
    """Get global MongoDB instance.

    Must be called after init_mongodb() has been invoked.

    Returns:
        MongoDBClient instance.

    Raises:
        RuntimeError: If MongoDB has not been initialized.
    """
    if _mongodb_instance is None:
        raise RuntimeError("MongoDB not initialized. Call init_mongodb() first.")
    return _mongodb_instance


async def cleanup_mongodb() -> None:
    """Cleanup global MongoDB instance.

    In no-database mode, this function does nothing.
    """
    global _mongodb_instance
    async with _mongodb_lock:
        if _mongodb_instance is not None:
            await _mongodb_instance.close()
            _mongodb_instance = None
