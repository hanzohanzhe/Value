"""Stable public failure taxonomy for model and artifact boundaries."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PublicFailure:
    code: str
    category: str
    message: str
    severity: str = "error"

    def to_dict(self) -> dict[str, str]:
        return dict(self.__dict__)


class VALUEError(Exception):
    code = "GF_RUNTIME_001"
    category = "runtime"
    public_message = "Model execution failed. Open the diagnostic artifact for details."

    def public_failure(self) -> PublicFailure:
        return PublicFailure(self.code, self.category, self.public_message)


class ContractError(VALUEError, ValueError):
    code = "GF_CONTRACT_001"
    category = "contract"
    public_message = "A selected module did not satisfy its declared contract."


class ExtensionOutputError(ContractError):
    """An extension hook returned an output VALUE refuses (AF-低1).

    The exception message names the extension, the hook and the rule; the
    Runs page shows its first line next to this public message.
    """

    code = "GF_EXTENSION_OUTPUT_REJECTED"
    category = "contract"
    public_message = (
        "An extension hook returned an output that VALUE does not accept; "
        "the detail below names the extension, the hook and the rule."
    )


class ExecutionIdentityChangedError(VALUEError, ValueError):
    """The installed code changed between enqueue and worker start (EM-中1)."""

    code = "GF_RUN_EXECUTION_IDENTITY_CHANGED"
    category = "execution_identity"
    public_message = (
        "The installed modules, extensions or VALUE code changed after this Run "
        "was queued, so it did not start. Resubmit it to run with the current code."
    )


class DataError(VALUEError, OSError):
    code = "GF_DATA_001"
    category = "data"
    public_message = "A required Data Pack binding is missing or invalid."


class ParameterError(VALUEError):
    code = "GF_PARAMETER_001"
    category = "parameter"
    public_message = "One or more project parameters are invalid."


class CompatibilityError(VALUEError, RuntimeError):
    code = "GF_COMPATIBILITY_001"
    category = "compatibility"
    public_message = "The selected model is incompatible with this runtime."


class DeprecatedRouteError(CompatibilityError):
    """A removed execution route was requested explicitly.

    This error is intentionally typed separately from an ordinary runtime
    incompatibility so callers cannot silently substitute a different engine.
    """

    code = "GF_DEPRECATED_ROUTE_001"
    category = "api_migration"
    public_message = (
        "This model entry point has been retired. Use the manifest-backed "
        "VALUE application service or the explicit reference-comparison command."
    )


class RuntimeCapabilityError(CompatibilityError):
    code = "GF_RUNTIME_CAPABILITY_001"
    category = "runtime_capability"
    public_message = "The requested model capability is not available in this environment."


class InvariantError(VALUEError, ValueError):
    code = "GF_INVARIANT_001"
    category = "invariant"
    public_message = "A scientific model invariant failed during execution."


class ArtifactError(VALUEError, OSError):
    code = "GF_ARTIFACT_001"
    category = "artifact"
    public_message = "A required run artifact could not be written or validated."


class RuntimeModelError(VALUEError):
    code = "GF_RUNTIME_001"
    category = "runtime"


def public_failure(error: BaseException) -> PublicFailure:
    if isinstance(error, VALUEError):
        return error.public_failure()
    if isinstance(error, (FileNotFoundError, OSError)):
        return PublicFailure(
            DataError.code, DataError.category, DataError.public_message
        )
    if isinstance(error, (TypeError, ValueError, KeyError)):
        return PublicFailure(
            ContractError.code, ContractError.category, ContractError.public_message
        )
    return RuntimeModelError().public_failure()


# Failure categories whose exception message is shown (first line) next to
# the public message on the Runs page (R6-1, EM-中1 / AF-低1).
DETAIL_CATEGORIES = frozenset({"contract", "execution_identity"})


def failure_detail(message: object, *, limit: int = 400) -> str | None:
    """First non-empty line of a diagnostic exception message, bounded."""

    for line in str(message or "").splitlines():
        line = line.strip()
        if line:
            return line if len(line) <= limit else line[: limit - 1] + "…"
    return None


def warning_event(
    code: str,
    category: str,
    message: str,
    *,
    severity: str = "warning",
) -> dict[str, str]:
    if severity not in {"info", "warning"}:
        raise ValueError("Recoverable event severity must be info or warning")
    return {
        "schema_version": "value.warning/v1",
        "code": code,
        "category": category,
        "severity": severity,
        "message": message,
    }
