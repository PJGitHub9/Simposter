from fastapi import APIRouter, HTTPException
from io import BytesIO

from ..config import logger
from ..rendering import render_poster_image
from ..schemas import PreviewRequest

router = APIRouter()

@router.post("/preview")
def api_preview(req: PreviewRequest):
    try:
        img = render_poster_image(
            req.template_id,
            req.background_url,
            req.logo_url,
            req.options or {},
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid background image.")
    except Exception:
        logger.exception("Preview render failed")
        raise HTTPException(status_code=500, detail="Preview failed.")

    buf = BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=95)

    import base64
    return {"image_base64": base64.b64encode(buf.getvalue()).decode()}
