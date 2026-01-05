from fastapi import APIRouter

from app.api.version import API_VERSION

router = APIRouter(tags=["meta"])


@router.get("/meta")
def api_meta():
    return {
        "version": API_VERSION,
        "status": "internal",
        "breaking_changes": "requires new API version",
        # Build identifier injected at deploy time (e.g., short git SHA).
        # Intentionally None until CI/CD or multi-environment deployments exist.
        "build": None,
    }
