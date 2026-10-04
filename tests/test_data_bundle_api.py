from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from backend import server
from gridform_core.data_bundle import build_data_bundle


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC = ROOT / "data-packs" / "value-synthetic-contract-pack-v1"


class DataBundleApiTests(unittest.TestCase):
    def test_loopback_upload_requires_rights_and_exposes_installation(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            bundle = state / "synthetic.force-data-bundle.zip"
            build_data_bundle(pack_root=SYNTHETIC, destination=bundle)
            body = bundle.read_bytes()
            patches = (
                patch.dict(os.environ, {"VALUE_DATA_HOME": str(state)}),
                patch.object(server, "STATE_ROOT", state),
                patch.object(server, "IMPORT_STAGING_ROOT", state / "import-staging"),
                patch.object(server, "PACKS_ROOT", state / "data-packs"),
                patch.object(server, "PROJECTS_ROOT", state / "projects"),
                patch.object(server, "RUNS_ROOT", state / "runs"),
                patch.object(server, "ARCHIVES_ROOT", state / "archives"),
                patch.object(server, "TRASH_ROOT", state / "trash"),
                patch.object(server, "MIN_FREE_SPACE_BYTES", 0),
            )
            for item in patches:
                item.start()
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            origin = f"http://127.0.0.1:{httpd.server_address[1]}"
            try:
                unacknowledged = urllib.request.Request(
                    origin + "/api/data-packs/install",
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/zip", "X-Filename": "synthetic.zip"},
                )
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    urllib.request.urlopen(unacknowledged, timeout=10)
                self.assertEqual(rejected.exception.code, 400)
                self.assertEqual(
                    json.loads(rejected.exception.read())["error_code"],
                    "GF_DATA_BUNDLE_RIGHTS_ACK",
                )

                acknowledged = urllib.request.Request(
                    origin + "/api/data-packs/install",
                    data=body,
                    method="POST",
                    headers={
                        "Content-Type": "application/zip",
                        "X-Filename": "synthetic.zip",
                        "X-Force-Data-Rights": "acknowledged",
                    },
                )
                installed = json.loads(urllib.request.urlopen(acknowledged, timeout=10).read())
                self.assertTrue(installed["ok"])
                self.assertEqual(installed["installation"]["validation"]["passed"], 25)
                self.assertFalse(installed["installation"]["original_bundle_retained"])

                workspace = json.loads(
                    urllib.request.urlopen(origin + "/api/workspace", timeout=10).read()
                )
                pack = next(
                    item for item in workspace["data_packs"]
                    if item["id"] == "value-synthetic-contract-pack-v1"
                )
                self.assertTrue(pack["complete"])
                self.assertEqual(
                    pack["installation"]["installation_boundary"],
                    "local_data_only_no_executable_content",
                )
                self.assertFalse(any((state / "import-staging").glob("*")))
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=10)
                for item in reversed(patches):
                    item.stop()


if __name__ == "__main__":
    unittest.main()
