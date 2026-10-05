"""User-directory Linux installation and ownership-checked local process control."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

DEFAULT_ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "value.linux-local-install/v1"
UI_PORTS = {8800, 18800}


def isolated_python_argv(python, prefix):
    """-B -s and a fresh pycache_prefix: never read source-tree bytecode (R1-07).

    Same contract as app/backend/lifecycle/python_argv.py; this controller
    runs on the external interpreter before app/ is importable.
    """
    return [str(python), "-B", "-s", "-X", f"pycache_prefix={prefix}"]


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    pending = path.with_name(path.name + ".pending")
    pending.write_text(json.dumps(value, indent=2) + "\n"); pending.chmod(0o600); pending.replace(path)


def absolute(path):
    if not path.is_absolute() or path == Path("/"):
        raise ValueError("Use an absolute user directory other than /.")
    return path.resolve()


def verify(root):
    manifest = read(root / "release-manifest.json")
    if manifest.get("schema_version") != "value.linux-local-release/v1":
        raise ValueError("Unsupported Linux release manifest.")
    seen, mismatches = set(), []
    for entry in manifest.get("files", []):
        name = entry.get("path"); relative = PurePosixPath(name) if isinstance(name, str) else None
        if relative is None or relative.is_absolute() or ".." in relative.parts or name in seen:
            raise ValueError("Release inventory has an unsafe or duplicate path.")
        seen.add(name); path = root / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or sha(path) != entry.get("sha256"):
            mismatches.append(name)
    if not seen or "app/backend/server.py" not in seen or "app/dist/server/index.js" not in seen:
        raise ValueError("Release inventory omits the executable application.")
    # Generated Python bytecode is diagnostic noise; unknown source is not.
    app = root / "app"
    for base, dirs, files in os.walk(app):
        dirs[:] = [name for name in dirs if name != "__pycache__"]
        for name in files:
            path = Path(base) / name
            if path.suffix not in {".pyc", ".pyo"} and path.relative_to(root).as_posix() not in seen:
                mismatches.append(path.relative_to(root).as_posix())
    return manifest, sorted(set(mismatches))


def runtime(python, node):
    python, node = python.resolve(), node.resolve()
    if not python.is_file() or not node.is_file():
        raise ValueError("Both existing runtime executable paths are required.")
    code = """import importlib, importlib.metadata as m, json, platform, sys
if sys.version_info[:2] != (3,10) or platform.system() != 'Linux' or platform.machine() not in ('x86_64','AMD64'):
    raise SystemExit('VALUE requires external Linux x86-64 Python 3.10')
packages={}
for name in ('numpy','pandas','scipy','xarray','netCDF4','pyproj'):
    importlib.import_module(name)
    packages[name]=m.version(name)
print(json.dumps({'version':platform.python_version(),'packages':packages}))
"""
    clean = os.environ.copy(); clean.pop("PYTHONPATH", None); clean.pop("PYTHONHOME", None); clean.pop("NODE_OPTIONS", None)
    checked = subprocess.run([str(python), "-c", code], cwd="/", env=clean, capture_output=True, text=True, timeout=60)
    if checked.returncode: raise ValueError("External Python runtime cannot load required VALUE dependencies: " + checked.stderr[-4000:])
    python_info = json.loads(checked.stdout)
    checked = subprocess.run([str(node), "-p", "JSON.stringify({version:process.versions.node,platform:process.platform,arch:process.arch})"], env=clean, capture_output=True, text=True, timeout=10)
    if checked.returncode: raise ValueError("External Node runtime did not start.")
    node_info = json.loads(checked.stdout); parts = tuple(int(part) for part in node_info["version"].split("."))
    if parts < (22, 13, 0) or node_info["platform"] != "linux" or node_info["arch"] != "x64":
        raise ValueError("VALUE requires external Linux x86-64 Node >=22.13.0.")
    return {"python": {"path": str(python), "sha256": sha(python), **python_info}, "node": {"path": str(node), "sha256": sha(node), **node_info}}


def install(args):
    prefix, bundle = absolute(args.prefix), args.bundle.resolve()
    if prefix.exists() and (not prefix.is_dir() or any(prefix.iterdir())):
        raise ValueError("Installation requires a new or empty prefix. Existing files and state are preserved.")
    data_home = absolute(args.data_home) if args.data_home else prefix / "state"
    if (data_home.is_relative_to(prefix) and data_home != prefix / "state") or prefix.is_relative_to(data_home):
        raise ValueError("Choose an independent state directory outside the installed app.")
    if data_home.exists() and (not data_home.is_dir() or any(data_home.iterdir())):
        raise ValueError("Initial installation requires an empty independent VALUE_DATA_HOME.")
    manifest, changed = verify(bundle)
    if changed: raise ValueError("Bundle inventory failed: " + ", ".join(changed[:20]))
    runtimes = runtime(args.python, args.node)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{prefix.name}.installing-", dir=prefix.parent))
    external_stage = None
    try:
        for row in manifest["files"]:
            source, destination = bundle / row["path"], stage / row["path"]
            destination.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, destination)
            destination.chmod(row["mode"])
        shutil.copyfile(bundle / "release-manifest.json", stage / "release-manifest.json")
        if verify(stage)[1]: raise ValueError("Copied release failed inventory validation.")
        local_state = data_home.is_relative_to(prefix)
        if local_state:
            staged_state = stage / data_home.relative_to(prefix); staged_state.mkdir(parents=True)
        else:
            data_home.parent.mkdir(parents=True, exist_ok=True)
            external_stage = Path(tempfile.mkdtemp(prefix=f".{data_home.name}.installing-", dir=data_home.parent)); staged_state = external_stage
        if manifest.get("teaching_packs"):
            if set(manifest["teaching_packs"]) != {"value-101-baseline-v1", "value-101-network-v1"}:
                raise ValueError("Only the verified CC0 teaching pair may be automatically installed.")
            env = os.environ.copy(); env.pop("PYTHONHOME", None)
            env["PYTHONPATH"] = str(stage / "app"); env["VALUE_DATA_HOME"] = str(staged_state); env["PYTHONDONTWRITEBYTECODE"] = "1"
            installed = subprocess.run([runtimes["python"]["path"], str(stage / "app/scripts/install_synthetic_pack.py"), "--state-root", str(staged_state), "--value-101-only"],
                                       cwd=stage / "app", env=env, capture_output=True, text=True, timeout=60)
            if installed.returncode: raise ValueError("Teaching pack installation failed: " + installed.stderr[-4000:])
        config = {"schema_version": SCHEMA, "prefix": str(prefix), "data_home": str(data_home), "runtime": runtimes,
                  "manifest_sha256": sha(stage / "release-manifest.json"), "api_port": 8766, "ui_port": args.ui_port}
        write(stage / "installation.json", config)
        for name in ("start-value", "stop-value", "diagnose-value"):
            target = stage / "bin" / name; target.parent.mkdir(exist_ok=True)
            shutil.copyfile(stage / "app/packaging/linux-local" / name, target); target.chmod(0o755)
        (stage / "diagnostics").mkdir()
        if prefix.exists() and any(prefix.iterdir()): raise ValueError("The target prefix changed during installation.")
        if external_stage is not None:
            if data_home.exists() and any(data_home.iterdir()): raise ValueError("The target state directory changed during installation.")
            external_stage.replace(data_home)
            try:
                stage.replace(prefix)
            except OSError:
                data_home.replace(external_stage)
                raise
            external_stage = None
        else:
            stage.replace(prefix)
        print(json.dumps({"installed": str(prefix), "data_home": str(data_home), "external_runtime_required": True,
                          "teaching_packs": manifest.get("teaching_packs", []), "start": str(prefix / "bin/start-value")}))
    finally:
        if stage.exists(): shutil.rmtree(stage)
        if external_stage is not None and external_stage.exists(): shutil.rmtree(external_stage)


def config_for(prefix):
    config = read(prefix / "installation.json")
    if config.get("schema_version") != SCHEMA or config.get("prefix") != str(prefix):
        raise ValueError("Installation identity does not match this prefix.")
    if config.get("ui_port") not in UI_PORTS or config.get("api_port") != 8766:
        raise ValueError("This release supports UI ports 8800 or 18800 and API port 8766.")
    return config


def process_info(pid):
    directory = Path("/proc") / str(pid)
    try:
        stat = (directory / "stat").read_text().rsplit(")", 1)[1].split()
        return {"start_time": stat[19], "group": int(stat[2]), "state": stat[0],
                "argv": (directory / "cmdline").read_bytes().rstrip(b"\0").split(b"\0"),
                "environment": (directory / "environ").read_bytes().split(b"\0")}
    except (OSError, ValueError, IndexError): return None


def owned(entry, token):
    actual = process_info(entry["pid"])
    return bool(actual and actual["state"] != "Z" and actual["group"] == entry["pid"] and actual["start_time"] == entry["start_time"]
                and actual["argv"] == [item.encode() for item in entry["argv"]]
                and f"VALUE_LOCAL_INSTANCE={token}".encode() in actual["environment"])


def background_runs(data_home):
    """Runs whose model worker still holds its lease (they keep running)."""
    names = []
    for lock in sorted(Path(data_home).glob("runs/*/worker.lock")):
        try:
            with lock.open("r+b") as stream:
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                except BlockingIOError:
                    names.append(lock.parent.name)
        except OSError:
            continue
    return names


def health(port, path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as response: return response.status == 200
    except (OSError, ValueError): return False


def stop_record(record):
    live = []
    for entry in record["processes"].values():
        actual = process_info(entry["pid"])
        if not actual or actual["state"] == "Z": continue
        if not owned(entry, record["token"]): raise ValueError("Process ownership changed; refusing to signal an unrelated process.")
        live.append(entry)
    for entry in live:
        if not owned(entry, record["token"]): raise ValueError("Process ownership changed before signaling.")
        os.killpg(entry["pid"], signal.SIGTERM)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and any(owned(entry, record["token"]) for entry in record["processes"].values()): time.sleep(0.1)
    for entry in record["processes"].values():
        if owned(entry, record["token"]): os.killpg(entry["pid"], signal.SIGKILL)


def start(prefix, config):
    record_path = prefix / "processes.json"
    if record_path.exists():
        previous = read(record_path)
        if all(owned(entry, previous["token"]) for entry in previous["processes"].values()):
            print(json.dumps({"status": "already_started", "ui": f"http://127.0.0.1:{config['ui_port']}"})); return
        if any((info := process_info(entry["pid"])) and info["state"] != "Z" for entry in previous["processes"].values()):
            raise ValueError("Partial or uncertain existing process record; run diagnose-value and stop-value first.")
        record_path.unlink()
    manifest, changed = verify(prefix)
    if sha(prefix / "release-manifest.json") != config["manifest_sha256"] or changed:
        raise ValueError("Installed source/build changed; diagnose before starting: " + ", ".join(changed[:20]))
    rt = runtime(Path(config["runtime"]["python"]["path"]), Path(config["runtime"]["node"]["path"]))
    if rt != config["runtime"]: raise ValueError("External runtime identity or dependency versions changed; diagnose before starting.")
    for port in (config["api_port"], config["ui_port"]):
        with socket.socket() as sock:
            # Permit restart after closed connections enter TIME_WAIT, while
            # an active listener still owns the address (no SO_REUSEPORT).
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                sock.listen(1)
            except OSError as exc: raise ValueError(f"Local port {port} is occupied; no existing process will be stopped.") from exc
    token = uuid.uuid4().hex; app = prefix / "app"
    pycache = tempfile.mkdtemp(prefix="value-pycache-")
    env = os.environ.copy(); env.pop("PYTHONHOME", None); env.pop("NODE_PATH", None); env.pop("NODE_OPTIONS", None)
    env.update(VALUE_DATA_HOME=config["data_home"], PYTHONPATH=str(app), VALUE_LOCAL_INSTANCE=token, PYTHONHASHSEED="0",
               PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=pycache, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    commands = {"api": [*isolated_python_argv(rt["python"]["path"], pycache), "-m", "backend.server", "--host", "127.0.0.1", "--port", str(config["api_port"])],
                # --api-origin follows --port; the gateway reads the API session from VALUE_DATA_HOME (no token here).
                "ui": [rt["node"]["path"], str(app / "scripts/serve-value-ui.mjs"), "--host", "127.0.0.1", "--port", str(config["ui_port"]),
                       "--api-origin", f"http://127.0.0.1:{config['api_port']}"]}
    processes = {}; children = []
    record = {"schema_version": "value.linux-local-processes/v1", "prefix": str(prefix), "token": token, "processes": processes}
    try:
        for kind, command in commands.items():
            with (prefix / "diagnostics" / f"{kind}.log").open("ab") as log:
                child = subprocess.Popen(command, cwd=app, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            children.append(child); info = process_info(child.pid)
            if info is None: raise ValueError(f"{kind} exited before process ownership was recorded.")
            processes[kind] = {"pid": child.pid, "start_time": info["start_time"], "argv": command}
        write(record_path, record)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if any(child.poll() is not None for child in children): raise ValueError("A local service exited; inspect diagnostics/api.log and ui.log.")
            if health(config["api_port"], "/api/health") and health(config["ui_port"], "/") and health(config["ui_port"], "/api/health"):
                print(json.dumps({"status": "started", "ui": f"http://127.0.0.1:{config['ui_port']}", "api": f"http://127.0.0.1:{config['api_port']}", "data_home": config["data_home"]})); return
            time.sleep(0.2)
        raise ValueError("Local service readiness timed out; inspect diagnostics logs.")
    except Exception:
        stop_record(record); record_path.unlink(missing_ok=True)
        for child in children:
            try: child.wait(timeout=3)
            except subprocess.TimeoutExpired: pass
        raise


def diagnose(prefix, config):
    report = {"schema_version": "value.linux-local-diagnostics/v1", "prefix": str(prefix), "data_home": config["data_home"]}
    try:
        _, changed = verify(prefix); report["source_changed"] = changed
        report["manifest_matches_install"] = sha(prefix / "release-manifest.json") == config["manifest_sha256"]
    except (ValueError, OSError) as exc: report["inventory_error"] = str(exc)
    try:
        observed = runtime(Path(config["runtime"]["python"]["path"]), Path(config["runtime"]["node"]["path"]))
        report["runtime_matches_install"] = observed == config["runtime"]; report["runtime"] = observed
    except (ValueError, OSError) as exc: report["runtime_error"] = str(exc)
    path = prefix / "processes.json"
    if path.exists():
        record = read(path); report["process_ownership"] = {kind: owned(entry, record["token"]) for kind, entry in record["processes"].items()}
    else: report["process_ownership"] = {}
    report["health"] = {"api": health(config["api_port"], "/api/health"), "ui": health(config["ui_port"], "/"),
                        "ui_gateway_to_api": health(config["ui_port"], "/api/health")}
    report["logs"] = {}
    for name in ("api.log", "ui.log"):
        path = prefix / "diagnostics" / name
        if path.is_file():
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - 16384)); report["logs"][name] = stream.read().decode(errors="replace")
    print(json.dumps(report, indent=2))


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    installer = commands.add_parser("install")
    installer.add_argument("--prefix", type=Path, required=True); installer.add_argument("--bundle", type=Path, default=DEFAULT_ROOT)
    installer.add_argument("--python", type=Path, required=True); installer.add_argument("--node", type=Path, required=True)
    installer.add_argument("--data-home", type=Path); installer.add_argument("--ui-port", type=int, default=8800)
    for name in ("start", "stop", "diagnose"):
        commands.add_parser(name).add_argument("--prefix", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    try:
        if platform.system() != "Linux" or platform.machine() not in {"x86_64", "AMD64"}: raise ValueError("This candidate targets Linux x86-64.")
        if args.command == "install":
            if args.ui_port not in UI_PORTS: raise ValueError("Choose UI port 8800 or 18800.")
            install(args); return
        prefix = absolute(args.prefix); config = config_for(prefix)
        with (prefix / "control.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if args.command == "start": start(prefix, config)
            elif args.command == "diagnose": diagnose(prefix, config)
            else:
                path = prefix / "processes.json"
                if path.exists(): stop_record(read(path)); path.unlink()
                # Model workers run in their own sessions and keep running (Q4).
                print(json.dumps({"status": "stopped", "data_preserved": True,
                                  "background_runs": background_runs(Path(config["data_home"]))}))
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__": main()
