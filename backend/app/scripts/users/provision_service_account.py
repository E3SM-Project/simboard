"""
Provision a SERVICE_ACCOUNT user and API token via the SimBoard REST API.

Usage:
    uv run python -m app.scripts.provision_service_account \
        --service-name perlmutter-ingestion

Optional:
    --base-url https://api.simboard.org
    --admin-email admin@simboard.org
    --expires-in-days 365
"""

import argparse
import getpass
import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.api.version import API_BASE

# DEFAULT_BASE_URL = f"https://{settings.domain}:8000"
DEFAULT_BASE_URL = "https://127.0.0.1:8000"
LOCAL_CERT_PATH = Path(__file__).resolve().parents[4] / "certs" / "local.crt"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provision a SERVICE_ACCOUNT and API token."
    )
    parser.add_argument("--service-name", required=True)
    parser.add_argument("--base-url", required=False)
    parser.add_argument("--admin-email", required=False)
    parser.add_argument("--expires-in-days", type=int, default=None)

    args = parser.parse_args()

    base_url = args.base_url or DEFAULT_BASE_URL
    admin_email = args.admin_email or input("Admin email: ").strip()
    admin_password = getpass.getpass("Admin password: ")

    print("Authenticating admin...")

    jwt_token = login_and_get_token(base_url, admin_email, admin_password)

    print("Authenticated.")
    print("Provisioning service account...")

    provision(
        base_url,
        jwt_token,
        args.service_name,
        args.expires_in_days,
    )


def login_and_get_token(base_url: str, email: str, password: str) -> str:
    login_url = f"{base_url.rstrip('/')}{API_BASE}/auth/jwt/login"

    form_data = urllib.parse.urlencode(
        {"username": email, "password": password}
    ).encode()

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    req = urllib.request.Request(login_url, data=form_data, headers=headers)

    context = _build_ssl_context(login_url)

    try:
        with urllib.request.urlopen(req, context=context) as resp:
            payload = json.loads(resp.read())
            return payload["access_token"]
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Authentication failed ({e.code}): {body}", file=sys.stderr)
        sys.exit(1)


def provision(
    base_url: str,
    jwt_token: str,
    service_name: str,
    expires_in_days: int | None,
) -> None:
    api_base = f"{base_url.rstrip('/')}{API_BASE}"

    user_data = _api_request(
        f"{api_base}/tokens/service-accounts",
        jwt_token,
        {"service_name": service_name},
    )

    user_id = user_data["id"]
    email = user_data["email"]

    if user_data.get("created"):
        print(f"Created SERVICE_ACCOUNT: {email}")
    else:
        print(f"Using existing SERVICE_ACCOUNT: {email}")

    token_payload = {
        "name": f"{service_name}-token",
        "user_id": user_id,
    }

    if expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        token_payload["expires_at"] = expires_at.isoformat()

    token_data = _api_request(
        f"{api_base}/tokens",
        jwt_token,
        token_payload,
    )

    print()
    print("API Token:")
    print(token_data["token"])
    print()
    print("WARNING: Store securely. This token will not be shown again.")


def _api_request(url: str, token: str, data: dict) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    request_body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=request_body, headers=headers)

    context = _build_ssl_context(url)

    try:
        with urllib.request.urlopen(req, context=context) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"API error ({e.code}): {error_body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        sys.exit(1)


def _build_ssl_context(url: str) -> ssl.SSLContext | None:
    parsed = urlparse(url)

    if parsed.scheme != "https":
        return None

    hostname = parsed.hostname

    if hostname in LOCAL_HOSTS:
        if LOCAL_CERT_PATH.exists():
            return ssl.create_default_context(cafile=str(LOCAL_CERT_PATH))
        else:
            raise RuntimeError(f"Local certificate not found at {LOCAL_CERT_PATH}")

    return ssl.create_default_context()


if __name__ == "__main__":
    main()
