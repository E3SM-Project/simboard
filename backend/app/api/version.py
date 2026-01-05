API_PREFIX = "/api"

# NOTE: Any backward-incompatible response shape change requires a new API version (v2+).
API_VERSION = "v1"

API_BASE = f"{API_PREFIX}/{API_VERSION}"

__all__ = ["API_BASE", "API_VERSION"]
