"""
Input validation utilities for Simposter API.

Provides validation functions for common input types to prevent
injection attacks and ensure data integrity.
"""

import re
from typing import Optional, List, Any, Dict
from fastapi import HTTPException, status


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


def validate_rating_key(rating_key: str) -> str:
    """
    Validate Plex rating key format.

    Plex rating keys are typically numeric strings or alphanumeric with specific patterns.

    Args:
        rating_key: Plex rating key to validate

    Returns:
        Validated rating key

    Raises:
        HTTPException: If rating key is invalid
    """
    if not rating_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rating key cannot be empty"
        )

    # Allow alphanumeric, hyphens, underscores (Plex rating key patterns)
    if not re.match(r'^[a-zA-Z0-9_-]+$', rating_key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid rating key format. Must be alphanumeric with optional hyphens/underscores."
        )

    # Reasonable length limit (prevent DOS)
    if len(rating_key) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rating key too long (max 100 characters)"
        )

    return rating_key


def validate_tmdb_id(tmdb_id: Any) -> int:
    """
    Validate TMDB ID.

    TMDB IDs are positive integers.

    Args:
        tmdb_id: TMDB ID to validate (int or str)

    Returns:
        Validated TMDB ID as integer

    Raises:
        HTTPException: If TMDB ID is invalid
    """
    try:
        tmdb_id_int = int(tmdb_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TMDB ID must be a valid integer"
        )

    if tmdb_id_int <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TMDB ID must be a positive integer"
        )

    # TMDB IDs are typically < 10 million (as of 2026)
    if tmdb_id_int > 100_000_000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TMDB ID out of valid range"
        )

    return tmdb_id_int


def validate_tvdb_id(tvdb_id: Any) -> int:
    """
    Validate TVDB ID.

    TVDB IDs are positive integers.

    Args:
        tvdb_id: TVDB ID to validate (int or str)

    Returns:
        Validated TVDB ID as integer

    Raises:
        HTTPException: If TVDB ID is invalid
    """
    try:
        tvdb_id_int = int(tvdb_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TVDB ID must be a valid integer"
        )

    if tvdb_id_int <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TVDB ID must be a positive integer"
        )

    # TVDB IDs are typically < 1 million
    if tvdb_id_int > 10_000_000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TVDB ID out of valid range"
        )

    return tvdb_id_int


def validate_season_number(season: Any) -> int:
    """
    Validate season number.

    Season numbers are non-negative integers (0 = specials).

    Args:
        season: Season number to validate

    Returns:
        Validated season number

    Raises:
        HTTPException: If season number is invalid
    """
    try:
        season_int = int(season)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Season number must be a valid integer"
        )

    if season_int < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Season number cannot be negative"
        )

    # Reasonable upper limit (prevent DOS)
    if season_int > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Season number out of valid range (max 500)"
        )

    return season_int


def validate_library_id(library_id: str) -> str:
    """
    Validate Plex library ID.

    Library IDs are typically numeric strings.

    Args:
        library_id: Library ID to validate

    Returns:
        Validated library ID

    Raises:
        HTTPException: If library ID is invalid
    """
    if not library_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Library ID cannot be empty"
        )

    # Allow alphanumeric and hyphens
    if not re.match(r'^[a-zA-Z0-9-]+$', library_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid library ID format"
        )

    if len(library_id) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Library ID too long (max 50 characters)"
        )

    return library_id


def validate_template_id(template_id: str) -> str:
    """
    Validate template ID.

    Template IDs should be alphanumeric with underscores.

    Args:
        template_id: Template ID to validate

    Returns:
        Validated template ID

    Raises:
        HTTPException: If template ID is invalid
    """
    if not template_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template ID cannot be empty"
        )

    # Allow alphanumeric and underscores
    if not re.match(r'^[a-z0-9_]+$', template_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid template ID format. Must be lowercase alphanumeric with underscores."
        )

    if len(template_id) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template ID too long (max 50 characters)"
        )

    return template_id


def validate_preset_id(preset_id: str) -> str:
    """
    Validate preset ID.

    Preset IDs should be alphanumeric with hyphens and underscores.

    Args:
        preset_id: Preset ID to validate

    Returns:
        Validated preset ID

    Raises:
        HTTPException: If preset ID is invalid
    """
    if not preset_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Preset ID cannot be empty"
        )

    # Allow alphanumeric, hyphens, underscores
    if not re.match(r'^[a-zA-Z0-9_-]+$', preset_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid preset ID format. Must be alphanumeric with hyphens/underscores."
        )

    if len(preset_id) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Preset ID too long (max 100 characters)"
        )

    return preset_id


def validate_url(url: str, allow_data_uri: bool = False) -> str:
    """
    Validate URL format.

    Args:
        url: URL to validate
        allow_data_uri: Whether to allow data: URIs

    Returns:
        Validated URL

    Raises:
        HTTPException: If URL is invalid
    """
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL cannot be empty"
        )

    # Check for data URI
    if url.startswith("data:"):
        if not allow_data_uri:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Data URIs are not allowed"
            )
        # Basic data URI validation
        if not re.match(r'^data:image/[a-z]+;base64,', url):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid data URI format"
            )
        return url

    # Validate HTTP/HTTPS URLs
    if not re.match(r'^https?://', url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL must start with http:// or https://"
        )

    # Prevent SSRF: block private IPs and localhost (except for Plex servers)
    # Allow private network URLs from Plex servers (port 32400) since many users
    # run Plex on their local network and need to access poster/logo URLs
    private_patterns = [
        r'localhost',
        r'127\.0\.0\.',
        r'192\.168\.',
        r'10\.',
        r'172\.(1[6-9]|2[0-9]|3[0-1])\.',
    ]

    for pattern in private_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            # Allow private network URLs if they appear to be from Plex or this app
            # Common patterns: port 32400, .plex.direct domain, localhost, Plex metadata paths
            is_plex_url = (
                'localhost' in url or
                '127.0.0.1' in url or
                ':32400' in url or
                '.plex.direct' in url or
                'X-Plex-Token' in url or  # URL contains Plex auth token
                '/library/metadata/' in url  # Plex metadata path (may be behind reverse proxy)
            )
            if not is_plex_url:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Private network URLs are not allowed"
                )

    # Length check
    if len(url) > 2048:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL too long (max 2048 characters)"
        )

    return url


def validate_file_path(file_path: str, allowed_dirs: Optional[List[str]] = None) -> str:
    """
    Validate file path to prevent directory traversal attacks.

    Args:
        file_path: File path to validate
        allowed_dirs: List of allowed directory prefixes

    Returns:
        Validated file path

    Raises:
        HTTPException: If file path is invalid or outside allowed directories
    """
    if not file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File path cannot be empty"
        )

    # Check for directory traversal attempts
    if ".." in file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Directory traversal not allowed"
        )

    # Check for absolute paths (should be relative or in allowed dirs)
    if file_path.startswith("/") or (len(file_path) > 1 and file_path[1] == ":"):
        if allowed_dirs:
            # Verify path starts with one of the allowed directories
            if not any(file_path.startswith(allowed_dir) for allowed_dir in allowed_dirs):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File path not in allowed directories"
                )

    # Check for null bytes (path injection)
    if "\x00" in file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Null bytes not allowed in file path"
        )

    return file_path


def validate_labels(labels: List[str]) -> List[str]:
    """
    Validate list of Plex labels.

    Args:
        labels: List of label strings

    Returns:
        Validated labels

    Raises:
        HTTPException: If labels are invalid
    """
    if not isinstance(labels, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Labels must be a list"
        )

    # Limit number of labels (prevent DOS)
    if len(labels) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many labels (max 50)"
        )

    validated = []
    for label in labels:
        if not isinstance(label, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each label must be a string"
            )

        # Trim whitespace
        label = label.strip()

        if not label:
            continue  # Skip empty labels

        # Length check
        if len(label) > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Label too long: '{label[:50]}...' (max 100 characters)"
            )

        # Basic sanitization: alphanumeric, spaces, hyphens, underscores
        if not re.match(r'^[a-zA-Z0-9 _-]+$', label):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid label format: '{label}'. Must be alphanumeric with spaces, hyphens, underscores."
            )

        validated.append(label)

    return validated


def validate_options(options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate template options dictionary.

    Args:
        options: Options dictionary

    Returns:
        Validated options

    Raises:
        HTTPException: If options are invalid
    """
    if not isinstance(options, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Options must be a dictionary"
        )

    # Limit size (prevent DOS)
    if len(options) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many options (max 100)"
        )

    # Validate specific option types
    numeric_options = [
        "posterZoom", "posterShiftY", "matteHeight", "fadeHeight",
        "vignette", "grain", "wash", "logoScale", "logoOffsetY",
        "fontSize", "letterSpacing", "lineHeight", "positionY",
        "shadowBlur", "shadowOffsetX", "shadowOffsetY", "shadowOpacity",
        "strokeWidth", "cornerRadius", "borderWidth"
    ]

    boolean_options = [
        "textOverlayEnabled", "shadowEnabled", "strokeEnabled",
        "roundedCorners", "borderEnabled", "uniform_override"
    ]

    string_options = [
        "logoMode", "logoHex", "matteColor", "customText",
        "fontFamily", "fontWeight", "textColor", "textAlign",
        "textTransform", "shadowColor", "strokeColor", "borderColor"
    ]

    for key, value in options.items():
        # Validate key format (prevent injection)
        if not re.match(r'^[a-zA-Z0-9_]+$', key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid option key: '{key}'"
            )

        # Type validation
        if key in numeric_options:
            if not isinstance(value, (int, float)):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Option '{key}' must be numeric"
                )
        elif key in boolean_options:
            if not isinstance(value, bool):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Option '{key}' must be boolean"
                )
        elif key in string_options:
            if not isinstance(value, str):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Option '{key}' must be string"
                )
            # Length check for strings
            if len(value) > 500:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Option '{key}' too long (max 500 characters)"
                )

    return options
