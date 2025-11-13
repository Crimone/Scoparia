import asyncio
import contextlib
import re
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from enum import Enum
from functools import wraps
from re import Match
from typing import Any, cast
from urllib.parse import urlparse

import aiohttp
import feedparser
import msgspec
from aiohttp.client_exceptions import ServerDisconnectedError
from aiohttp_retry import ExponentialRetry, RetryClient
from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

from . import logger
from .config import MentionLevel, UserInfo

# ==============================================================================
# Exceptions
# ==============================================================================


class WikidotException(Exception):
    """Base exception class for wikidot.py.

    Parameters
    ----------
    message : str
        Exception message
    """

    def __init__(self, message):
        super().__init__(message)


class UnexpectedException(WikidotException):
    """Exception raised when an unexpected error occurs.

    Parameters
    ----------
    message : str
        Exception message
    """

    def __init__(self, message):
        super().__init__(message)


class SessionCreateException(WikidotException):
    """Exception raised when session creation fails.

    Parameters
    ----------
    message : str
        Exception message
    """

    def __init__(self, message):
        super().__init__(message)


class LoginRequiredException(WikidotException):
    """Exception raised when login is required but not logged in.

    Parameters
    ----------
    message : str
        Exception message
    """

    def __init__(self, message):
        super().__init__(message)


class AjaxModuleConnectorException(WikidotException):
    """Base exception class for Ajax Module Connector related errors.

    Parameters
    ----------
    message : str
        Exception message
    """

    def __init__(self, message):
        super().__init__(message)


class AMCHttpStatusCodeException(AjaxModuleConnectorException):
    """Exception raised when AMC returns non-200 HTTP status code.

    Parameters
    ----------
    message : str
        Exception message
    status_code : int
        HTTP status code that caused the error

    Attributes
    ----------
    status_code : int
        HTTP status code that caused the error
    """

    def __init__(self, message, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class WikidotStatusCodeException(AjaxModuleConnectorException):
    """Exception raised when AMC response status is not 'ok'.

    Parameters
    ----------
    message : str
        Exception message
    status_code : str
        Wikidot error status code

    Attributes
    ----------
    status_code : str
        Wikidot error status code
    """

    def __init__(self, message, status_code: str):
        super().__init__(message)
        self.status_code = status_code


class ResponseDataException(AjaxModuleConnectorException):
    """Exception raised when AMC response data is invalid.

    Parameters
    ----------
    message : str
        Exception message
    """

    def __init__(self, message):
        super().__init__(message)


class NotFoundException(WikidotException):
    """Exception raised when requested resource is not found.

    Parameters
    ----------
    message : str
        Exception message
    """

    def __init__(self, message):
        super().__init__(message)


class TargetExistsException(WikidotException):
    """Exception raised when trying to create a resource that already exists.

    Parameters
    ----------
    message : str
        Exception message
    """

    def __init__(self, message):
        super().__init__(message)


class TargetErrorException(WikidotException):
    """Exception raised when operation cannot be applied to target object.

    Parameters
    ----------
    message : str
        Exception message
    """

    def __init__(self, message):
        super().__init__(message)


class ForbiddenException(WikidotException):
    """Exception raised when operation is forbidden due to insufficient permissions.

    Parameters
    ----------
    message : str
        Exception message
    """

    def __init__(self, message):
        super().__init__(message)


class NoElementException(WikidotException):
    """Exception raised when required element is not found.

    Parameters
    ----------
    message : str
        Exception message
    """

    def __init__(self, message):
        super().__init__(message)


# ==============================================================================
# Decorators
# ==============================================================================


def login_required(func):
    """Decorator for methods/functions that require login.

    This decorator automatically checks login status before execution.
    Raises LoginRequiredException if not logged in.

    Client instance is searched in the following priority:
    1. 'client' named argument
    2. Any argument that is a Client instance
    3. self.client (caller object's attribute)
    4. self's attribute's client attribute (e.g., self.site.client)

    Parameters
    ----------
    func : callable
        Function or method to decorate

    Returns
    -------
    callable
        Wrapped function or method

    Raises
    ------
    ValueError
        If client instance is not found
    LoginRequiredException
        If not logged in (via client.login_check())
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        client = None
        if "client" in kwargs:
            client = kwargs["client"]
        else:
            for arg in args:
                if isinstance(arg, Client):
                    client = arg
                    break

            # Check if exists in self?
            if client is None and args:
                if hasattr(args[0], "client"):
                    client = args[0].client
                else:
                    # Search for client in self's attributes
                    for attr_name in dir(args[0]):
                        if attr_name.startswith("_"):
                            continue
                        attr = getattr(args[0], attr_name)
                        if hasattr(attr, "client"):
                            client = attr.client
                            if isinstance(client, Client):
                                break

        if client is None:
            raise ValueError("Client is not found")

        client.login_check()

        return func(*args, **kwargs)

    return wrapper


# ==============================================================================
# Ajax Module Connector
# ==============================================================================


class AjaxRequestHeader:
    """Class to manage request headers for Ajax Module Connector communication.

    Manages Content-Type, User-Agent, Referer, Cookie, etc., and provides
    functionality to generate appropriate HTTP headers.
    """

    def __init__(
        self,
        content_type: str | None = None,
        user_agent: str | None = None,
        referer: str | None = None,
        cookie: dict | None = None,
    ):
        """Initialize AjaxRequestHeader.

        Parameters
        ----------
        content_type : str | None, default None
            Content-Type to set. Uses default if None
        user_agent : str | None, default None
            User-Agent to set. Uses default if None
        referer : str | None, default None
            Referer to set. Uses default if None
        cookie : dict | None, default None
            Cookie to set. Uses empty dict if None
        """
        self.content_type: str = (
            "application/x-www-form-urlencoded; charset=UTF-8"
            if content_type is None
            else content_type
        )
        self.user_agent: str = "Scoparia" if user_agent is None else user_agent
        self.referer: str = "https://www.wikidot.com/" if referer is None else referer
        self.cookie: dict[str, Any] = {"wikidot_token7": 123456}
        if cookie is not None:
            self.cookie.update(cookie)
        return

    def set_cookie(self, name, value) -> None:
        """Set a cookie.

        Parameters
        ----------
        name : str
            Cookie name
        value : str
            Cookie value
        """
        self.cookie[name] = value
        return

    def delete_cookie(self, name) -> None:
        """Delete a cookie.

        Parameters
        ----------
        name : str
            Cookie name to delete
        """
        del self.cookie[name]
        return

    def get_header(self) -> dict:
        """Get constructed HTTP header.

        Returns
        -------
        dict
            Header dictionary for HTTP request
        """
        return {
            "Content-Type": self.content_type,
            "User-Agent": self.user_agent,
            "Referer": self.referer,
            "Cookie": "".join(
                [f"{name}={value};" for name, value in self.cookie.items()]
            ),
        }


class AjaxModuleConnectorConfig(msgspec.Struct):
    """Data class holding Ajax Module Connector communication settings.

    Manages settings such as request timeout, retry count, concurrent connections, etc.

    Attributes
    ----------
    request_timeout : int, default 20
        Request timeout in seconds
    attempt_limit : int, default 3
        Maximum retry attempts on error
    retry_interval : int, default 5
        Retry interval (seconds)
    semaphore_limit : int, default 10
        Maximum concurrent async requests
    """

    request_timeout: int = 20
    attempt_limit: int = 3
    retry_interval: int = 5
    semaphore_limit: int = 10


# ==============================================================================
# Parser utilities
# ==============================================================================


def odate_parse(odate_element: Tag) -> datetime:
    """Parse odate element and return datetime object.

    Parameters
    ----------
    odate_element: Tag
        odate element

    Returns
    -------
    datetime
        Datetime represented by the odate element

    Raises
    ------
    ValueError
        If odate element does not contain a valid unix time
    """
    _odate_classes = odate_element["class"]
    for _odate_class in _odate_classes:
        if "time_" in str(_odate_class):
            unix_time = int(str(_odate_class).replace("time_", ""))
            return datetime.fromtimestamp(unix_time, tz=UTC)

    raise ValueError("odate element does not contain a valid unix time")


def user_parse(elem: Tag) -> "User":
    """Parse printuser element and return user object.

    Parameters
    ----------
    elem: Tag
        Element to parse (element with printuser class)

    Returns
    -------
    User
        Parsed user object with appropriate type
    """
    if ("class" in elem.attrs and "deleted" in elem["class"]) or (
        isinstance(elem, str) and elem.strip() == "(user deleted)"
    ):
        if isinstance(elem, str):
            return User(
                type=UserType.DELETED,
                id=0,
                name="account deleted",
                unix_name="account_deleted",
            )
        else:
            return User(
                type=UserType.DELETED,
                id=int(str(elem["data-id"])),
                name="account deleted",
                unix_name="account_deleted",
            )

    if "class" in elem.attrs and "anonymous" in elem["class"]:
        ip_elem = elem.find("span", class_="ip")
        if ip_elem is None:
            return User(
                type=UserType.ANONYMOUS,
                name="Anonymous",
                unix_name="anonymous",
            )
        ip = ip_elem.get_text().replace("(", "").replace(")", "").strip()
        return User(
            type=UserType.ANONYMOUS,
            name="Anonymous",
            unix_name="anonymous",
            ip=ip,
        )

    # Treat as GuestUser if has Gravatar URL
    img_elem = elem.find("img")
    if isinstance(img_elem, Tag) and "gravatar.com" in img_elem["src"]:
        avatar_url = img_elem["src"]
        guest_name = elem.get_text().strip().split(" ")[0]
        return User(
            type=UserType.GUEST,
            name=guest_name,
            avatar_url=str(avatar_url) if avatar_url else None,
        )

    if elem.get_text() == "Wikidot":
        return User(
            type=UserType.WIKIDOT,
            name="Wikidot",
            unix_name="wikidot",
        )

    _user = elem.find_all("a")[-1]
    if not isinstance(_user, Tag):
        raise ValueError("link element is not found")
    user_name = _user.get_text()
    user_unix = str(_user.get("href")).replace("https://www.wikidot.com/user:info/", "")
    user_id = int(
        str(_user.get("onclick"))
        .replace("WIKIDOT.page.listeners.userInfo(", "")
        .replace("); return false;", "")
    )

    return User(
        type=UserType.USER,
        id=user_id,
        name=user_name,
        unix_name=user_unix,
        avatar_url=f"https://www.wikidot.com/avatar.php?userid={user_id}",
    )


# ==============================================================================
# Authentication
# ==============================================================================


class HTTPAuthentication:
    """Class providing HTTP authentication to Wikidot.

    Provides static methods for managing login and logout processing.
    """

    @staticmethod
    async def login(
        client: "Client",
        username: str,
        password: str,
    ):
        """Log in to Wikidot with username and password (async).

        Parameters
        ----------
        client : Client
            Client instance to connect with
        username : str
            Username to log in with
        password : str
            User's password

        Raises
        ------
        SessionCreateException
            If login attempt fails (HTTP response code error, authentication
            mismatch, cookie issues, etc.)
        """
        # Execute login request using the shared async client
        timeout = aiohttp.ClientTimeout(total=20)
        async with client._client.post(
            url="https://www.wikidot.com/default--flow/login__LoginPopupScreen",
            data={
                "login": username,
                "password": password,
                "action": "Login2Action",
                "event": "login",
            },
            headers=client.header.get_header(),
            timeout=timeout,
        ) as response:
            # Check status code
            if response.status != 200:
                raise SessionCreateException(
                    "Login attempt is failed due to HTTP status code: "
                    + str(response.status)
                )

            # Check body
            response_text = await response.text()
            if "The login and password do not match" in response_text:
                raise SessionCreateException(
                    "Login attempt is failed due to invalid username or password"
                )

            # Check cookies
            if "WIKIDOT_SESSION_ID" not in response.cookies:
                raise SessionCreateException(
                    "Login attempt is failed due to invalid cookies"
                )

            # Set cookies
            session_id = response.cookies["WIKIDOT_SESSION_ID"].value
            client.header.set_cookie("WIKIDOT_SESSION_ID", session_id)

    @staticmethod
    async def logout(client: "Client"):
        """Log out from Wikidot (async).

        Parameters
        ----------
        client : Client
            Client instance to log out

        Notes
        -----
        Even if an error occurs during logout processing, it is ignored and
        cookie deletion is always performed.
        """
        with contextlib.suppress(Exception):
            # Execute logout request to www.wikidot.com
            await client.ajax(
                {
                    "action": "Login2Action",
                    "event": "logout",
                    "moduleName": "Empty",
                },
                "https://www.wikidot.com",
            )

        client.header.delete_cookie("WIKIDOT_SESSION_ID")


# ==============================================================================
# Link classes
# ==============================================================================


class Link(msgspec.Struct):
    """Class representing a link with text and URL.

    Attributes
    ----------
    text : str
        Link text
    url : str
        Link URL
    """

    text: str
    url: str


# ==============================================================================
# User classes
# ==============================================================================


class UserType(str, Enum):
    """Enumeration of user types."""

    USER = "user"  # Normal registered user
    DELETED = "deleted"  # Deleted user account
    ANONYMOUS = "anonymous"  # Anonymous (unregistered) user
    GUEST = "guest"  # Guest user (posted with name and email)
    WIKIDOT = "wikidot"  # Wikidot system user


class User(msgspec.Struct):
    """Unified class representing any type of Wikidot user.

    Attributes
    ----------
    type : UserType
        Type of user (user, deleted, anonymous, guest, wikidot)
    id : int | None
        User ID (None for anonymous, guest, or system users)
    name : str | None
        Username
    unix_name : str | None
        UNIX format name used in user URL (None for guest users)
    avatar_url : str | None
        User avatar image URL
    ip : str | None
        User IP address (only set for anonymous users)
    """

    type: UserType
    id: int | None = None
    name: str | None = None
    unix_name: str | None = None
    avatar_url: str | None = None
    ip: str | None = None


# ==============================================================================
# Page classes
# ==============================================================================


class Page(msgspec.Struct):
    """Class representing a Wikidot page.

    Holds basic information about a page. Provides information like page title,
    fullname, creator, creation datetime, etc.

    Attributes
    ----------
    site_url : str
        Site URL where this page belongs
    fullname : str
        Page fullname
    title : str
        Page title
    created_by : User
        Page creator
    created_at : datetime
        Page creation datetime
    updated_by : User
        Page updater
    updated_at : datetime
        Page update datetime
    """

    site_url: str
    fullname: str
    title: str
    created_by: "User"
    created_at: datetime
    updated_by: "User"
    updated_at: datetime

    @staticmethod
    def _parse_from_html(html_body: BeautifulSoup, site_url: str) -> "Page | None":
        """Parse page information from HTML body.

        Parameters
        ----------
        html_body : BeautifulSoup
            HTML body containing page information
        site_url : str
            Site URL where these pages belong

        Returns
        -------
        Page | None
            Parsed Page object, or None if parsing fails
        """
        page_elem = html_body.select_one("div.page")

        if page_elem is None:
            logger.debug("Page element not found")
            return None

        try:
            # Get fullname
            fullname_value = page_elem.select_one("span.query_fullname")
            if fullname_value is None:
                logger.debug("Page element missing fullname value")
                return None
            fullname = fullname_value.text.strip()

            # Get title
            title_value = page_elem.select_one("span.query_title")
            if title_value is None:
                logger.debug("Page element %s missing title value", fullname)
                return None
            title = title_value.text.strip()

            # Get created_by from created_by_linked (contains printuser element)
            created_by_user_elem = page_elem.select_one(
                "span.query_created_by_linked span.printuser"
            )
            if created_by_user_elem is None:
                raise NoElementException(
                    f"User element is not found for page {fullname}"
                )
            created_by = user_parse(created_by_user_elem)

            # Get created_at from span.query_created_at > span.odate
            created_at_odate = page_elem.select_one("span.query_created_at span.odate")
            if created_at_odate is None or not isinstance(created_at_odate, Tag):
                raise NoElementException(
                    f"Created at element is not found for page {fullname}"
                )
            created_at = odate_parse(created_at_odate)

            # Get updated_by from updated_by_linked (contains printuser element)
            updated_by_user_elem = page_elem.select_one(
                "span.query_updated_by_linked span.printuser"
            )
            if updated_by_user_elem is None:
                raise NoElementException(
                    f"Updated by user element is not found for page {fullname}"
                )
            updated_by = user_parse(updated_by_user_elem)

            # Get updated_at from span.query_updated_at > span.odate
            updated_at_odate = page_elem.select_one("span.query_updated_at span.odate")
            if updated_at_odate is None or not isinstance(updated_at_odate, Tag):
                raise NoElementException(
                    f"Updated at element is not found for page {fullname}"
                )
            updated_at = odate_parse(updated_at_odate)

            return Page(
                site_url=site_url,
                fullname=fullname,
                title=title,
                created_by=created_by,
                created_at=created_at,
                updated_by=updated_by,
                updated_at=updated_at,
            )
        except Exception as e:
            logger.debug("Failed to parse page element: %s", e, exc_info=True)
            return None

    @classmethod
    async def get_from_fullname(cls, site_url: str, fullname: str) -> "Page | None":
        """Get page information from fullname.

        Uses ListPagesModule to fetch page information via API.

        Parameters
        ----------
        site_url : str
            Site URL (e.g., "https://scp-wiki-cn.wikidot.com")
        fullname : str
            Page fullname

        Returns
        -------
        Page | None
            Page object if found, None otherwise
        """
        try:
            # Query ListPagesModule
            page_elements = await _query_list_pages_module(
                site_url=site_url,
                fields=[
                    "fullname",
                    "title",
                    "created_by_linked",
                    "created_at",
                    "updated_by_linked",
                    "updated_at",
                ],
                per_page=1,
                fullname=fullname,
            )

            # Parse page elements
            if not page_elements:
                logger.debug("Page not found: %s", fullname)
                return None

            # Create temporary BeautifulSoup object for parsing
            temp_html = BeautifulSoup(
                "".join(str(elem) for elem in page_elements), "lxml"
            )
            return cls._parse_from_html(temp_html, site_url)
        except Exception as e:
            logger.debug(
                "Failed to get page from fullname %s: %s",
                fullname,
                e,
                exc_info=True,
            )
            return None


# ==============================================================================
# RSS Forum Post classes
# ==============================================================================


class RSSForumPost(msgspec.Struct):
    """Class representing a forum post from RSS feed.

    Attributes
    ----------
    post_id : int
        Post ID
    thread_id : int
        Thread ID
    title : str
        Post title
    link : str
        Post URL
    author_name : str
        Author name
    content : str
        Post content (HTML)
    publish_time : datetime
        Publish datetime
    site_url : str
        Site URL where this post is from
    """

    post_id: int
    thread_id: int
    title: str
    link: str
    author_name: str
    content: str
    publish_time: datetime
    site_url: str
    parents: list["Link"]


# ==============================================================================
# Forum Category classes
# ==============================================================================


class ForumCategory(msgspec.Struct):
    """Class representing a forum category.

    Attributes
    ----------
    id : int
        Category ID
    title : str
        Category title
    """

    id: int
    title: str


# ==============================================================================
# Forum Post classes
# ==============================================================================


class ForumPost(msgspec.Struct):
    """Class representing a Wikidot forum post.

    Holds information about an individual post (message) in a forum thread.
    Provides information like post title, body, creator, creation datetime, etc.

    Attributes
    ----------
    site_url : str
        Site URL where this post belongs
    thread_id : int
        ID of thread that post belongs to
    id : int
        Post ID
    title : str
        Post title
    text : str
        Post body (HTML text)
    element : BeautifulSoup
        Post HTML element (for parsing)
    created_by : User
        Post creator
    created_at : datetime
        Post creation datetime
    edited_by : User | None, default None
        Post editor (None if not edited)
    edited_at : datetime | None, default None
        Post edit datetime (None if not edited)
    parents : list[ForumPost], default []
        Parent posts chain (from direct parent to root)
    _source : str | None, default None
        Post source (Wikidot notation)
    """

    site_url: str
    thread_id: int
    id: int
    title: str
    text: str
    created_by: "User"
    created_at: datetime
    element: BeautifulSoup
    edited_by: "User | None" = None
    edited_at: datetime | None = None
    parents: list["ForumPost"] = msgspec.field(default_factory=list)
    _source: str | None = None


# ==============================================================================
# Forum Thread classes
# ==============================================================================


class ForumThread(msgspec.Struct):
    """Class representing a Wikidot forum thread.

    Holds basic information about a forum thread. Provides information like
    thread title, description, creator, creation datetime, post count, etc.

    Attributes
    ----------
    site_url : str
        Site URL where this thread belongs
    id : int
        Thread ID
    title : str
        Thread title
    description : str
        Thread description or excerpt
    created_by : User
        Thread creator
    created_at : datetime
        Thread creation datetime
    post_count : int
        Number of posts in thread
    category : ForumCategory
        Forum category that thread belongs to
    page_fullname : str | None, default None
        Full name of the page associated with this thread
    """

    site_url: str
    id: int
    title: str
    description: str
    created_by: "User"
    created_at: datetime
    post_count: int
    category: "ForumCategory"
    page_fullname: str | None = None

    @staticmethod
    def _parse_thread_page(html: BeautifulSoup, site_url: str) -> "ForumThread":
        """Extract thread information from thread page HTML.

        Extracts information like thread title, description, creator, creation
        datetime from HTML and generates ForumThread object.

        Parameters
        ----------
        html : BeautifulSoup
            HTML to parse
        site_url : str
            Site URL where this thread belongs

        Returns
        -------
        ForumThread
            Extracted thread object

        Raises
        ------
        NoElementException
            If required HTML elements are not found
        """
        # title retrieval processing
        # Get last NavigableString of forum-breadcrumbs
        bc_elem = html.select_one("div.forum-breadcrumbs")
        if bc_elem is None:
            raise NoElementException("Breadcrumbs element is not found.")
        title = bc_elem.contents[-1].text.strip().removeprefix("» ")

        # description retrieval processing
        description_block_elem = html.select_one("div.description-block")
        if description_block_elem is None:
            raise NoElementException("Description block element is not found.")
        description = "".join(
            [
                text.strip()
                for text in description_block_elem
                if isinstance(text, NavigableString) and text.strip()
            ]
        )

        # created_by retrieval processing
        user_elem = html.select_one("div.statistics span.printuser")
        if user_elem is None:
            raise NoElementException("User element is not found.")
        created_by = user_parse(user_elem)

        # created_at retrieval processing
        odate_elem = html.select_one("div.statistics span.odate")
        if odate_elem is None:
            raise NoElementException("Odate element is not found.")
        created_at = odate_parse(odate_elem)

        # post_count retrieval processing
        # Text before 3rd br
        br_tags = html.select("div.statistics br")
        if len(br_tags) < 3:
            raise NoElementException("Br tags are not enough.")
        post_count_elem = br_tags[2].previous_sibling
        if post_count_elem is None:
            raise NoElementException("Posts count element is not found.")
        post_count_text = str(post_count_elem)
        post_count_match = re.search(r"(\d+)", post_count_text)
        if post_count_match is None:
            raise NoElementException("Post count is not found.")
        post_count = int(post_count_match.group(1))

        # id retrieval processing
        # Search entire document for WIKIDOT.forumThreadId = xxxxxx;
        script_elem = html.find(
            "script", text=re.compile(r"WIKIDOT.forumThreadId = \d+;")
        )
        if script_elem is None:
            raise NoElementException("Script element is not found.")
        thread_id_match = re.search(r"(\d+)", script_elem.text)
        if thread_id_match is None:
            raise NoElementException("Thread ID is not found in script.")
        thread_id = int(thread_id_match.group(1))

        # Retrieve category
        # Get category link from forum-breadcrumbs (matches /forum/c- pattern)
        # bc_elem is guaranteed to be not None from earlier check
        category_elem = bc_elem.select_one("a[href^='/forum/c-']")
        if category_elem is None:
            raise NoElementException("Category link is not found in breadcrumbs.")

        # Parse category from link element
        href_attr = category_elem.get("href")
        if href_attr is None:
            raise NoElementException("Category element does not have href attribute")
        href = str(href_attr)

        # Extract category ID from href (format: /forum/c-675245/)
        category_id_match = re.search(r"/forum/c-(\d+)/?", href)
        if category_id_match is None:
            raise NoElementException(f"Invalid category href format: {href}")
        category_id = int(category_id_match.group(1))

        # Get category title from link text
        category_title = category_elem.get_text().strip()

        category = ForumCategory(id=category_id, title=category_title)

        # Retrieve page_fullname
        # Get related page from description-block
        page_fullname = None
        if description_block_elem is not None:
            # Find all links that start with / but not forum/ or feed/
            page_links = description_block_elem.select("a[href^='/']")
            for page_link in page_links:
                page_href = page_link.get("href", "")
                # Remove leading slash
                page_fullname_candidate = str(page_href).removeprefix("/")
                # Only set if it's not a forum/feed/javascript link
                if not page_fullname_candidate.startswith(
                    "forum"
                ) and not page_fullname_candidate.startswith("feed"):
                    page_fullname = page_fullname_candidate
                    break

        return ForumThread(
            site_url=site_url,
            id=thread_id,
            title=title,
            description=description,
            created_by=created_by,
            created_at=created_at,
            post_count=post_count,
            category=category,
            page_fullname=page_fullname,
        )

    @classmethod
    async def get_from_id(cls, site_url: str, thread_id: int) -> "ForumThread":
        """Get thread information from thread ID.

        Parameters
        ----------
        site_url : str
            Site URL (e.g., "https://scp-wiki-cn.wikidot.com")
        thread_id : int
            ID of thread to retrieve

        Returns
        -------
        ForumThread
            Retrieved thread information
        """
        # Get global client instance
        client = get_client()

        # Check cache first
        cache_key = (site_url, thread_id)
        if cache_key in client._thread_cache:
            logger.debug("Cache hit for thread %s from %s", thread_id, site_url)
            return client._thread_cache[cache_key]

        response_body = await client.ajax(
            {
                "t": thread_id,
                "moduleName": "forum/ForumViewThreadModule",
            },
            site_url,
        )

        body = response_body["body"]
        html = BeautifulSoup(body, "lxml")

        thread = cls._parse_thread_page(html, site_url)
        if thread_id != thread.id:
            raise NoElementException("Thread ID is not matched.")

        # Store in cache
        client._thread_cache[cache_key] = thread
        logger.debug("Cached thread %s from %s", thread_id, site_url)
        return thread

    async def get_post_by_id(self, post_id: int) -> "ForumPost | None":
        """Get a specific post by its ID directly using ForumViewThreadPostsModule.

        This method uses Wikidot's API to fetch a specific post and only parses
        the target post and its parent chain, making it very efficient.

        Parameters
        ----------
        post_id : int
            The ID of the post to retrieve.

        Returns
        -------
        ForumPost | None
            The post object if found, None otherwise.

        Raises
        ------
        NoElementException
            If required elements are not found in response.
        """
        # Get global client instance
        client = get_client()

        # Check cache first
        cache_key = (self.id, post_id)
        if cache_key in client._post_cache:
            logger.debug("Cache hit for post %s in thread %s", post_id, self.id)
            return client._post_cache[cache_key]

        try:
            # Use ForumViewThreadPostsModule to get the post directly
            response_body = await client.ajax(
                {
                    "postId": post_id,
                    "t": self.id,
                    "order": "",
                    "moduleName": "forum/ForumViewThreadPostsModule",
                },
                self.site_url,
            )

            body = response_body["body"]
            html = BeautifulSoup(body, "lxml")

            # Find the target post element
            target_post_elem = html.select_one(f"div.post#post-{post_id}")
            if target_post_elem is None:
                logger.debug("Post %s not found in thread %s", post_id, self.id)
                return None

            # Parse the target post
            target_post_container = target_post_elem.parent
            target_post, _ = self._parse_post_from_container(
                target_post_elem, target_post_container, self.id, self.site_url
            )

            # Build parent chain by walking up the DOM tree
            parent_chain: list[ForumPost] = []
            current_container = target_post_container

            while current_container is not None:
                # Find parent post-container
                parent_container = current_container.find_parent(
                    "div", class_="post-container"
                )
                if parent_container is None:
                    break

                # Find the post element within this parent container
                parent_post_elem = parent_container.select_one("div.post")
                if parent_post_elem is None:
                    break

                # Parse the parent post
                # Note: We don't know parent's thread_id, but we can get it
                # from the post. For now, use the same thread_id
                # (parent should be in same thread)
                parent_post, _ = self._parse_post_from_container(
                    parent_post_elem, parent_container, self.id, self.site_url
                )
                parent_chain.append(parent_post)

                # Move to next level up
                current_container = parent_container

            # Assign the parent chain to target post
            target_post.parents = parent_chain

            # Store in cache
            client._post_cache[cache_key] = target_post
            logger.debug("Cached post %s in thread %s", post_id, self.id)
            return target_post

        except Exception as e:
            # Fallback to searching through pages if the module doesn't work
            logger.debug(
                "Failed to get post %s from thread %s: %s",
                post_id,
                self.id,
                e,
                exc_info=True,
            )
            return None

    @staticmethod
    def _parse_post_from_container(
        post_elem, post_container, thread_id: int, site_url: str
    ) -> tuple["ForumPost", int | None]:
        """Parse a ForumPost from post element and container.

        Parameters
        ----------
        post_elem : BeautifulSoup element
            The post element (div.post)
        post_container : BeautifulSoup element
            The post container element (div.post-container)
        thread_id : int
            ID of thread that post belongs to
        site_url : str
            Site URL where this post belongs

        Returns
        -------
        tuple[ForumPost, int | None]
            Tuple of (ForumPost object, parent_post_id)

        Raises
        ------
        NoElementException
            If required elements are not found.
        """
        post_id_elem = post_elem.get("id")
        if post_id_elem is None:
            raise NoElementException("Post ID not found")

        parsed_post_id_str = str(post_id_elem).removeprefix("post-")
        if not parsed_post_id_str.isdigit():
            raise NoElementException("Invalid post ID format")
        parsed_post_id = int(parsed_post_id_str)

        # Get title
        title_elem = post_container.select_one("div.title")
        title = title_elem.text.strip() if title_elem else ""

        # Get text
        text_elem = post_container.select_one("div.content")
        text = str(text_elem) if text_elem else ""

        # Get created_by
        user_elem = post_container.select_one("div.info span.printuser")
        if user_elem is None:
            raise NoElementException("User element is not found.")
        created_by = user_parse(user_elem)

        # Get created_at
        odate_elem = post_container.select_one("div.info span.odate")
        if odate_elem is None:
            raise NoElementException("Odate element is not found.")
        created_at = odate_parse(odate_elem)

        # Get edited info if exists
        edited_by = None
        edited_at = None
        edit_info_elem = post_container.select_one("div.changes")
        if edit_info_elem:
            edited_user_elem = edit_info_elem.select_one("span.printuser")
            edited_odate_elem = edit_info_elem.select_one("span.odate")
            if edited_user_elem and edited_odate_elem:
                edited_by = user_parse(edited_user_elem)
                edited_at = odate_parse(edited_odate_elem)

        # Get parent post ID if exists
        parent_post_id_val = None
        if post_container is not None:
            parent_container = post_container.find_parent(
                "div", class_="post-container"
            )
            if parent_container is not None:
                parent_container_id = parent_container.get("id")
                if parent_container_id:
                    parent_id_str = str(parent_container_id).removeprefix("fpc-")
                    if parent_id_str.isdigit():
                        parent_post_id_val = int(parent_id_str)

        post = ForumPost(
            site_url=site_url,
            thread_id=thread_id,
            id=parsed_post_id,
            title=title,
            text=text,
            element=post_elem,
            created_by=created_by,
            created_at=created_at,
            edited_by=edited_by,
            edited_at=edited_at,
            parents=[],
        )

        return post, parent_post_id_val


# ==============================================================================
# Client class
# ==============================================================================


class Client:
    """Core client managing connections and interactions with Wikidot API.

    This class is the foundation for all interactions with Wikidot API.
    All features like user authentication, site operations, page management
    are provided through this client.
    """

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        config: AjaxModuleConnectorConfig | None = None,
    ):
        """Initialize client.

        Parameters
        ----------
        username : str | None, default None
            Username (not used in __init__, login happens in init_client)
        password : str | None, default None
            Password (not used in __init__, login happens in init_client)
        config : AjaxModuleConnectorConfig | None, default None
            Communication configuration
        """

        # Initialize configuration
        self.config: AjaxModuleConnectorConfig = (
            config if config is not None else AjaxModuleConnectorConfig()
        )

        # Initialize header
        self.header: AjaxRequestHeader = AjaxRequestHeader()

        # Create shared async client session with connection pool limits
        connector = aiohttp.TCPConnector(
            limit=self.config.semaphore_limit,
            limit_per_host=self.config.semaphore_limit,
        )
        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)
        base_session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
        )

        # Configure retry strategy: 10 retries with exponential backoff
        retry_options = ExponentialRetry(
            attempts=10,
            start_timeout=0.4,
            statuses={429, 500, 502, 503, 504},
            exceptions={
                ServerDisconnectedError,
                TimeoutError,
            },
        )
        self._client: RetryClient = RetryClient(
            client_session=base_session, retry_options=retry_options
        )

        # Initialize session-related variables
        self.is_logged_in = False
        self.username: str | None = None

        # Initialize caches for thread and post data
        self._thread_cache: dict[tuple[str, int], Any] = {}
        self._post_cache: dict[tuple[int, int], Any] = {}

    async def aclose(self) -> None:
        """Close the async client session and release connections."""
        await self._client.close()

    async def ajax(self, body: dict[str, Any], site_url: str) -> dict[str, Any]:
        """Send a single request to Ajax Module Connector (async).

        Parameters
        ----------
        body : dict[str, Any]
            Request body to send
        site_url : str
            Site URL (e.g., "https://scp-wiki-cn.wikidot.com")

        Returns
        -------
        dict[str, Any]
            Decoded JSON response body

        Raises
        ------
        AMCHttpStatusCodeException
            If HTTP status code is not 200
        WikidotStatusCodeException
            If response status is not "ok"
        ResponseDataException
            If response is invalid JSON format or empty
        """
        url = f"{site_url}/ajax-module-connector.php"

        body_copy = body.copy()
        # Get wikidot_token7 from cookie
        token = self.header.cookie.get("wikidot_token7", 123456)
        body_copy["wikidot_token7"] = token
        logger.debug("Ajax Request: %s -> %s", url, body_copy)

        async with self._client.post(
            url,
            headers=self.header.get_header(),
            data=body_copy,
        ) as response:
            response.raise_for_status()
            response_content = await response.read()

        response_body = msgspec.json.decode(response_content)
        if not response_body:
            raise ResponseDataException("AMC returned empty data")

        if "status" in response_body and response_body["status"] != "ok":
            status = response_body["status"]
            if status == "no_permission":
                raise ForbiddenException("No permission to perform this action")
            raise WikidotStatusCodeException(f"AMC error status: {status}", status)

        return response_body

    async def fetch_rss_posts(
        self, site_url: str, since: datetime | None = None
    ) -> tuple[list["RSSForumPost"], datetime]:
        """Fetch latest posts from RSS feed.

        Parameters
        ----------
        site_url : str
            Site URL (e.g., "https://scp-wiki-cn.wikidot.com")
        since : datetime | None, default None
            Only return posts published after this time.
            If None, return all posts.

        Returns
        -------
        tuple[list[RSSForumPost], datetime]
            Tuple of (posts, last_build_date) where:
            - posts: List of RSSForumPost objects with parsed RSS data
            - last_build_date: RSS feed's lastBuildDate, or current time
              if feed parsed successfully but no timestamp available

        Raises
        ------
        RuntimeError
            If client is not initialized or RSS feed parsing fails.
        """
        # Construct RSS feed URL
        rss_feed_url = f"{site_url}/feed/forum/posts.xml"

        logger.info("Fetching RSS feed from %s", rss_feed_url)
        if since:
            logger.info("Filtering posts since: %s", since.isoformat())

        # Fetch RSS feed with automatic retry
        async with self._client.get(rss_feed_url) as response:
            response.raise_for_status()
            content = await response.read()

        # Parse RSS feed using feedparser
        feed = feedparser.parse(content)

        # Extract lastBuildDate from feed
        last_build_date: datetime | None = None
        updated_parsed = getattr(feed.feed, "updated_parsed", None)
        if updated_parsed:
            parsed_time = cast(time.struct_time, updated_parsed)
            last_build_date = datetime(*parsed_time[:6], tzinfo=UTC)
            logger.debug("RSS feed lastBuildDate: %s", last_build_date.isoformat())
        else:
            # Feed parsed successfully but no timestamp available, use current time
            last_build_date = datetime.now(UTC)
            logger.debug(
                "No lastBuildDate in RSS feed, using current time: %s",
                last_build_date.isoformat(),
            )

        # Extract scheme from RSS feed URL
        parsed_rss_url = urlparse(rss_feed_url)
        feed_scheme = parsed_rss_url.scheme

        posts: list[RSSForumPost] = []
        for entry in feed.entries:
            if not isinstance(entry, feedparser.util.FeedParserDict):
                continue

            try:
                title = str(entry.title)
                link = str(entry.link)

                # Normalize link scheme to match RSS feed URL scheme
                parsed_link = urlparse(link)
                parsed_link = parsed_link._replace(scheme=feed_scheme)
                link = parsed_link.geturl()

                # Get author name (wikidot:authorName)
                author_name = str(entry.wikidot_authorname)

                # Get content (content:encoded or summary)
                content_text = str(entry.content[0].value).strip()

                # Normalize URLs in content to match RSS feed URL scheme
                site_domain = parsed_link.netloc
                if feed_scheme == "https":
                    # Replace http://site.domain with https://site.domain
                    content_text = content_text.replace(
                        f"http://{site_domain}", f"https://{site_domain}"
                    )

                # Remove forum category and thread links from content
                # Find all <br/> tags and remove from second-to-last onwards
                br_pattern = r"<br\s*/?>"
                br_matches = list[Match[str]](re.finditer(br_pattern, content_text))

                if len(br_matches) >= 2:
                    # Remove from the second-to-last <br/> onwards
                    second_last_pos = br_matches[-2].start()
                    content_text = content_text[:second_last_pos]

                # Get publish date (directly construct from struct_time)
                parsed_time = cast(time.struct_time, entry.published_parsed)
                publish_datetime = datetime(*parsed_time[:6], tzinfo=UTC)

                # Filter by publish time if since is provided
                if since and publish_datetime <= since:
                    continue

                # Parse post_id from URL fragment (required)
                if not parsed_link.fragment:
                    logger.warning("Post missing fragment in URL: %s", link)
                    continue
                post_id = int(parsed_link.fragment.removeprefix("post-"))

                # Parse thread_id from URL path (required)
                thread_match = re.search(r"t-(\d+)", parsed_link.path)
                if not thread_match:
                    logger.warning("Post missing thread_id in URL: %s", link)
                    continue
                thread_id = int(thread_match.group(1))

                # Extract site URL from RSS feed URL
                site_url_value = f"{parsed_rss_url.scheme}://{parsed_rss_url.netloc}"

                posts.append(
                    RSSForumPost(
                        post_id=post_id,
                        thread_id=thread_id,
                        title=title,
                        link=link,
                        author_name=author_name,
                        content=content_text,
                        publish_time=publish_datetime,
                        site_url=site_url_value,
                        parents=[],
                    )
                )
            except Exception as e:
                logger.warning("Failed to parse RSS entry: %s", e)
                continue

        logger.info("Fetched %s posts from RSS feed %s", len(posts), rss_feed_url)
        return posts, last_build_date

    def login_check(self) -> None:
        """Check login status.

        Called before executing operations that require login.
        Raises exception if not logged in.

        Raises
        ------
        LoginRequiredException
            If not logged in
        """
        if not self.is_logged_in:
            raise LoginRequiredException("Login is required to execute this function")
        return

    async def get_contacts(self) -> list[dict[str, Any]]:
        """Get the account's back contacts list and their emails.

        Retrieves back contacts (users who have added this account to their
        contacts) along with their email addresses from the account's contact list.
        Emails are personal information and are not cached to the database;
        they are discarded as soon as they're used.
        Connection needs to be logged in.

        Returns
        -------
        list[dict[str, Any]]
            List of contact dictionaries with keys: userid (int), username (str),
            email (str)

        Raises
        ------
        LoginRequiredException
            If not logged in
        """
        response = await self.ajax(
            {"moduleName": "dashboard/messages/DMContactsModule"},
            "https://www.wikidot.com",
        )
        contacts = BeautifulSoup(response["body"], "lxml")

        contacts_list: list[dict[str, Any]] = []

        # Parse back contacts (under h2 heading)
        back_contacts_heading = cast(Tag | None, contacts.find("h2"))
        if back_contacts_heading is None:
            # The heading does not appear if there are no back contacts
            logger.info("No back contacts found")
            return []

        back_contacts_table = cast(
            Tag | None,
            back_contacts_heading.find_next_sibling(class_="contact-list-table"),
        )
        if back_contacts_table is None:
            # If there is a heading there should also be a contacts table,
            # but can't hurt to be sure
            logger.info("No back contacts table found")
            return []

        for row in cast(Iterable[Tag], back_contacts_table.find_all("tr")):
            cells = list(cast(Iterable[Tag], row.find_all("td")))
            if len(cells) < 2:
                continue
            nametag_cell, address_cell = cells[0], cells[1]
            nametag_span = cast(
                Tag | None, nametag_cell.find("span", class_="printuser")
            )
            if nametag_span is None:
                continue
            user = user_parse(nametag_span)
            if user.id is None or user.name is None:
                continue
            email = address_cell.get_text().strip()
            contacts_list.append(
                {
                    "userid": user.id,
                    "username": user.name,
                    "email": email,
                }
            )

        logger.info(
            "Retrieved %s back contacts with email addresses", len(contacts_list)
        )
        return contacts_list

    async def send_private_message(
        self, to_user_id: int, subject: str, body: str
    ) -> bool:
        """Send a private message to a user.

        Parameters
        ----------
        to_user_id : int
            The Wikidot user ID of the recipient
        subject : str
            Message subject
        body : str
            Message body content

        Returns
        -------
        bool
            True if message was sent successfully, False otherwise

        Raises
        ------
        LoginRequiredException
            If not logged in
        """
        try:
            response = await self.ajax(
                {
                    "source": body,
                    "subject": subject,
                    "to_user_id": to_user_id,
                    "action": "DashboardMessageAction",
                    "event": "send",
                    "moduleName": "Empty",
                },
                "https://www.wikidot.com",
            )

            # Check if message was sent successfully
            if response.get("status") == "ok":
                logger.info("Sent private message to user %s", to_user_id)
                return True
            else:
                logger.warning(
                    "Failed to send private message to user %s: %s",
                    to_user_id,
                    response.get("status"),
                )
                return False

        except Exception as e:
            logger.error(
                "Error sending private message to user %s: %s",
                to_user_id,
                e,
                exc_info=True,
            )
            return False

    async def delete_page(self, site_url: str, fullname: str) -> bool:
        """Delete a page using Ajax Module Connector.

        Parameters
        ----------
        site_url : str
            Site URL where the page belongs
        fullname : str
            Page fullname to delete

        Returns
        -------
        bool
            True if deletion was successful, False otherwise

        Raises
        ------
        Exception
            If the ajax request fails or page cannot be found
        """
        try:
            # Access the page with norender/noredirect to get page ID
            page_url = f"{site_url}/{fullname}/norender/true/noredirect/true"

            async with self._client.get(
                page_url, headers=self.header.get_header()
            ) as response:
                response.raise_for_status()
                html_content = await response.text()

                # Update cookies from response
                for cookie_name, cookie in response.cookies.items():
                    self.header.set_cookie(cookie_name, cookie.value)
                    logger.debug("Updated cookie %s: %s", cookie_name, cookie.value)

            # Extract page ID directly from HTML content
            page_id_match = re.search(
                r"WIKIREQUEST\.info\.pageId = (\d+);", html_content
            )
            if page_id_match is None:
                logger.warning("Page ID not found for %s", fullname)
                return False

            page_id = int(page_id_match.group(1))

            # Delete the page using Ajax
            response = await self.ajax(
                {
                    "action": "WikiPageAction",
                    "event": "deletePage",
                    "page_id": str(page_id),
                    "moduleName": "Empty",
                },
                site_url,
            )

            # Check if the response indicates success
            if response.get("status") == "ok":
                logger.info("Successfully deleted page %s (ID: %s)", fullname, page_id)
                return True
            else:
                logger.warning(
                    "Failed to delete page %s (ID: %s): %s",
                    fullname,
                    page_id,
                    response.get("message", "Unknown error"),
                )
                return False
        except Exception as e:
            logger.error("Error deleting page %s: %s", fullname, e, exc_info=True)
            return False


# ==============================================================================
# Global Client Singleton
# ==============================================================================

_client_instance: Client | None = None
_client_lock = asyncio.Lock()


async def init_client(
    username: str,
    password: str,
    config: AjaxModuleConnectorConfig | None = None,
) -> None:
    """Initialize global Client instance.

    Parameters
    ----------
    username : str
        Wikidot username for authentication
    password : str
        Wikidot password for authentication
    config : AjaxModuleConnectorConfig | None, default None
        Communication configuration

    Raises
    ------
    RuntimeError
        If client is already initialized
    """
    global _client_instance
    async with _client_lock:
        if _client_instance is not None:
            raise RuntimeError("Client already initialized.")

        _client_instance = Client(
            username=username,
            password=password,
            config=config,
        )

        # Perform async login
        await HTTPAuthentication.login(_client_instance, username, password)
        _client_instance.is_logged_in = True
        _client_instance.username = username


def get_client() -> Client:
    """Get global Client instance.

    Returns
    -------
    Client
        Global Client instance

    Raises
    ------
    RuntimeError
        If client is not initialized
    """
    global _client_instance
    if _client_instance is None:
        raise RuntimeError("Client not initialized. Call init_client() first.")
    return _client_instance


async def cleanup_client() -> None:
    """Cleanup global Client instance."""
    global _client_instance
    async with _client_lock:
        if _client_instance is not None:
            # Perform logout if logged in
            if _client_instance.is_logged_in:
                await HTTPAuthentication.logout(_client_instance)
                _client_instance.is_logged_in = False
                _client_instance.username = None
            # Close async client connections
            await _client_instance.aclose()
            _client_instance = None


# ==============================================================================
# ListPagesModule Helper
# ==============================================================================


async def _query_list_pages_module(
    site_url: str,
    fields: list[str],
    form_data_fields: list[str] | None = None,
    per_page: int = 50,
    offset: int = 0,
    category: str | None = None,
    fullname: str | None = None,
) -> list[Tag]:
    """Query ListPagesModule with specified fields and return page elements.

    This function handles the entire workflow: template generation, ajax query,
    and HTML parsing.

    Parameters
    ----------
    site_url : str
        Site URL
    fields : list[str]
        List of field names to query (e.g., 'name', 'title', 'created_at')
    form_data_fields : list[str], default None
        List of form_data fields to include.
    per_page : int, default 50
        Number of pages to fetch per request
    offset : int, default 0
        Offset for pagination
    category : str | None, default None
        Category to filter pages by
    fullname : str | None, default None
        Specific page fullname to query

    Returns
    -------
    list[Tag]
        List of parsed page elements (div.page)

    Raises
    ------
    Exception
        If the ajax request fails

    Examples
    --------
    >>> await _query_list_pages_module(
    ...     site_url="https://example.wikidot.com",
    ...     fields=["name", "title"],
    ...     per_page=10
    ... )
    """
    client = get_client()

    # Build module body template
    module_body = '[[div class="page"]]\n'
    for field in fields:
        module_body += f'[[span class="query_{field}"]] %%{field}%% [[/span]]'
    if form_data_fields:
        for field_name in form_data_fields:
            module_body += (
                f'[[span class="query_{field_name}"]]'
                f" %%form_data{{{field_name}}}%% [[/span]]"
            )
    module_body += "\n[[/div]]"

    # Build query dict
    query_dict: dict[str, Any] = {
        "moduleName": "list/ListPagesModule",
        "perPage": per_page,
        "offset": offset,
        "module_body": module_body,
    }
    if category:
        query_dict["category"] = category
    if fullname:
        query_dict["fullname"] = fullname

    # Execute ajax request and parse
    response_body = await client.ajax(query_dict, site_url)
    html_body = BeautifulSoup(response_body["body"], "lxml")
    return html_body.select("div.page")


# ==============================================================================
# User Config Sync
# ==============================================================================


async def list_pages(
    site_url: str,
    category: str | None = None,
) -> list[Tag]:
    """List pages from a Wikidot site.

    Parameters
    ----------
    site_url : str
        Site URL
    category : str | None, default None
        Category to filter pages by

    Returns
    -------
    list[Tag]
        List of Tag elements representing page elements

    Notes
    -----
    This function uses ListPagesModule to fetch pages. It handles pagination
    automatically and returns all pages.
    """
    pages: list[Tag] = []
    offset = 0
    per_page = 50  # Fetch 50 pages at a time

    while True:
        try:
            # Query ListPagesModule
            page_elements = await _query_list_pages_module(
                site_url=site_url,
                fields=["name", "created_by_linked", "content"],
                form_data_fields=["apprise_urls", "email"],
                per_page=per_page,
                offset=offset,
                category=category,
            )

            if not page_elements:
                break  # No more pages

            # Extend pages list
            pages.extend(page_elements)
            offset += per_page

            # If we got fewer pages than requested, we've reached the end
            if len(page_elements) < per_page:
                break

        except Exception as e:
            logger.error(
                "Error listing pages at offset %s: %s", offset, e, exc_info=True
            )
            break

    return pages


async def sync_user_configs_from_wiki(
    config_wiki_url: str,
    user_config_category: str,
) -> list[UserInfo]:
    """Fetch user configurations from Wikidot wiki.

    Fetches user configurations from the specified category on the config wiki
    and parses them into UserInfo objects.

    Parameters
    ----------
    config_wiki_url : str
        URL of the configuration wiki
    user_config_category : str
        Category name containing user configuration pages

    Returns
    -------
    list[UserInfo]
        List of UserInfo objects parsed from wiki pages

    Notes
    -----
    User configurations are stored as YAML on Wikidot pages. Each page should
    contain a YAML document with fields like:
    - apprise_urls: list[str] (optional)
    - timezone: str (optional, defaults to "UTC")
    - mention_level: str (optional, defaults to "avatarhover")
    - email: str (optional)
    - enable_wikidot_pm: bool (optional, defaults to True)
    - enable_email: bool (optional, defaults to True)
    - enable_apprise: bool (optional, defaults to True)

    Username and userid are extracted from the page's created_by_linked field,
    not from the YAML configuration.
    """

    logger.info(
        "Syncing user configs from %s, category: %s",
        config_wiki_url,
        user_config_category,
    )

    # List all pages in the category
    page_elements = await list_pages(config_wiki_url, category=user_config_category)
    logger.info(
        "Found %s pages in category %s", len(page_elements), user_config_category
    )

    user_infos: list[UserInfo] = []

    for page_elem in page_elements:
        try:
            # Get name from page element
            name_elem = page_elem.select_one("span.query_name")
            if name_elem is None:
                logger.debug("Page element missing name, skipping")
                continue

            page_name = name_elem.get_text().strip()

            # Get created_by_linked and verify it matches the name
            created_by_elem = page_elem.select_one(
                "span.query_created_by_linked span.printuser"
            )
            if created_by_elem is None:
                logger.warning(
                    "Page %s missing created_by_linked element, skipping", page_name
                )
                continue

            try:
                created_by_user = user_parse(created_by_elem)
            except Exception as e:
                logger.warning(
                    "Page %s failed to parse created_by_linked: %s, skipping",
                    page_name,
                    e,
                )
                continue

            # Verify that the creator matches the name (page_name is user ID)
            # Convert page_name to int for comparison
            try:
                page_name_id = int(page_name)
            except ValueError:
                logger.warning(
                    "Page name %s is not a valid user ID, skipping", page_name
                )
                continue

            if created_by_user.id is None or created_by_user.id != page_name_id:
                logger.warning(
                    "Page %s created by user ID %s, does not match page name "
                    "(user ID), attempting to delete page",
                    page_name,
                    created_by_user.id,
                )

                # Delete the page using constructed fullname
                try:
                    fullname = f"{user_config_category}:{page_name}"
                    client = get_client()
                    success = await client.delete_page(config_wiki_url, fullname)
                    if success:
                        logger.info("Successfully deleted page %s", fullname)
                    else:
                        logger.error("Failed to delete page %s", fullname)
                except Exception as e:
                    logger.error(
                        "Error during page deletion for %s: %s",
                        page_name,
                        e,
                        exc_info=True,
                    )

                continue

            # Get username and userid from created_by_user
            if created_by_user.name is None:
                logger.warning(
                    "Page %s created_by_user has no name, skipping", page_name
                )
                continue

            username = created_by_user.name
            userid = created_by_user.id

            # Get content from page element (YAML content)
            content_elem = page_elem.select_one("span.query_content")
            if content_elem is None:
                logger.warning("Page %s missing content element, skipping", page_name)
                continue

            raw_config = content_elem.get_text().strip()

            # Parse YAML config using msgspec
            try:
                config_dict = msgspec.yaml.decode(raw_config)
            except Exception:
                logger.error(
                    "Could not parse user config %s: invalid YAML format",
                    page_name,
                    exc_info=True,
                )
                continue

            # Get apprise_urls from form_data field (default to empty list)
            apprise_urls_elem = page_elem.select_one("span.query_apprise_urls")
            if apprise_urls_elem:
                apprise_urls_text = apprise_urls_elem.get_text().strip()
                apprise_urls = [
                    url.strip() for url in apprise_urls_text.splitlines() if url.strip()
                ]
            else:
                apprise_urls = []

            # Get timezone (default to UTC)
            timezone = config_dict.get("timezone", "UTC")
            if not isinstance(timezone, str):
                timezone = "UTC"

            # Get mention_level (default to AVATARHOVER)
            mention_level_str = config_dict.get("mention_level", "avatarhover")
            if not isinstance(mention_level_str, str):
                mention_level_str = "avatarhover"
            try:
                mention_level = MentionLevel(mention_level_str.lower())
            except ValueError:
                mention_level = MentionLevel.AVATARHOVER

            # Get email from form_data field (optional)
            email_elem = page_elem.select_one("span.query_email")
            if email_elem:
                email_text = email_elem.get_text().strip()
                email = email_text if email_text else None
            else:
                email = None

            # Get notification enable flags
            enable_wikidot_pm = config_dict.get("enable_wikidot_pm") == "1"
            enable_email = config_dict.get("enable_email") == "1"
            enable_apprise = config_dict.get("enable_apprise") == "1"

            # Create UserInfo object
            user_info = UserInfo(
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

            user_infos.append(user_info)
            logger.debug(
                "Parsed user config for %s (ID: %s) from %s",
                username,
                userid,
                page_name,
            )

        except Exception as e:
            logger.error(
                "Error processing page element: %s",
                e,
                exc_info=True,
            )
            continue

    logger.info("Successfully parsed %s user configurations", len(user_infos))
    return user_infos
