# backend/api/templates.py
from fastapi import APIRouter

from ..templates import list_templates

router = APIRouter()


@router.get("/templates/list")
def api_list_templates():
    """
    Returns available templates in a structured format.
    """
    data = list_templates()
    # Flatten the groups structure for easier frontend consumption
    templates = []
    for group in data.get("groups", []):
        templates.extend(group.get("templates", []))

    return {"templates": templates}
