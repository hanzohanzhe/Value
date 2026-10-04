"""Run a bounded VALUE workload and record wall, CPU and peak-memory evidence."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path


def _windows_counters(process: subprocess.Popen[bytes]) -> tuple[float | None, int | None]:
    if os.name != "nt":
        return None, None

    class FileTime(ctypes.Structure):
        _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    handle = wintypes.HANDLE(int(process._handle))  # type: ignore[attr-defined]
    creation, exit_time, kernel, user = FileTime(), FileTime(), FileTime(), FileTime()
    cpu = None
    if ctypes.windll.kernel32.GetProcessTimes(
        handle, ctypes.byref(creation), ctypes.byref(exit_time), ctypes.byref(kernel), ctypes.byref(user)
    ):
        ticks = (
            (kernel.high << 32) + kernel.low + (user.high << 32) + user.low
        )
        cpu = ticks / 10_000_000
    memory = ProcessMemoryCounters()
    memory.cb = ctypes.sizeof(memory)
    peak = None
    if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb):
        peak = int(memory.PeakWorkingSetSize)
    return cpu, peak


def _posix_rss(pid: int) -> int | None:
    status = Path(f"/proc/{pid}/status")
    if not status.is_file():
        return None
    try:
        for line in status.read_text(encoding="utf-8").splitlines():
            if line.startswith(("VmHWM:", "VmRSS:")):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--pack", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mode", required=True, choices=("validation_24h", "validation_168h", "smoke", "two_year_smoke"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, "-m", "gridform_core.application",
        "--project", str(args.project.resolve()), "--pack", str(args.pack.resolve()),
        "--output", str(args.output.resolve()), "--run-id", args.run_id, "--mode", args.mode,
    ]
    # The application indexes every file already present in ``output``.  Keep
    # observer logs beside, not inside, the model bundle so later writes cannot
    # invalidate an otherwise immutable scientific artifact hash.
    stdout_path = args.output.parent / f"{args.output.name}.stdout.log"
    stderr_path = args.output.parent / f"{args.output.name}.stderr.log"
    before_children = os.times().children_user + os.times().children_system
    started = time.perf_counter()
    peak_rss = 0
    cpu = None
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        while process.poll() is None:
            _cpu, windows_peak = _windows_counters(process)
            if _cpu is not None:
                cpu = _cpu
            observed = windows_peak if windows_peak is not None else _posix_rss(process.pid)
            if observed is not None:
                peak_rss = max(peak_rss, observed)
            time.sleep(0.1)
        windows_cpu, windows_peak = _windows_counters(process)
        if windows_cpu is not None:
            cpu = windows_cpu
        if windows_peak is not None:
            peak_rss = max(peak_rss, windows_peak)
        return_code = int(process.returncode or 0)
    wall = time.perf_counter() - started
    if cpu is None:
        after_children = os.times().children_user + os.times().children_system
        cpu = max(0.0, after_children - before_children)
    metrics = {
        "schema_version": "value.process-metrics/v1",
        "run_id": args.run_id,
        "mode": args.mode,
        "command": command,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "wall_seconds": wall,
        "cpu_seconds": cpu,
        "peak_resident_memory_bytes": peak_rss or None,
        "sampling_interval_seconds": 0.1,
        "return_code": return_code,
        "stdout": str(stdout_path.resolve()),
        "stderr": str(stderr_path.resolve()),
    }
    (args.output / "process-metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    raise SystemExit(return_code)


if __name__ == "__main__":
    main()
