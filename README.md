<div align="center"><img width="400px" src="https://cdn.jsdelivr.net/gh/Crimone/Scoparia@main/src/scoparia/static/scoparia.webp"/></div>

<h1 align="center">Scoparia</h1>

<div align="center">

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Notify](https://github.com/Crimone/Scoparia/actions/workflows/notify.yml/badge.svg)](https://github.com/Crimone/Scoparia/actions/workflows/notify.yml)
[![License](https://img.shields.io/badge/license-AGPL--3.0-purple.svg)](https://github.com/Crimone/Scoparia/blob/main/LICENSE)

</div>

`Scoparia` is a lightweight, serverless, CI/CD-oriented notification system designed for Wikidot forums. It monitors forum RSS feeds, detects user mentions, replies, and related activities, and sends notifications through multiple channels.

## Prerequisites

- Access to Wikidot forums for monitoring
- Valid Wikidot account credentials
- Optional: MongoDB instance for persistent storage

## Configuration Reference

`Scoparia` supports two operation modes:
- **Database Mode**: Uses MongoDB for persistent storage and wiki-based user configuration
- **No-Database Mode**: Uses environment variables for configuration (suitable for serverless deployments)

### Environment Variables

**Basic Configuration**

| Variable | Required | Description |
|----------|----------|-------------|
| `WIKIDOT_USERNAME` | ✅ | Wikidot username |
| `WIKIDOT_PASSWORD` | ✅ | Wikidot password |
| `RSS_SITE_URLS` | ✅ | JSON array of site URLs to monitor |

**Database Mode**

| Variable | Required | Description |
|----------|----------|-------------|
| `MONGODB_URI` | ✅ | MongoDB connection string |

**No-Database Mode**

| Variable | Required | Description |
|----------|----------|-------------|
| `USERS_JSON` | ✅ | User configuration JSON (required when not using MongoDB) |
| `CONFIG_WIKI_URL` | ✅ | User configuration wiki URL |
| `USER_CONFIG_CATEGORY` | ✅ | User configuration page category |

**Email Notifications**

| Variable | Required | Description |
|----------|----------|-------------|
| `O365_CLIENT_ID` | ❌ | Office 365 client ID for email notifications |
| `O365_CLIENT_SECRET` | ❌ | Office 365 client secret for email notifications |
| `O365_TOKEN` | ❌ | Office 365 token JSON for email notifications |

### USERS_JSON Structure

```json
{
  "123456": {
  "userid": 123456,
  "username": "Username",
  "apprise_urls": ["notification_service_urls"],
  "timezone": "timezone (e.g., Asia/Shanghai)",
  "mention_level": "mention_level (disabled/avatarhover/all)",
  "email": "email_address",
  "enable_wikidot_pm": true,
  "enable_email": true,
  "enable_apprise": true
  }
}
```

#### Mention Levels

- `disabled`: No mention notifications
- `avatarhover`: Only `[[*user]]` syntax mentions (recommended)
- `all`: Both `[[user]]` and `[[*user]]` syntax mentions

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the [GNU Affero General Public License v3.0](https://github.com/Crimone/Scoparia/blob/main/LICENSE).
