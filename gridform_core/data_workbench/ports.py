"""Storage and governance ports for local and future hosted deployments."""

from __future__ import annotations

from typing import Iterable, Protocol

from .contracts import SourceDefinition, StoredObject


class SourceRegistry(Protocol):
    def list_sources(self) -> tuple[SourceDefinition, ...]: ...

    def get_source(self, source_id: str) -> SourceDefinition: ...


class ObjectStore(Protocol):
    def put_stream(self, blocks: Iterable[bytes], *, media_type: str) -> StoredObject: ...

    def verify(self, object_key: str, sha256: str) -> bool: ...


class JobStore(Protocol):
    def read(self, job_id: str) -> object | None: ...

    def write(self, job_id: str, payload: object) -> None: ...


class ApprovalStore(Protocol):
    def record(self, candidate_id: str, payload: object) -> None: ...

