# backend/templates/__init__.py
from .uniformlogo import render_uniform_logo

# Simple registry so we can grow later if needed
# Map template IDs → renderer functions
TEMPLATES = {
    "uniformlogo": render_uniform_logo
}

def get_renderer(template_id: str):
    if template_id not in TEMPLATES:
        raise ValueError(f"Unknown template '{template_id}'")
    return TEMPLATES[template_id]

def list_templates():
    """
    Currently not used heavily by your UI (since template <select> is hardcoded),
    but we keep it for future use.
    """
    return {
        "groups": [
            {
                "id": "basic",
                "label": "Basic",
                "templates": [
                    {"id": "uniformlogo", "name": "Uniform Logo"},
                ],
            }
        ]
    }
