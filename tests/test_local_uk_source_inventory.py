from __future__ import annotations

import json
import unittest
from pathlib import Path

from gridform_core.catalog import DATASET_SLOTS


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "publication" / "value-uk-open-data-pack" / "local-source-inventory.json"


class LocalUkSourceInventoryTests(unittest.TestCase):
    def test_all_contract_roles_have_source_and_no_absolute_local_path(self) -> None:
        payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
        rows = payload["objects"]
        self.assertEqual(len(rows), len(DATASET_SLOTS))
        self.assertEqual({row["canonical_role"] for row in rows}, {slot["role"] for slot in DATASET_SLOTS})
        self.assertTrue(all(row["source_id"] for row in rows))
        serialized = INVENTORY.read_text(encoding="utf-8").lower()
        self.assertNotIn("c:\\users\\", serialized)
        self.assertEqual(payload["roles_in_public_archive"], 0)

    def test_local_runtime_and_public_redistribution_are_separate(self) -> None:
        payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
        self.assertEqual(payload["roles_locally_available"], 25)
        self.assertEqual(
            payload["publication_status"],
            "PUBLIC_REDISTRIBUTION_GO_PER_OBJECT_WITH_ATTRIBUTION",
        )


if __name__ == "__main__":
    unittest.main()
