# API Token Authentication Guide

## Overview

API token authentication enables secure programmatic access to ingestion endpoints from external HPC systems without requiring browser-based GitHub OAuth flows.

## Architecture

### Authentication Flow

1. **OAuth First**: The system first attempts OAuth/JWT authentication (existing behavior)
2. **API Token Fallback**: If OAuth fails, the system checks for a Bearer token in the Authorization header
3. **Unified Resolution**: Both methods resolve through the same `current_active_user` dependency

### Security Features

- **SHA256 Token Hashing**: Raw tokens are hashed before storage
- **Constant-Time Comparison**: Token validation uses `hmac.compare_digest` to prevent timing attacks
- **One-Time Exposure**: Raw tokens are returned only once at creation time
- **32+ Bytes Entropy**: Tokens are generated using `secrets.token_urlsafe(32)`
- **Token Prefix**: All tokens start with `sbk_` for operational clarity
- **Expiration Support**: Tokens can have optional expiration dates
- **Revocation Support**: Tokens can be revoked by administrators

## Usage

### Creating an API Token (Admin Only)

```bash
curl -X POST https://api.simboard.org/api/v1/tokens \
  -H "Authorization: Bearer <ADMIN_TOKEN_OR_OAUTH>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "HPC Ingestion Bot",
    "user_id": "service-account-uuid",
    "expires_at": "2027-12-31T23:59:59Z"
  }'
```

**Response:**
```json
{
  "id": "token-uuid",
  "name": "HPC Ingestion Bot",
  "token": "sbk_xxxxxxxxxxxxxxxxxxxxx",
  "created_at": "2026-02-19T00:00:00Z",
  "expires_at": "2027-12-31T23:59:59Z"
}
```

⚠️ **Important**: Save the `token` value immediately. It will never be shown again.

### Using an API Token for Ingestion

#### Path-Based Ingestion

```bash
curl -X POST https://api.simboard.org/api/v1/ingestions/from-path \
  -H "Authorization: Bearer sbk_xxxxxxxxxxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "archive_path": "/hpc/storage/simulations/archive.tar.gz",
    "machine_name": "perlmutter",
    "hpc_username": "johndoe"
  }'
```

#### Upload-Based Ingestion

```bash
curl -X POST https://api.simboard.org/api/v1/ingestions/from-upload \
  -H "Authorization: Bearer sbk_xxxxxxxxxxxxxxxxxxxxx" \
  -F "file=@archive.tar.gz" \
  -F "machine_name=perlmutter" \
  -F "hpc_username=johndoe"
```

### Listing API Tokens (Admin Only)

```bash
curl -X GET https://api.simboard.org/api/v1/tokens \
  -H "Authorization: Bearer <ADMIN_TOKEN_OR_OAUTH>"
```

### Revoking an API Token (Admin Only)

```bash
curl -X DELETE https://api.simboard.org/api/v1/tokens/{token_id} \
  -H "Authorization: Bearer <ADMIN_TOKEN_OR_OAUTH>"
```

## Service Accounts

### Creating a Service Account User

Service accounts are users with `role=SERVICE_ACCOUNT`, modeled through the existing `UserRole` enum. No separate boolean or identity flag is used.

1. Create a user via the admin panel or database with `role=SERVICE_ACCOUNT`
2. Create API tokens associated with this user

**Constraints:**
- `SERVICE_ACCOUNT` users authenticate via API tokens only.
- They cannot log in via GitHub OAuth.
- Only `SERVICE_ACCOUNT` users may use Bearer token authentication.

### Recommended Service Accounts

- `hpc-ingestion-bot@simboard.org` - For HPC ingestion jobs
- `ci-integration-bot@simboard.org` - For CI/CD pipelines
- `monitoring-bot@simboard.org` - For monitoring and health checks

## HPC Username Provenance

The `hpc_username` field captures the identity of the user who triggered the ingestion job on the HPC system. This is:

- **Trusted Input**: Provided by trusted HPC ingestion jobs
- **Informational Only**: Used for provenance and future ownership enforcement
- **Not Validated**: Not checked against GitHub or other authentication systems
- **Optional**: Can be omitted if not applicable

## Examples

### Python Example

```python
import requests

API_BASE = "https://api.simboard.org/api/v1"
API_TOKEN = "sbk_xxxxxxxxxxxxxxxxxxxxx"

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

# Ingest from path
response = requests.post(
    f"{API_BASE}/ingestions/from-path",
    headers=headers,
    json={
        "archive_path": "/path/to/archive.tar.gz",
        "machine_name": "perlmutter",
        "hpc_username": "johndoe"
    }
)

print(response.json())
```

### Bash Script Example

```bash
#!/bin/bash

API_BASE="https://api.simboard.org/api/v1"
API_TOKEN="sbk_xxxxxxxxxxxxxxxxxxxxx"
ARCHIVE_PATH="/hpc/storage/archive.tar.gz"
MACHINE="perlmutter"
HPC_USER="${USER}"

curl -X POST "${API_BASE}/ingestions/from-path" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"archive_path\": \"${ARCHIVE_PATH}\",
    \"machine_name\": \"${MACHINE}\",
    \"hpc_username\": \"${HPC_USER}\"
  }"
```

## Database Schema

### ApiToken Model

```python
class ApiToken(Base):
    id: UUID                    # Primary key
    name: str                   # Human-readable identifier
    token_hash: str            # SHA256 hash of raw token
    user_id: UUID              # Foreign key to users.id
    created_at: datetime       # Token creation timestamp
    expires_at: datetime | None # Optional expiration
    revoked: bool              # Revocation flag
```

### User Model Updates

- `UserRole` enum extended with `SERVICE_ACCOUNT`
- API tokens are associated only with users whose role is `SERVICE_ACCOUNT`

### Simulation Model Updates

- Added `hpc_username: str | None` field

## Migration

Run the migration to add API token support:

```bash
make backend-upgrade
```

This will:
1. Add `SERVICE_ACCOUNT` enum value to `user_role` type
2. Add `hpc_username` column to `simulations` table
3. Create `api_tokens` table with proper indexes and constraints

## Testing

```bash
# Run all token-related tests
cd backend && uv run pytest tests/features/user/test_token_auth.py -v
cd backend && uv run pytest tests/features/user/test_token_api.py -v
cd backend && uv run pytest tests/features/ingestion/test_token_ingestion.py -v
```

## Troubleshooting

### Token Not Working

1. Check if token is revoked: `GET /api/v1/tokens`
2. Check if token is expired
3. Verify token format: Must start with `sbk_`
4. Ensure Bearer scheme: `Authorization: Bearer sbk_xxx`
5. Check that associated user is active and has `role=SERVICE_ACCOUNT`

### 403 Forbidden

- Only administrators can create, list, and revoke tokens
- Verify user role is `ADMIN`

### 401 Unauthorized

- Token may be invalid, revoked, or expired
- Check Authorization header format
- Verify the token is associated with a `SERVICE_ACCOUNT` user
- Verify OAuth is not interfering (OAuth takes precedence)

## References

- Token Auth Implementation: `backend/app/features/user/token_auth.py`
- Token API Endpoints: `backend/app/features/user/token_api.py`
- Authentication Dependency: `backend/app/features/user/manager.py`
- Migration: `backend/migrations/versions/20260219_000000_add_api_token_authentication.py`
