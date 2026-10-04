"""Process-local module runtime selected by the current research project."""

from __future__ import annotations

from ..scheme_c_modules import SchemeCModuleRuntime


_runtime: SchemeCModuleRuntime | None = None


def configure_runtime(runtime: SchemeCModuleRuntime) -> None:
    global _runtime
    _runtime = runtime


def get_runtime() -> SchemeCModuleRuntime:
    if _runtime is None:
        raise RuntimeError("Scheme C module runtime has not been configured")
    return _runtime
