"""P0-1 S3: the UI gateway finds the backend's session file.

The gateway (node) and the backend (Python) must locate the same
``<data home>/runtime/api-session-<port>.json`` for every way a launcher or a
user can describe the data directory; otherwise every API request fails with
502 GF_GATEWAY_SESSION_UNAVAILABLE.  Ten environment cases are resolved by
``gridform_core.runtime_paths.user_data_root`` + ``backend.api_session`` and
by ``scripts/value-ui-gateway.mjs`` in separate processes and compared.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATEWAY = ROOT / "scripts" / "value-ui-gateway.mjs"


def node_executable() -> str | None:
    configured = os.environ.get("VALUE_NODE")
    if configured:
        return configured
    found = shutil.which("node")
    if found:
        return found
    for parent in Path(sys.executable).resolve().parents:
        candidate = parent / "node" / "bin" / "node"
        if parent.name == "runtime" and candidate.is_file():
            return str(candidate)
    return None


@unittest.skipIf(os.name == "nt", "POSIX path cases")
class SessionPathParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.node = node_executable()
        if self.node is None:
            self.skipTest("node is not available (set VALUE_NODE)")
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.base = Path(self._folder.name).resolve()
        self.home = self.base / "home"
        self.cwd = self.base / "cwd"
        self.home.mkdir()
        self.cwd.mkdir()
        (self.base / "real-state").mkdir()
        (self.base / "linked-state").symlink_to(self.base / "real-state")

    def _environment(self, overrides: dict[str, str | None]) -> dict[str, str]:
        environment = {key: value for key, value in os.environ.items()
                       if key not in {"VALUE_DATA_HOME", "LOCALAPPDATA", "XDG_DATA_HOME"}}
        environment.update(HOME=str(self.home), PYTHONDONTWRITEBYTECODE="1",
                           PYTHONPATH=str(ROOT))
        for key, value in overrides.items():
            if value is None:
                environment.pop(key, None)
            else:
                environment[key] = value
        return environment

    def _python(self, environment: dict[str, str], port: int) -> str:
        script = (
            "from gridform_core.runtime_paths import user_data_root\n"
            "from backend.api_session import session_path\n"
            f"print(session_path(user_data_root(), {port}))\n"
        )
        completed = subprocess.run([sys.executable, "-B", "-c", script], cwd=self.cwd, env=environment,
                                   capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout.strip()

    def _node(self, environment: dict[str, str], port: int) -> str:
        script = (
            f"import {{ resolveDataHome, sessionFilePath }} from {json.dumps(GATEWAY.as_uri())};\n"
            f"console.log(sessionFilePath(resolveDataHome(), {port}));\n"
        )
        completed = subprocess.run([self.node, "--input-type=module", "-e", script], cwd=self.cwd, env=environment,
                                   capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout.strip()

    def test_ten_environment_cases_resolve_to_the_same_session_file(self) -> None:
        base = str(self.base)
        cases = [
            ("absolute VALUE_DATA_HOME", {"VALUE_DATA_HOME": f"{base}/state"}),
            ("tilde VALUE_DATA_HOME", {"VALUE_DATA_HOME": "~/value-state"}),
            ("bare tilde", {"VALUE_DATA_HOME": "~"}),
            ("relative VALUE_DATA_HOME", {"VALUE_DATA_HOME": "relative/state"}),
            ("dot-dot and trailing slash", {"VALUE_DATA_HOME": f"{base}/cwd/../state/"}),
            ("symlinked data home", {"VALUE_DATA_HOME": f"{base}/linked-state"}),
            ("empty VALUE_DATA_HOME falls back to XDG", {"VALUE_DATA_HOME": "", "XDG_DATA_HOME": f"{base}/xdg"}),
            ("LOCALAPPDATA wins over XDG", {"LOCALAPPDATA": f"{base}/lad", "XDG_DATA_HOME": f"{base}/xdg"}),
            ("relative XDG", {"XDG_DATA_HOME": "xdg-relative"}),
            ("nothing set", {"VALUE_DATA_HOME": None, "XDG_DATA_HOME": "", "LOCALAPPDATA": ""}),
        ]
        self.assertEqual(len(cases), 10)
        for index, (label, overrides) in enumerate(cases):
            port = 8766 if index % 2 else 18766
            with self.subTest(label):
                environment = self._environment(overrides)
                python_path = self._python(environment, port)
                node_path = self._node(environment, port)
                self.assertEqual(node_path, python_path)
                self.assertTrue(python_path.endswith(f"/runtime/api-session-{port}.json"))


if __name__ == "__main__":
    unittest.main()
