# Security: API Key Protection in Logging

## Overview
This document outlines the security measures in place to prevent API keys and tokens from appearing in logs.

## Sensitive Data Types
The following data types must NEVER appear in logs unmasked:
- Plex Token (`PLEX_TOKEN`)
- TMDb API Key (`TMDB_API_KEY`)
- TVDb API Key (`TVDB_API_KEY`)
- Fanart.tv API Key (`FANART_API_KEY`)
<!-- Integrations removed: Radarr/Sonarr/Tautulli -->

## Protection Mechanisms

### 1. Utility Function (`backend/config.py`)
```python
def mask_sensitive(value: str, visible_chars: int = 4) -> str:
    """
    Mask sensitive data like API keys for logging.
    Shows only the last `visible_chars` characters.

    Examples:
        mask_sensitive("abcdef123456") -> "********3456"
        mask_sensitive("short") -> "****t"
    """
```

### 2. HTTP Response Redaction (`backend/config.py:redact_log_record`)
- Automatically redacts tokens from HTTP response logs
- Replaces full tokens with first 4 chars + `***REDACTED***`
- Applies to:
  - PLEX_TOKEN
  - TMDB_API_KEY

### 3. Fanart Client (`backend/fanart_client.py`)
- Masks API keys before logging
- Shows only first 8 characters + "..."

<!-- Integration testing removed -->

<!-- Integration polling removed -->

<!-- Webhooks removed -->

## Guidelines for Developers

### DO ✅
- Use `mask_sensitive()` when logging any user-provided credentials
- Log only non-sensitive identifiers (URLs, instance names, IDs)
- Use generic error messages that don't reveal sensitive data

### DON'T ❌
- Never use `logger.debug()`, `logger.info()`, or any logger with raw API keys
- Never log request/response objects that might contain auth headers
- Never log full URLs that contain API keys as query parameters

### Example - Correct
```python
from backend.config import mask_sensitive

api_key = instance.get("apiKey")
logger.info(f"Testing connection with key: {mask_sensitive(api_key)}")
# Output: Testing connection with key: ********3a7f
```

### Example - Incorrect ❌
```python
api_key = instance.get("apiKey")
logger.info(f"Testing connection with key: {api_key}")
# Output: Testing connection with key: 1234567890abcdef (EXPOSED!)
```

## Verification
To verify no API keys are logged:
1. Enable DEBUG logging
2. Perform all integration tests
3. Search logs for patterns:
   - Full token/key strings
   - Authorization headers
   - Query parameters with keys

## Related Files
- `backend/config.py` - Main redaction logic
- `backend/fanart_client.py` - Fanart API key masking
<!-- Integration files removed -->

## Updates
- 2026-01-13: Added `mask_sensitive()` utility function
- 2026-01-13: Documented all protection mechanisms
