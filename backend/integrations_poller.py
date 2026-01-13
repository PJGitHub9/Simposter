"""
Integrations removed: Radarr/Sonarr/Tautulli polling deprecated.
This module is retained as a no-op for compatibility.
"""
from typing import Dict, List, Optional, Any


def get_last_poll_time(instance_type: str, instance_id: str) -> Optional[str]:
    return None


def set_last_poll_time(instance_type: str, instance_id: str, timestamp: str) -> None:
    pass


def poll_radarr_instance(instance: Dict[str, Any], library_mappings: List[Dict[str, Any]], tag_mappings: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    return []


def poll_sonarr_instance(instance: Dict[str, Any], library_mappings: List[Dict[str, Any]], tag_mappings: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    return []


def poll_all_integrations() -> Dict[str, List[Dict[str, Any]]]:
    return {"movies": [], "tv_shows": []}


def generate_poster_for_content(content: Dict[str, Any]) -> bool:
    return False


def process_new_content(content_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"success": 0, "failed": 0, "total": 0}

