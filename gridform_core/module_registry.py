"""Runtime module registry.

Research projects store stable module IDs.  This registry resolves those IDs
to executable implementations and rejects kind mismatches before a model run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping


@dataclass(frozen=True)
class ModuleRegistration:
    id: str
    kind: str
    version: str
    factory: Callable[..., object]


class ModuleRegistry:
    def __init__(self) -> None:
        self._registrations: dict[str, ModuleRegistration] = {}

    def register(self, registration: ModuleRegistration) -> None:
        if registration.id in self._registrations:
            raise ValueError(f"Module is already registered: {registration.id}")
        self._registrations[registration.id] = registration

    def resolve(self, module_id: str, *, kind: str, **factory_args: object) -> object:
        try:
            registration = self._registrations[module_id]
        except KeyError as exc:
            raise ValueError(f"Module is not registered: {module_id}") from exc
        if registration.kind != kind:
            raise ValueError(
                f"Module {module_id} has kind {registration.kind}; expected {kind}"
            )
        return registration.factory(**factory_args)

    def registrations(self) -> Mapping[str, ModuleRegistration]:
        return dict(self._registrations)

