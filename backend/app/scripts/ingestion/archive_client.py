"""HTTP client, remote state, persistence, and retries for archive ingestion."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from app.api.version import API_BASE
from app.scripts.ingestion.archive_ingestor_core import (
    DISCOVERY_RESULT_BATCH_SIZE,
    STATE_VERSION,
    ExecutionDiscoveryResult,
    IngestionAttemptResult,
    IngestionCandidate,
    IngestionRequestError,
    IngestionRequestResponse,
    IngestorConfig,
    _case_state_processed_ids,
    _compute_case_fingerprint,
    _deduplicate_discovery_results,
    _is_transient_status,
    _log_event,
    _utc_now_iso,
)


def _build_endpoint_url(config: IngestorConfig) -> str:
    """Build the path-based ingestion endpoint URL from runtime config."""
    return f"{_normalized_api_base_url(config.api_base_url)}/ingestions/from-path"


def _build_state_endpoint_url(config: IngestorConfig) -> str:
    """Build the ingestion-state endpoint URL from runtime config."""
    return f"{_normalized_api_base_url(config.api_base_url)}/ingestions/state"


def _build_archive_checkpoints_endpoint_url(config: IngestorConfig) -> str:
    """Build archive checkpoint read/write endpoint URL."""
    return f"{_normalized_api_base_url(config.api_base_url)}/ingestions/archive-checkpoints"


def _build_discovery_results_endpoint_url(config: IngestorConfig) -> str:
    """Build discovery-result persistence endpoint URL."""
    return (
        f"{_normalized_api_base_url(config.api_base_url)}/ingestions/discovery-results"
    )


def _normalized_api_base_url(api_base_url: str) -> str:
    """Normalize a SimBoard base URL to include ``API_BASE``."""
    stripped = api_base_url.rstrip("/")
    if stripped.endswith(API_BASE):
        return stripped

    return f"{stripped}{API_BASE}"


def _fetch_ingestion_state(
    endpoint_url: str,
    api_token: str,
    machine_name: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Fetch database-backed ingestion state from SimBoard API."""
    query = urllib.parse.urlencode({"machine_name": machine_name})
    request = urllib.request.Request(
        f"{endpoint_url}?{query}",
        headers={"Authorization": f"Bearer {api_token}"},
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
            try:
                parsed_body = json.loads(raw_body) if raw_body else {}
            except json.JSONDecodeError as exc:
                raise IngestionRequestError(
                    f"Invalid JSON response: {exc}",
                    status_code=response.status,
                    transient=False,
                ) from exc

            return _normalize_remote_state(parsed_body)
    except urllib.error.HTTPError as exc:
        response_text = exc.read().decode("utf-8", errors="replace")
        raise IngestionRequestError(
            f"HTTP {exc.code}: {response_text}",
            status_code=exc.code,
            transient=_is_transient_status(exc.code),
        ) from exc
    except urllib.error.URLError as exc:
        raise IngestionRequestError(
            f"URL error: {exc.reason}", status_code=None, transient=True
        ) from exc
    except TimeoutError as exc:
        raise IngestionRequestError(
            "Request timed out", status_code=None, transient=True
        ) from exc


def _normalize_remote_state(body: dict[str, Any]) -> dict[str, Any]:
    """Normalize API state response into runner-compatible structure."""
    if not isinstance(body, dict):
        raise IngestionRequestError(
            "Invalid ingestion state response payload.",
            status_code=None,
            transient=False,
        )

    raw_cases = body.get("cases", {})
    if not isinstance(raw_cases, dict):
        raw_cases = {}

    cases: dict[str, dict[str, Any]] = {}
    for case_path, case_state in raw_cases.items():
        if not isinstance(case_path, str) or not isinstance(case_state, dict):
            continue

        processed_execution_ids = sorted(_case_state_processed_ids(case_state))
        fingerprint = case_state.get("fingerprint")
        if not isinstance(fingerprint, str):
            fingerprint = _compute_case_fingerprint(processed_execution_ids)

        cases[case_path] = {
            "processed_execution_ids": processed_execution_ids,
            "fingerprint": fingerprint,
        }

    raw_discovery_results = body.get("discovery_results", {})
    discovery_results: dict[str, list[dict[str, str]]] = {}
    if isinstance(raw_discovery_results, dict):
        for case_identity, raw_results in raw_discovery_results.items():
            if not isinstance(case_identity, str) or not isinstance(raw_results, list):
                continue
            normalized_results = [
                {
                    "case_identity": case_identity,
                    "execution_id": result["execution_id"],
                    "outcome": result["outcome"],
                }
                for result in raw_results
                if isinstance(result, dict)
                and isinstance(result.get("execution_id"), str)
                and result.get("outcome")
                in {"accepted", "rejected_incomplete", "rejected_invalid"}
            ]
            if normalized_results:
                discovery_results[case_identity] = normalized_results

    return {
        "version": STATE_VERSION,
        "cases": cases,
        "discovery_results": discovery_results,
        "updated_at": _utc_now_iso(),
    }


def _fetch_archive_checkpoints(
    endpoint_url: str,
    api_token: str,
    machine_name: str,
    archive_name: str,
    *,
    archive_start: str | None,
    archive_end: str | None,
    timeout_seconds: int,
) -> set[str]:
    """Fetch completed immutable snapshot keys from SimBoard."""
    query_values = {"machine_name": machine_name, "archive_name": archive_name}
    if archive_start is not None:
        query_values["archive_start"] = archive_start
    if archive_end is not None:
        query_values["archive_end"] = archive_end
    request = urllib.request.Request(
        f"{endpoint_url}?{urllib.parse.urlencode(query_values)}",
        headers={"Authorization": f"Bearer {api_token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
            body = json.loads(raw_body) if raw_body else {}
    except urllib.error.HTTPError as exc:
        response_text = exc.read().decode("utf-8", errors="replace")
        raise IngestionRequestError(
            f"HTTP {exc.code}: {response_text}",
            status_code=exc.code,
            transient=_is_transient_status(exc.code),
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise IngestionRequestError(
            f"Checkpoint request failed: {exc}",
            status_code=None,
            transient=True,
        ) from exc
    except json.JSONDecodeError as exc:
        raise IngestionRequestError(
            f"Invalid checkpoint response: {exc}",
            status_code=None,
            transient=False,
        ) from exc

    if not isinstance(body, dict) or not isinstance(body.get("snapshots"), list):
        raise IngestionRequestError(
            "Invalid checkpoint response payload.",
            status_code=None,
            transient=False,
        )
    snapshots = body["snapshots"]
    return {
        f"{snapshot['archive_month']}/{snapshot['snapshot_name']}"
        for snapshot in snapshots
        if isinstance(snapshot, dict)
        and isinstance(snapshot.get("archive_month"), str)
        and isinstance(snapshot.get("snapshot_name"), str)
    }


def _persist_discovery_results_with_retries(
    results: list[ExecutionDiscoveryResult],
    endpoint_url: str,
    api_token: str,
    machine_name: str,
    *,
    max_attempts: int,
    timeout_seconds: int,
    sleep_fn: Callable[[float], None],
    post_request_fn: Callable[..., IngestionRequestResponse] | None = None,
) -> bool:
    """Persist discovery results in bounded batches before any ingestion."""
    deduplicated_results = _deduplicate_discovery_results(results)
    if not deduplicated_results:
        return True
    if post_request_fn is None:
        post_request_fn = _post_discovery_results_request

    for offset in range(0, len(deduplicated_results), DISCOVERY_RESULT_BATCH_SIZE):
        batch = deduplicated_results[offset : offset + DISCOVERY_RESULT_BATCH_SIZE]
        for attempt in range(1, max_attempts + 1):
            try:
                post_request_fn(
                    endpoint_url,
                    api_token,
                    machine_name,
                    results=batch,
                    timeout_seconds=timeout_seconds,
                )
                break
            except IngestionRequestError as exc:
                retrying = exc.transient and attempt < max_attempts
                _log_event(
                    "discovery_results_persistence_failed",
                    {
                        "attempt": attempt,
                        "status_code": exc.status_code,
                        "transient": exc.transient,
                        "retrying": retrying,
                        "error": str(exc),
                    },
                )
                if not retrying:
                    return False
                sleep_fn(2 ** (attempt - 1))

    return True


def _post_discovery_results_request(
    endpoint_url: str,
    api_token: str,
    machine_name: str,
    *,
    results: list[ExecutionDiscoveryResult],
    timeout_seconds: int,
) -> IngestionRequestResponse:
    """POST one JSON discovery-result batch."""
    body = json.dumps(
        {
            "machine_name": machine_name,
            "results": [
                {
                    "case_identity": result.case_identity,
                    "execution_id": result.execution_id,
                    "outcome": result.outcome,
                }
                for result in results
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint_url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
            parsed_body = json.loads(raw_body) if raw_body else {}
            return {"status_code": response.status, "body": parsed_body}
    except urllib.error.HTTPError as exc:
        response_text = exc.read().decode("utf-8", errors="replace")
        raise IngestionRequestError(
            f"HTTP {exc.code}: {response_text}",
            status_code=exc.code,
            transient=_is_transient_status(exc.code),
        ) from exc
    except urllib.error.URLError as exc:
        raise IngestionRequestError(
            f"URL error: {exc.reason}",
            status_code=None,
            transient=True,
        ) from exc
    except TimeoutError as exc:
        raise IngestionRequestError(
            "Request timed out",
            status_code=None,
            transient=True,
        ) from exc


def _ingest_case_with_retries(
    candidate: IngestionCandidate,
    endpoint_url: str,
    api_token: str,
    machine_name: str,
    max_attempts: int,
    timeout_seconds: int,
    sleep_fn: Callable[[float], None],
    post_request_fn: Callable[..., IngestionRequestResponse] | None = None,
) -> IngestionAttemptResult:
    """Ingest one case with exponential-backoff retries."""
    if post_request_fn is None:
        post_request_fn = _post_ingestion_request

    for attempt in range(1, max_attempts + 1):
        try:
            response = post_request_fn(
                endpoint_url,
                api_token,
                candidate.case_path,
                machine_name,
                processed_execution_ids=candidate.new_execution_ids,
                timeout_seconds=timeout_seconds,
            )
            body = response.get("body")

            if not isinstance(body, dict):
                body = {}

            return {
                "ok": True,
                "attempts": attempt,
                "status_code": response.get("status_code"),
                "body": body,
                "error": None,
            }
        except IngestionRequestError as exc:
            should_retry = exc.transient and attempt < max_attempts

            _log_event(
                "case_ingestion_request_failed",
                {
                    "case_path": candidate.case_path,
                    "attempt": attempt,
                    "status_code": exc.status_code,
                    "transient": exc.transient,
                    "retrying": should_retry,
                    "error": str(exc),
                },
            )

            if should_retry:
                backoff_seconds = 2 ** (attempt - 1)
                sleep_fn(backoff_seconds)
                continue

            return {
                "ok": False,
                "attempts": attempt,
                "status_code": exc.status_code,
                "body": None,
                "error": str(exc),
            }

    return {
        "ok": False,
        "attempts": max_attempts,
        "status_code": None,
        "body": None,
        "error": "Exhausted retries",
    }


def _post_ingestion_request(
    endpoint_url: str,
    api_token: str,
    archive_path: str,
    machine_name: str,
    *,
    processed_execution_ids: list[str],
    timeout_seconds: int,
) -> IngestionRequestResponse:
    """Send one path-based ingestion request to SimBoard."""
    payload = {
        "archive_path": archive_path,
        "machine_name": machine_name,
        "processed_execution_ids": processed_execution_ids,
    }
    body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        endpoint_url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
            parsed_body = json.loads(raw_body) if raw_body else {}
            return {
                "status_code": response.status,
                "body": parsed_body,
            }
    except urllib.error.HTTPError as exc:
        response_text = exc.read().decode("utf-8", errors="replace")

        raise IngestionRequestError(
            f"HTTP {exc.code}: {response_text}",
            status_code=exc.code,
            transient=_is_transient_status(exc.code),
        ) from exc
    except urllib.error.URLError as exc:
        raise IngestionRequestError(
            f"URL error: {exc.reason}", status_code=None, transient=True
        ) from exc
    except TimeoutError as exc:
        raise IngestionRequestError(
            "Request timed out", status_code=None, transient=True
        ) from exc


def _persist_archive_checkpoints_with_retries(
    snapshot_keys: set[str],
    endpoint_url: str,
    api_token: str,
    machine_name: str,
    archive_name: str,
    *,
    max_attempts: int,
    timeout_seconds: int,
    sleep_fn: Callable[[float], None],
    post_request_fn: Callable[..., IngestionRequestResponse] | None = None,
) -> bool:
    """Persist settled immutable snapshot keys with bounded retries."""
    if not snapshot_keys:
        return True
    if post_request_fn is None:
        post_request_fn = _post_archive_checkpoints_request
    for attempt in range(1, max_attempts + 1):
        try:
            post_request_fn(
                endpoint_url,
                api_token,
                machine_name,
                archive_name=archive_name,
                snapshot_keys=sorted(snapshot_keys),
                timeout_seconds=timeout_seconds,
            )
            return True
        except IngestionRequestError as exc:
            retrying = exc.transient and attempt < max_attempts
            _log_event(
                "archive_checkpoint_persistence_failed",
                {
                    "attempt": attempt,
                    "status_code": exc.status_code,
                    "retrying": retrying,
                    "error": str(exc),
                },
            )
            if not retrying:
                return False
            sleep_fn(2 ** (attempt - 1))
    return False


def _post_archive_checkpoints_request(
    endpoint_url: str,
    api_token: str,
    machine_name: str,
    *,
    archive_name: str,
    snapshot_keys: list[str],
    timeout_seconds: int,
) -> IngestionRequestResponse:
    """POST one completed archive-checkpoint batch."""
    body = json.dumps(
        {
            "machine_name": machine_name,
            "archive_name": archive_name,
            "snapshots": [
                {
                    "archive_month": key.split("/", 1)[0],
                    "snapshot_name": key.split("/", 1)[1],
                }
                for key in snapshot_keys
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint_url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
            return {
                "status_code": response.status,
                "body": json.loads(raw_body) if raw_body else {},
            }
    except urllib.error.HTTPError as exc:
        response_text = exc.read().decode("utf-8", errors="replace")
        raise IngestionRequestError(
            f"HTTP {exc.code}: {response_text}",
            status_code=exc.code,
            transient=_is_transient_status(exc.code),
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise IngestionRequestError(
            f"Checkpoint request failed: {exc}",
            status_code=None,
            transient=True,
        ) from exc
