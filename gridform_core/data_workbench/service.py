"""Transport-neutral Data Workbench service protocol."""

from __future__ import annotations

from typing import Protocol

from .contracts import (
    BuildRequest,
    CandidatePack,
    DiscoveryReport,
    DiscoveryRequest,
    PromotionRequest,
    RawObjectReceipt,
    SignedBundleReceipt,
    SourceRevision,
    ValidationReport,
)


class DataWorkbenchService(Protocol):
    def discover(self, request: DiscoveryRequest) -> DiscoveryReport: ...

    def fetch(self, revision: SourceRevision) -> RawObjectReceipt: ...

    def compile(self, request: BuildRequest) -> CandidatePack: ...

    def validate(self, candidate_id: str) -> ValidationReport: ...

    def promote(self, request: PromotionRequest) -> SignedBundleReceipt: ...

