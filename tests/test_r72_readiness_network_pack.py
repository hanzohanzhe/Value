"""R7-2 (1): /api/projects/resolve-readiness reads the separate signed Network Pack.

Before the fix the endpoint called ``build_domain_readiness`` without the
selected network overlay, so every zonal draft whose base pack carries no
``value.zonal.*`` roles was reported as ``GF_DOMAIN_ZONAL_INPUT``
("value.zonal.zones not bound"), although preflight and the Run accepted it.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import urllib.request
from pathlib import Path

from tests.local_api_harness import start_local_api


ROOT = Path(__file__).resolve().parents[1]
BASE_PACK = ROOT / "data-packs" / "value-101-baseline-v1"
NETWORK_PACK = ROOT / "data-packs" / "value-101-network-v1"


def _zonal_draft(network_pack_id: str) -> dict[str, object]:
    return {
        "data_pack_id": "value-101-baseline-v1",
        "start_year": 2025,
        "end_year": 2025,
        "mode": "smoke",
        "modules": {
            "psm": "value-staged-bid-at-cost-psm",
            "balancing": "value-zonal-redispatch-balancing",
        },
        "selected_extensions": ["value-zonal-redispatch-extension"],
        "market_configuration": {
            "network_pack_id": network_pack_id,
            "zonal_demand_mode": "scenario_scaled_zonal_shares",
        },
    }


class ResolveReadinessNetworkPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _install_packs(self, *, network: bool) -> None:
        shutil.copytree(BASE_PACK, self.home / "data-packs" / BASE_PACK.name)
        if network:
            shutil.copytree(
                NETWORK_PACK,
                self.home / "data-workbench" / "installed-packs" / NETWORK_PACK.name,
            )

    def _readiness(self, origin: str, body: dict[str, object]) -> dict[str, object]:
        request = urllib.request.Request(
            origin + "/api/projects/resolve-readiness",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_base_pack_has_no_zonal_roles(self) -> None:
        manifest = json.loads((BASE_PACK / "manifest.json").read_text(encoding="utf-8"))
        self.assertFalse([role for role in manifest["bindings"] if role.startswith("value.zonal.")])

    def test_zonal_draft_reads_roles_from_the_installed_network_pack(self) -> None:
        self._install_packs(network=True)
        with start_local_api(data_home=self.home) as (_httpd, origin, _token):
            payload = self._readiness(origin, _zonal_draft(NETWORK_PACK.name))
        codes = [str(item.get("code")) for item in payload["issues"]]
        self.assertNotIn("GF_DOMAIN_ZONAL_INPUT", codes, payload["issues"])
        self.assertNotIn("GF_DOMAIN_ZONAL_PACK_SELECTION", codes)
        section = payload["sections"]["zonal_network"]
        self.assertNotEqual(section.get("status"), "blocked", section)
        self.assertIn("cutset_classification", section)

    def test_missing_network_pack_is_named_not_reported_as_unbound_roles(self) -> None:
        self._install_packs(network=False)
        with start_local_api(data_home=self.home) as (_httpd, origin, _token):
            payload = self._readiness(origin, _zonal_draft(NETWORK_PACK.name))
        self.assertEqual(payload["status"], "blocked")
        first = payload["issues"][0]
        self.assertEqual(first["code"], "GF_DOMAIN_ZONAL_PACK_SELECTION")
        self.assertIn("not installed", first["message"])
        self.assertEqual(first["severity"], "error")

    def test_copperplate_draft_needs_no_network_pack(self) -> None:
        self._install_packs(network=False)
        body = _zonal_draft(NETWORK_PACK.name)
        body["modules"] = {"psm": "value-staged-bid-at-cost-psm", "balancing": "value-copperplate-balancing"}
        body["selected_extensions"] = []
        body["market_configuration"] = {}
        with start_local_api(data_home=self.home) as (_httpd, origin, _token):
            payload = self._readiness(origin, body)
        codes = [str(item.get("code")) for item in payload["issues"]]
        self.assertNotIn("GF_DOMAIN_ZONAL_PACK_SELECTION", codes)
        self.assertNotIn("zonal_network", payload["sections"])


if __name__ == "__main__":
    unittest.main()
