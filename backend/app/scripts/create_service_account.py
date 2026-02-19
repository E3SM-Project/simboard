"""Provision a SERVICE_ACCOUNT user and API token via the SimBoard REST API.

Usage:
    uv run python -m scripts.create_service_account \\
        --base-url https://api.simboard.org \\
        --admin-token <ADMIN_TOKEN> \\
        --service-name hpc-ingestion-bot

    uv run python -m scripts.create_service_account \\
        --base-url https://api.simboard.org \\
        --admin-token <ADMIN_TOKEN> \\
        --service-name hpc-ingestion-bot \\
        --expires-in-days 365
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone


def _api_request(
    url: str,
    *,
    method: str = "POST",
    token: str,
    data: dict | None = None,
) -> dict:
    """Make an authenticated API request and return parsed JSON response.

    Parameters
    ----------
    url : str
        Full API URL.
    method : str
        HTTP method.
    token : str
        Bearer token for authentication.
    data : dict | None
        JSON payload.

    Returns
    -------
    dict
        Parsed JSON response.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def create_service_account(
    base_url: str,
    admin_token: str,
    service_name: str,
    expires_in_days: int | None = None,
) -> None:
    """Provision a SERVICE_ACCOUNT user and generate an API token.

    Parameters
    ----------
    base_url : str
        Base URL of the SimBoard API (e.g. https://api.simboard.org).
    admin_token : str
        Admin Bearer token for authentication.
    service_name : str
        Service name (used to derive email as {name}@service.local).
    expires_in_days : int | None
        Optional token expiration in days from now.
    """
    api_base = f"{base_url.rstrip('/')}/api/v1"

    # Step 1: Create or retrieve SERVICE_ACCOUNT user
    try:
        user_data = _api_request(
            f"{api_base}/tokens/service-accounts",
            token=admin_token,
            data={"service_name": service_name},
        )
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Failed to create service account: {e.code} {body}", file=sys.stderr)
        sys.exit(1)

    user_id = user_data["id"]
    email = user_data["email"]

    if user_data.get("created"):
        print(f"Created SERVICE_ACCOUNT user: {email} (id={user_id})")
    else:
        print(f"User '{email}' already exists (id={user_id}). Continuing.")

    # Step 2: Generate API token
    token_payload: dict = {
        "name": f"{service_name}-token",
        "user_id": user_id,
    }
    if expires_in_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        token_payload["expires_at"] = expires_at.isoformat()

    try:
        token_data = _api_request(
            f"{api_base}/tokens",
            token=admin_token,
            data=token_payload,
        )
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Failed to create API token: {e.code} {body}", file=sys.stderr)
        sys.exit(1)

    print(f"Created API token: {token_data['name']} (id={token_data['id']})")
    if token_data.get("expires_at"):
        print(f"Token expires at: {token_data['expires_at']}")
    print()
    print(f"API Token: {token_data['token']}")
    print()
    print("WARNING: Store securely. This token will not be shown again.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provision a SERVICE_ACCOUNT user and API token via REST API."
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="Base URL of the SimBoard API (e.g. https://api.simboard.org)",
    )
    parser.add_argument(
        "--admin-token",
        required=True,
        help="Admin Bearer token for authentication",
    )
    parser.add_argument(
        "--service-name",
        required=True,
        help="Service name (email derived as {name}@service.local)",
    )
    parser.add_argument(
        "--expires-in-days",
        type=int,
        default=None,
        help="Token expiration in days (default: no expiration)",
    )

    args = parser.parse_args()
    create_service_account(
        args.base_url,
        args.admin_token,
        args.service_name,
        args.expires_in_days,
    )


if __name__ == "__main__":
    main()
