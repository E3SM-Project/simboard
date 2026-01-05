from fastapi import APIRouter

from app.api.version import API_VERSION

router = APIRouter(tags=["meta"])


@router.get("/meta")
def api_meta():
    return {
        "version": API_VERSION,
        "status": "internal",
        "breaking_changes": (
            "No breaking changes are currently declared. This field will describe "
            "required upgrade paths when incompatible API versions are introduced."
        ),
        # Build identifier injected at deploy time (e.g., short git SHA).
        # Intentionally None until CI/CD or multi-environment deployments exist.
        "build": None,
    }
