"""Version info API endpoints for git branch detection and update checking."""
import os
import subprocess
import logging
from pathlib import Path
from fastapi import APIRouter
from typing import Optional
import requests

logger = logging.getLogger(__name__)
router = APIRouter()

# Get the repo root (backend parent directory)
REPO_ROOT = Path(__file__).parent.parent.parent


def parse_version(version_str: str) -> tuple:
    """
    Parse version string to tuple for comparison.
    Example: 'v1.5.5' -> (1, 5, 5)
    """
    try:
        # Remove 'v' prefix and any suffixes like '-dev'
        clean = version_str.lstrip('v').split('-')[0]
        parts = clean.split('.')
        return tuple(int(p) for p in parts)
    except (ValueError, AttributeError):
        return (0, 0, 0)


def get_current_version() -> str:
    """Get current app version from version.ts"""
    try:
        version_file = REPO_ROOT / "frontend" / "src" / "version.ts"
        if version_file.exists():
            content = version_file.read_text()
            # Extract version from: export const APP_VERSION = 'v1.5.5'
            for line in content.split('\n'):
                if 'APP_VERSION' in line and '=' in line:
                    # Extract the version string
                    parts = line.split("'")
                    if len(parts) >= 2:
                        return parts[1].strip()
        return "unknown"
    except Exception as e:
        logger.error(f"Failed to read version: {e}")
        return "unknown"


def get_git_branch() -> Optional[str]:
    """Get current git branch name."""
    try:
        # Try git command first
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            return branch if branch else None
    except (subprocess.SubprocessTimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.debug(f"Git command failed: {e}")

    # Fallback: read .git/HEAD file
    try:
        git_head = REPO_ROOT / ".git" / "HEAD"
        if git_head.exists():
            content = git_head.read_text().strip()
            if content.startswith('ref: refs/heads/'):
                return content.replace('ref: refs/heads/', '')
    except Exception as e:
        logger.debug(f"Failed to read .git/HEAD: {e}")

    return None


def check_for_updates(current_version: str, branch: str) -> Optional[dict]:
    """
    Check GitHub for newer releases/commits.
    Returns dict with 'available': bool, 'latest_version': str, 'url': str
    """
    try:
        if branch == 'main':
            # Check GitHub releases for main branch
            url = "https://api.github.com/repos/YOUR_USERNAME/simposter/releases/latest"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                latest_tag = data.get('tag_name', '')

                # Compare versions
                current_tuple = parse_version(current_version)
                latest_tuple = parse_version(latest_tag)

                if latest_tuple > current_tuple:
                    return {
                        'available': True,
                        'latest_version': latest_tag,
                        'url': data.get('html_url', '')
                    }
        elif branch and branch != 'main':
            # For dev branches, don't check for updates
            pass

        return {'available': False, 'latest_version': current_version, 'url': ''}
    except Exception as e:
        logger.debug(f"Update check failed: {e}")
        return None


@router.get("/version-info")
async def get_version_info():
    """
    Get version info including branch and update status.

    Returns:
        {
            "version": "v1.5.5",
            "branch": "dev" | "main" | null,
            "display_version": "v1.5.5-dev" | "v1.5.5",
            "update_available": bool,
            "latest_version": "v1.5.6",
            "update_url": "https://github.com/..."
        }
    """
    current_version = get_current_version()
    branch = get_git_branch()

    # Build display version with branch suffix
    display_version = current_version
    if branch and branch != 'main':
        # Only add suffix for non-main branches
        display_version = f"{current_version}-{branch}"

    # Check for updates (only for main branch)
    update_info = None
    if branch == 'main':
        update_info = check_for_updates(current_version, branch)

    return {
        "version": current_version,
        "branch": branch,
        "display_version": display_version,
        "update_available": update_info.get('available', False) if update_info else False,
        "latest_version": update_info.get('latest_version') if update_info else None,
        "update_url": update_info.get('url') if update_info else None
    }
