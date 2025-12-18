from fastapi import APIRouter, Query, HTTPException
from ..config import logger
from .. import tmdb_client, fanart_client

router = APIRouter()


@router.get("/test-tmdb")
async def test_tmdb_api_key(api_key: str = Query(..., description="TMDb API key to test")):
    """Test a TMDb API key by making a simple API call."""
    try:
        import requests

        # Test with a simple movie lookup (The Matrix - ID: 603)
        # TMDb API v3 uses api_key query parameter
        url = f"https://api.themoviedb.org/3/movie/603"
        params = {"api_key": api_key}

        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            return {
                "status": "ok",
                "example": f"{data.get('title', 'Unknown')} ({data.get('release_date', '')[:4]})"
            }
        elif response.status_code == 401:
            return {
                "status": "error",
                "error": "Invalid API key"
            }
        else:
            return {
                "status": "error",
                "error": f"API returned status {response.status_code}"
            }
    except Exception as e:
        logger.error(f"[TEST_TMDB] Error testing API key: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/test-tvdb")
async def test_tvdb_api_key(api_key: str = Query(..., description="TVDB API key to test")):
    """Test a TVDB API key by performing a login call."""
    try:
        from .. import tvdb_client
        result = tvdb_client.test_tvdb_key(api_key)
        return result
    except Exception as e:
        logger.error(f"[TEST_TVDB] Error testing API key: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/test-fanart")
async def test_fanart_api_key(payload: dict):
    """Test a Fanart.tv API key by making a simple API call (body, so key won't hit access logs)."""
    try:
        import requests

        api_key = str(payload.get("api_key") or "")
        if not api_key:
            return {"status": "error", "error": "API key required"}

        # Test with The Matrix (TMDb ID: 603)
        test_tmdb_id = 603
        url = f"https://webservice.fanart.tv/v3/movies/{test_tmdb_id}"
        params = {"api_key": api_key}

        response = requests.get(url, params=params, timeout=10)

        redacted = api_key[:6] + "..." if len(api_key) > 6 else "***"
        logger.info("[TEST_FANART] status=%s tmdb_id=%s key=%s", response.status_code, test_tmdb_id, redacted)

        if response.status_code == 200:
            data = response.json()
            logo_count = 0
            logo_count += len(data.get("hdmovielogo", []))
            logo_count += len(data.get("movielogo", []))
            logo_count += len(data.get("clearlogo", []))

            return {
                "status": "ok",
                "logo_count": logo_count,
                "message": "API key valid"
            }
        elif response.status_code == 401:
            return {
                "status": "error",
                "error": "Invalid API key"
            }
        elif response.status_code == 404:
            return {
                "status": "ok",
                "logo_count": 0,
                "message": "API key valid (no logos for test movie)"
            }
        else:
            return {
                "status": "error",
                "error": f"API returned status {response.status_code}"
            }
    except Exception as e:
        logger.error(f"[TEST_FANART] Error testing API key: {e}")
        return {
            "status": "error",
            "error": str(e)
        }
