"""Light model-worker entry point (``python -m backend.worker_entry``).

Phase one uses only the standard library: it takes the run's lease
(``worker.lock``), checks that this process is the worker the server spawned
(lease nonce in ``worker.json``) and that the run is still ``queued``, records
``worker-lease.json`` and installs termination handlers.  Only then, inside a
``try``, phase two imports ``backend.model_runner`` and the scientific stack,
so a broken numpy or kernel is recorded as ``GF_WORKER_IMPORT_FAILED`` instead
of leaving the run queued for ever (P7-07).

Exit codes: 0 completed, cancelled, or a stale/late worker that stood down
without writing anything; 1 failed; 75 another worker holds the lease;
128+n after termination signal n (143 for SIGTERM); 130 after Ctrl+C.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
import traceback
from pathlib import Path
from typing import Sequence

_STARTED = time.monotonic()

from .run_status import LateWriteRejected, read_status, record_light_failure  # noqa: E402
from .states import classify  # noqa: E402
from .worker_lease import (  # noqa: E402
    EXIT_FAILED,
    EXIT_OK,
    EXIT_SECOND_WORKER,
    WorkerTerminated,
    acquire_lease,
    read_spawn_record,
    write_lease_record,
)

EXIT_INTERRUPTED = 130
MODES = ("smoke", "two_year_smoke", "validation_24h", "validation_168h", "value_101_day", "two_year", "full")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="backend.worker_entry")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--lease-nonce", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--mode", choices=MODES, default="smoke")
    return parser


def _install_signal_handlers() -> None:
    def terminate(signum: int, _frame: object) -> None:
        # One recorded termination is enough; a second signal must not
        # interrupt the failure record itself.
        signal.signal(signum, signal.SIG_IGN)
        raise WorkerTerminated(signum)

    for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
        number = getattr(signal, name, None)
        if number is not None:
            signal.signal(number, terminate)


def _say(message: str) -> None:
    print(f"VALUE worker: {message}", file=sys.stderr, flush=True)


def _record(run_dir: Path, args: argparse.Namespace, code: str, message: str, error: BaseException) -> None:
    try:
        record_light_failure(
            run_dir, run_id=args.run, project_id=args.project, mode=args.mode,
            error_code=code, message=message, exception=error,
            traceback_text=traceback.format_exc(),
        )
    except LateWriteRejected:
        _say("the run is no longer active; nothing was recorded")


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    run_dir = Path(args.run_dir).absolute()
    if run_dir.name != args.run:
        _say("--run-dir does not name --run; refusing to start")
        return EXIT_FAILED
    lease = acquire_lease(run_dir)
    if lease is None:
        _say("another worker holds this run's lease")
        return EXIT_SECOND_WORKER
    try:
        spawn = read_spawn_record(run_dir) or {}
        if spawn.get("lease_nonce") != args.lease_nonce:
            _say("this worker is stale (lease nonce differs); standing down")
            return EXIT_OK
        state = classify(read_status(run_dir))
        if state != "queued":
            _say(f"the run is {state}, not queued; standing down")
            return EXIT_OK
        write_lease_record(
            run_dir, run_id=args.run, nonce=args.lease_nonce,
            startup_seconds=time.monotonic() - _STARTED,
        )
        _install_signal_handlers()
        try:
            from backend import model_runner
        except WorkerTerminated as exc:
            _record(run_dir, args, "GF_WORKER_TERMINATED", str(exc), exc)
            return 128 + exc.signum
        except KeyboardInterrupt as exc:  # Ctrl+C while importing: a termination
            _record(run_dir, args, "GF_WORKER_TERMINATED",
                    "The model worker was interrupted (Ctrl+C) while importing.", exc)
            return EXIT_INTERRUPTED
        except BaseException as exc:  # noqa: BLE001 - any import failure is recorded
            traceback.print_exc()
            _record(
                run_dir, args, "GF_WORKER_IMPORT_FAILED",
                "The model worker could not import its scientific dependencies.", exc,
            )
            return EXIT_FAILED
        expected = (Path(model_runner.STATE_ROOT) / "runs" / args.run).absolute()
        if os.path.normcase(str(expected)) != os.path.normcase(str(run_dir)):
            error = RuntimeError(f"Worker data home {model_runner.STATE_ROOT} does not contain {run_dir}")
            _record(run_dir, args, "GF_WORKER_DATA_HOME_MISMATCH", str(error), error)
            return EXIT_FAILED
        try:
            return model_runner.execute(
                args.project, args.run, args.mode, status_path=run_dir / "status.json",
            )
        except WorkerTerminated as exc:  # arrived outside execute's own handlers
            _record(run_dir, args, "GF_WORKER_TERMINATED", str(exc), exc)
            return 128 + exc.signum
    finally:
        lease.release()


if __name__ == "__main__":
    raise SystemExit(main())
