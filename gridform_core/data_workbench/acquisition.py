"""Bounded acquisition of already-discovered official source revisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import chain
from typing import Callable, Iterable, Mapping, Protocol
from urllib.parse import urlparse
from urllib.request import OpenerDirector, Request, build_opener

from .contracts import RawObjectReceipt, SourceDefinition, SourceRevision
from .object_store import LocalObjectStore


class MediaTypeMismatch(ValueError):
    pass


class FetchResponse(Protocol):
    final_url: str
    status: int
    headers: Mapping[str, str]
    media_type: str

    def iter_bytes(self, chunk_size: int) -> Iterable[bytes]: ...


class FetchTransport(Protocol):
    def open(self, url: str, *, timeout_seconds: float) -> FetchResponse: ...


class _UrllibFetchResponse:
    def __init__(self, response: object) -> None:
        self._response = response
        self.final_url = str(response.geturl())  # type: ignore[attr-defined]
        self.status = int(response.status)  # type: ignore[attr-defined]
        self.headers = {
            str(key): str(value)
            for key, value in response.headers.items()  # type: ignore[attr-defined]
        }
        self.media_type = _base_media_type(self.headers.get("Content-Type", ""))

    def iter_bytes(self, chunk_size: int) -> Iterable[bytes]:
        try:
            while True:
                block = self._response.read(chunk_size)  # type: ignore[attr-defined]
                if not block:
                    break
                yield block
        finally:
            self._response.close()  # type: ignore[attr-defined]


class UrllibFetchTransport:
    def __init__(self, *, opener: OpenerDirector | object | None = None) -> None:
        self._opener = opener or build_opener()

    def open(self, url: str, *, timeout_seconds: float) -> FetchResponse:
        request = Request(url, headers={"User-Agent": "VALUE-Data-Workbench/1"})
        response = self._opener.open(request, timeout=timeout_seconds)  # type: ignore[attr-defined]
        return _UrllibFetchResponse(response)


@dataclass(frozen=True)
class FetchLimits:
    max_bytes: int = 2 * 1024 * 1024 * 1024
    timeout_seconds: float = 60.0
    chunk_size: int = 1024 * 1024


def _allowed(url: str, domains: tuple[str, ...]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return url.startswith("https://") and any(
        host == domain.lower() or host.endswith("." + domain.lower())
        for domain in domains
    )


def _base_media_type(value: str) -> str:
    return value.split(";", 1)[0].strip().lower()


def _rights_decision(policy: str) -> str:
    decisions = {
        "redistributable",
        "pointer-only",
        "local-use-only",
        "needs-rights-review",
    }
    normalized = policy.strip().lower().replace("_", "-")
    if normalized == "verify-each-revision":
        return "needs_rights_review"
    if normalized not in decisions:
        return "needs_rights_review"
    return normalized.replace("-", "_")


def _matches_declared_content(first_block: bytes, media_type: str) -> bool:
    if media_type in {
        "application/zip",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }:
        return first_block.startswith(b"PK\x03\x04")
    stripped = first_block.lstrip(b"\xef\xbb\xbf \t\r\n")
    if media_type in {"application/json", "application/geo+json"}:
        return stripped.startswith((b"{", b"["))
    if media_type in {"text/csv", "application/csv"}:
        try:
            text = first_block.decode("utf-8-sig")
        except UnicodeDecodeError:
            return False
        first_line = text.splitlines()[0] if text.splitlines() else ""
        return bool(first_line) and any(delimiter in first_line for delimiter in (",", ";", "\t"))
    return False


def fetch_revision(
    source: SourceDefinition,
    revision: SourceRevision,
    transport: FetchTransport,
    store: LocalObjectStore,
    *,
    limits: FetchLimits | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    retrieved_at: str | None = None,
) -> RawObjectReceipt:
    if source.source_id != revision.source_id:
        raise ValueError("Revision does not belong to the selected source definition")
    domains = tuple(source.allowed_domains)
    if not _allowed(revision.download_url, domains):
        raise ValueError("Discovered download URL is outside the official allowlist")
    expected = {_base_media_type(item) for item in source.expected_media_types}
    if expected and _base_media_type(revision.media_type) not in expected:
        raise MediaTypeMismatch("Discovered revision media type is not expected by source")

    effective_limits = limits or FetchLimits()
    response = transport.open(
        revision.download_url,
        timeout_seconds=effective_limits.timeout_seconds,
    )
    if not _allowed(response.final_url, domains):
        raise ValueError("Fetch redirected outside the official allowlist")
    if not 200 <= response.status < 300:
        raise OSError(f"Official source returned HTTP {response.status}")
    response_media = _base_media_type(response.media_type)
    blocks = iter(response.iter_bytes(effective_limits.chunk_size))
    if expected and response_media == "application/octet-stream":
        first_block = next(blocks, b"")
        declared_media = _base_media_type(revision.media_type)
        if not first_block or not _matches_declared_content(first_block, declared_media):
            close = getattr(blocks, "close", None)
            if callable(close):
                close()
            raise MediaTypeMismatch(
                f"Generic binary response failed the {declared_media} content signature"
            )
        response_media = declared_media
        blocks = chain((first_block,), blocks)
    elif expected and response_media not in expected:
        raise MediaTypeMismatch(
            f"Expected one of {sorted(expected)} but received {response_media}"
        )

    stored = store.put_stream(
        blocks,
        media_type=response_media,
        max_bytes=effective_limits.max_bytes,
        cancel_requested=cancel_requested,
    )
    return RawObjectReceipt(
        source_id=source.source_id,
        revision_id=revision.revision_id,
        sha256=stored.sha256,
        byte_size=stored.byte_size,
        media_type=stored.media_type,
        retrieved_at=retrieved_at or datetime.now(timezone.utc).isoformat(),
        final_resolved_url=response.final_url,
        licence_snapshot=revision.reported_licence,
        object_key=stored.object_key,
        http_metadata={str(key): str(value) for key, value in response.headers.items()},
        redistribution_decision=_rights_decision(source.redistribution_policy),
    )
