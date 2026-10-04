"""Manual, digest-pinned transfer to approved repository draft releases only.

Never persist or print the scoped source URLs. No source-repository token is used.
The optional data hook receives local paths and no credentials.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
HOSTS = frozenset({"release-assets.githubusercontent.com", "objects.githubusercontent.com"})
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}\Z")
TAG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,100}\Z")


class SafeFailure(Exception):
    """Only fixed, nonsensitive messages may reach the console."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SafeFailure(message)


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_url(url: object) -> str:
    require(isinstance(url, str) and len(url) <= 32768, "invalid scoped source URL")
    try:
        parts = urllib.parse.urlsplit(url)
        valid = (parts.scheme == "https" and parts.hostname in HOSTS
                 and parts.port in (None, 443) and not parts.username
                 and not parts.password and not parts.fragment and bool(parts.query)
                 and parts.path.startswith("/github-production-release-asset"))
    except Exception:
        raise SafeFailure("invalid scoped source URL") from None
    require(valid, "source URL outside approved signed asset hosts")
    return url


class ScopedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        validate_url(new_url)
        return super().redirect_request(request, response, code, message, headers, new_url)


def parse_payload(raw: str, registry: dict, software_tag: str, data_tag: str, build_data: bool) -> list[dict]:
    try:
        payload = json.loads(raw)
    except Exception:
        raise SafeFailure("transfer secret is not valid JSON") from None
    approved = {a["name"]: a for a in registry["assets"]}
    needed = {n for n, a in approved.items() if a["role"] == "software" or build_data}
    require(isinstance(payload, list) and len(payload) == len(needed), "transfer secret asset count mismatch")
    seen = set()
    for item in payload:
        require(isinstance(item, dict) and set(item) == {"url", "name", "sha256", "bytes", "target_tag"},
                "transfer secret entry schema mismatch")
        name = item["name"]
        require(isinstance(name, str) and NAME_RE.fullmatch(name) and name in needed and name not in seen,
                "asset filename not uniquely approved")
        seen.add(name)
        spec = approved[name]
        require(type(item["bytes"]) is int and item["bytes"] == spec["bytes"]
                and item["sha256"] == spec["sha256"], "asset digest or byte count not approved")
        expected_tag = software_tag if spec["role"] == "software" else data_tag
        require(item["target_tag"] == expected_tag, "asset target tag mismatch")
        validate_url(item["url"])
        item["role"] = spec["role"]
    require(seen == needed, "transfer secret missing approved assets")
    return payload


def download(item: dict, directory: Path) -> Path:
    path = directory / item["name"]
    partial = path.with_name(path.name + ".partial")
    total = 0
    h = hashlib.sha256()
    try:
        # Deliberately no Authorization header, token, cookie jar, or URL logging.
        opener = urllib.request.build_opener(ScopedRedirect())
        with opener.open(item["url"], timeout=120) as response, partial.open("xb") as output:
            require(response.status == 200, "source asset download status rejected")
            declared = response.headers.get("Content-Length")
            if declared is not None:
                require(declared.isdigit() and int(declared) == item["bytes"], "source asset length mismatch")
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                require(total <= item["bytes"], "source asset exceeds approved length")
                output.write(chunk)
                h.update(chunk)
        require(total == item["bytes"] and h.hexdigest() == item["sha256"], "source asset byte/SHA verification failed")
        partial.replace(path)
        print("Verified approved asset: " + item["name"], flush=True)
        return path
    except SafeFailure:
        raise
    except Exception:
        # urllib exceptions may contain the complete signed URL; discard them.
        raise SafeFailure("source asset download failed; regenerate scoped URLs if expired") from None
    finally:
        partial.unlink(missing_ok=True)


def gh_json(args: list[str]) -> dict:
    try:
        result = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120, check=False)
        require(result.returncode == 0, "GitHub metadata check failed")
        return json.loads(result.stdout)
    except SafeFailure:
        raise
    except Exception:
        raise SafeFailure("GitHub metadata check failed") from None


def draft_gate(repository: str, tag: str) -> int:
    release = gh_json(["release", "view", tag, "--repo", repository, "--json", "databaseId,isDraft,tagName"])
    require(release.get("isDraft") is True and release.get("tagName") == tag,
            "target release must already exist and remain a draft")
    release_id = release.get("databaseId")
    require(type(release_id) is int and release_id > 0, "target draft release ID invalid")
    return release_id


def upload(path: Path, repository: str, tag: str) -> dict:
    release_id = draft_gate(repository, tag)
    api_args = ["api", "repos/" + repository + "/releases/" + str(release_id)]
    release = gh_json(api_args)
    require(release.get("draft") is True and release.get("id") == release_id and release.get("tag_name") == tag,
            "target draft changed before upload")
    matches = [a for a in release.get("assets", []) if a.get("name") == path.name]
    require(len(matches) <= 1, "target draft contains duplicate asset names")
    expected_sha = file_digest(path)
    expected_bytes = path.stat().st_size
    if matches and matches[0].get("size") == expected_bytes and matches[0].get("digest") == "sha256:" + expected_sha:
        print("Reverified existing draft asset; upload skipped: " + path.name, flush=True)
        return {"name": path.name, "bytes": expected_bytes, "sha256": expected_sha, "target_tag": tag,
                "remote_asset_id": matches[0]["id"], "remote_digest_verified": True, "existing_asset_reused": True}
    try:
        result = subprocess.run(["gh", "release", "upload", tag, str(path), "--repo", repository, "--clobber"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900, check=False)
        require(result.returncode == 0, "draft release upload failed")
    except SafeFailure:
        raise
    except Exception:
        raise SafeFailure("draft release upload failed") from None
    release = gh_json(api_args)
    matches = [a for a in release.get("assets", []) if a.get("name") == path.name]
    require(release.get("draft") is True and release.get("id") == release_id
            and release.get("tag_name") == tag and len(matches) == 1,
            "uploaded asset missing or target release no longer draft")
    asset = matches[0]
    require(asset.get("size") == path.stat().st_size and asset.get("digest") == "sha256:" + expected_sha,
            "remote uploaded asset byte/SHA verification failed")
    print("Uploaded verified draft asset: " + path.name, flush=True)
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": expected_sha, "target_tag": tag,
            "remote_asset_id": asset["id"], "remote_digest_verified": True, "existing_asset_reused": False}


def clean_hook_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items()
            if key in {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR"}}


def prepare_fixture(scratch: Path, repository: str) -> Path:
    approved = json.loads((ROOT / "publication/cloud-transfer-approved-data.json").read_text())
    fixture = approved.get("fixture", {})
    require(set(fixture) == {"name", "sha256", "bytes", "tag"}, "reviewed fixture metadata missing")
    name = fixture["name"]
    require(isinstance(name, str) and NAME_RE.fullmatch(name)
            and name.endswith((".zip", ".tar.gz")) and type(fixture["bytes"]) is int
            and fixture["bytes"] > 0 and isinstance(fixture["sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", fixture["sha256"])
            and fixture["tag"] == "transfer-fixture-2026-10-04", "reviewed fixture metadata invalid")
    release_id = draft_gate(repository, fixture["tag"])
    release = gh_json(["api", "repos/" + repository + "/releases/" + str(release_id)])
    matches = [a for a in release.get("assets", []) if a.get("name") == name]
    require(release.get("draft") is True and release.get("id") == release_id
            and release.get("tag_name") == fixture["tag"] and len(matches) == 1,
            "temporary fixture draft/asset mismatch")
    asset = matches[0]
    require(type(asset.get("id")) is int and asset["id"] > 0 and asset.get("size") == fixture["bytes"]
            and asset.get("digest") == "sha256:" + fixture["sha256"], "temporary fixture remote byte/SHA mismatch")
    path = scratch / name
    try:
        with path.open("xb") as output:
            result = subprocess.run(["gh", "api", "repos/" + repository + "/releases/assets/" + str(asset["id"]),
                                     "-H", "Accept: application/octet-stream"],
                                    stdout=output, stderr=subprocess.DEVNULL, timeout=900, check=False)
        require(result.returncode == 0 and path.stat().st_size == fixture["bytes"]
                and file_digest(path) == fixture["sha256"], "temporary fixture local byte/SHA mismatch")
        destination = scratch / "fixture"
        destination.mkdir()
        if name.endswith(".tar.gz"):
            require(hasattr(tarfile, "data_filter"), "host Python requires safe tar data filter")
            with tarfile.open(path, "r:gz") as archive:
                require(sum(m.size for m in archive.getmembers()) <= 4 * 1024**3,
                        "fixture expansion exceeds approved scratch budget")
                archive.extractall(destination, filter="data")
        else:
            with zipfile.ZipFile(path) as archive:
                require(sum(m.file_size for m in archive.infolist()) <= 4 * 1024**3,
                        "fixture expansion exceeds approved scratch budget")
                for member in archive.infolist():
                    target = (destination / member.filename).resolve()
                    require(not member.filename.startswith(("/", "\\")) and "\\" not in member.filename
                            and target.is_relative_to(destination.resolve())
                            and ((member.external_attr >> 16) & 0o170000) != 0o120000,
                            "fixture ZIP member path/link rejected")
                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member) as source, target.open("xb") as output:
                            shutil.copyfileobj(source, output, length=1024 * 1024)
        print("Verified temporary offline fixture: " + name, flush=True)
        return destination
    except SafeFailure:
        raise
    except Exception:
        raise SafeFailure("temporary fixture download or safe extraction failed") from None


def build_data_assets(scratch: Path, sources: dict[str, Path], data_tag: str, fixture_dir: Path) -> list[Path]:
    hook = ROOT / "scripts/cloud_transfer_data_hook.py"
    approved_path = ROOT / "publication/cloud-transfer-approved-data.json"
    require(hook.is_file() and fixture_dir.is_dir() and approved_path.is_file(),
            "reviewed data hook/fixture missing; data build is not enabled yet")
    full_archive = sources["VALUE-Linux-x64-Full-2026-10-03-rc1.tar.gz"]
    unpacked = scratch / "full-runtime"
    unpacked.mkdir()
    require(hasattr(tarfile, "data_filter"), "host Python requires safe tar data filter")
    try:
        with tarfile.open(full_archive, "r:gz") as archive:
            archive.extractall(unpacked, filter="data")
    except Exception:
        raise SafeFailure("verified Linux Full safe extraction failed") from None
    full = unpacked / "VALUE-Linux-x64"
    require(full.is_dir(), "Linux Full archive layout mismatch")
    manifest = json.loads((full / "release-manifest.json").read_text())
    require(manifest["application_files_sha256"] == "6c74f51a176ea238141dd3a10cd24e966b4dd3fc82615444f467e58e819b0010",
            "Linux Full app identity mismatch")
    python_rel = "runtime/python/bin/python3.10"
    py_spec = next(r for r in manifest["files"] if r["path"] == python_rel)
    require(file_digest(full / python_rel) == py_spec["sha256"], "Linux Full interpreter digest mismatch")
    runtime_check = subprocess.run(
        [str(full / python_rel), "-B", "-c", "import sys,zlib; print(sys.version.split()[0],zlib.ZLIB_RUNTIME_VERSION)"],
        env=clean_hook_env(), capture_output=True, text=True, timeout=60, check=False)
    require(runtime_check.returncode == 0 and runtime_check.stdout.strip() == "3.10.18 1.3.1",
            "Linux Full Python/zlib identity mismatch")
    output = scratch / "data-assets"
    output.mkdir()
    receipt = scratch / "data-receipt.json"
    env = clean_hook_env()
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", VALUE_DATA_TARGET_TAG=data_tag,
               VALUE_APPROVED_REUSE_SOURCE=str(sources["force-uk-benchmark-2025-v1.zip"]))
    # The reviewed fixed hook has no URL or GitHub credential in its environment.
    try:
        # Hosted Ubuntu provides passwordless sudo + util-linux. Create an empty
        # network namespace, then drop privileges back to the runner's UID/GID.
        require(all(shutil.which(binary) for binary in ("sudo", "unshare", "setpriv", "env")),
                "offline data hook isolation tools unavailable")
        command = ["sudo", "-n", "unshare", "--net", "--", "setpriv", "--reuid", str(os.getuid()),
                   "--regid", str(os.getgid()), "--clear-groups", "env", "-i"]
        command.extend(key + "=" + value for key, value in env.items())
        command.extend([sys.executable, "-B", str(hook), "--full-root", str(full),
                        "--fixture-dir", str(fixture_dir), "--output-dir", str(output), "--receipt", str(receipt)])
        built = subprocess.run(command,
                               env=clean_hook_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=2400, check=False)
        require(built.returncode == 0 and receipt.is_file(), "reviewed data fixture build failed")
        records = json.loads(receipt.read_text())["assets"]
        approved = json.loads(approved_path.read_text())["assets"]
        expected = {a["name"]: a for a in approved}
        require(len(records) == len(expected) == 6, "data build must produce exactly six approved assets")
        seen = set()
        paths = []
        for record in records:
            name = record["name"]
            require(isinstance(name, str) and NAME_RE.fullmatch(name) and name in expected and name not in seen,
                    "data build filename not uniquely approved")
            seen.add(name)
            spec = expected[name]
            require(record["bytes"] == spec["bytes"] and record["sha256"] == spec["sha256"]
                    and record["target_tag"] == data_tag, "data build approval metadata mismatch")
            path = Path(record["path"]).resolve()
            require(path.parent == output.resolve() and path.name == name and path.is_file()
                    and not Path(record["path"]).is_symlink(), "data output escaped scratch directory")
            require(path.stat().st_size == spec["bytes"] and file_digest(path) == spec["sha256"],
                    "data output byte/SHA verification failed")
            paths.append(path)
        return paths
    except SafeFailure:
        raise
    except Exception:
        raise SafeFailure("reviewed data fixture build or receipt validation failed") from None


def main() -> None:
    os.umask(0o077)
    raw = os.environ.pop("VALUE_ASSET_TRANSFER", "")
    registry = json.loads((ROOT / "publication/cloud-transfer-approved-sources.json").read_text())
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    require(repository.casefold() == registry["destination_repository"].casefold(), "destination repository mismatch")
    software_tag = os.environ.get("SOFTWARE_TARGET_TAG", "")
    data_tag = os.environ.get("DATA_TARGET_TAG", "")
    build_data = os.environ.get("BUILD_DATA", "false") == "true"
    require(TAG_RE.fullmatch(software_tag) and (not build_data or TAG_RE.fullmatch(data_tag)), "invalid target tag")
    entries = parse_payload(raw, registry, software_tag, data_tag, build_data)
    del raw
    draft_gate(repository, software_tag)
    if build_data:
        require(data_tag != software_tag, "software and data releases require distinct target tags")
        draft_gate(repository, data_tag)
    with tempfile.TemporaryDirectory(prefix="value-scoped-transfer-", dir=os.environ.get("RUNNER_TEMP")) as directory:
        scratch = Path(directory)
        required = sum(e["bytes"] for e in entries) + (9 * 1024**3 if build_data else 1024**3)
        require(shutil.disk_usage(scratch).free > required, "insufficient scratch space")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            # Consume every result before uploads; a failed digest cannot cause partial transfer.
            futures = {e["name"]: executor.submit(download, e, scratch) for e in entries}
            sources = {name: future.result() for name, future in futures.items()}
        fixture_dir = prepare_fixture(scratch, repository) if build_data else None
        data_outputs = build_data_assets(scratch, sources, data_tag, fixture_dir) if build_data else []
        # All downloads and optional outputs have passed their pinned checks first.
        uploaded = []
        for item in entries:
            if item["role"] == "software":
                uploaded.append(upload(sources[item["name"]], repository, software_tag))
        for path in data_outputs:
            uploaded.append(upload(path, repository, data_tag))
        # This receipt contains public filenames/digests only, never source URLs.
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as report:
                report.write("### Verified draft asset transfer\n\n")
                for asset in uploaded:
                    report.write("- `" + asset["name"] + "`: " + str(asset["bytes"]) + " bytes, SHA256 `"
                                 + asset["sha256"] + "`, remote digest verified.\n")
    print("Verified draft transfer complete; scratch removed. No release published.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except SafeFailure as error:
        print("Transfer stopped: " + str(error), file=sys.stderr)
        sys.exit(1)
    except BaseException:
        # Never emit exception repr, stack locals, URLs, or subprocess stderr.
        print("Transfer stopped: internal error (details intentionally suppressed)", file=sys.stderr)
        sys.exit(1)
