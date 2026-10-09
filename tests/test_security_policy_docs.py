"""P0-1 S8: the security policy and guides describe the shipped boundary."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


class SecurityPolicyDocsTests(unittest.TestCase):
    def test_security_policy_names_value_and_its_advisory_form(self) -> None:
        for name in ("SECURITY.md", "docs/SECURITY_AND_SUPPLY_CHAIN.md"):
            self.assertNotIn("FORCE", _read(name), name)
        policy = _read("SECURITY.md")
        self.assertIn("https://github.com/hanzohanzhe/Value/security/advisories/new", policy)

    def test_policy_states_the_boundary_assumption_and_non_controls(self) -> None:
        policy = _read("SECURITY.md")
        for phrase in ("one person per computer", "remote-desktop", "X-VALUE-Executable-Trust",
                       "informed-consent flag, not an access control", "authorized_headers",
                       "api-session-<port>.json", "verify_local_security_boundary.py", "421", "415"):
            self.assertIn(phrase, policy)
        for name, phrase in (("docs/tutorial/VALUE_101.md", "one person per computer"),
                             ("docs/tutorial/VALUE_101_ZH.md", "一台电脑只有一个使用者"),
                             ("docs/USER_GUIDE.md", "Open VALUE from its launcher"),
                             ("docs/USER_GUIDE_ZH.md", "Open VALUE from its launcher")):
            self.assertIn(phrase, _read(name), name)

    def test_guides_no_longer_promise_cors_access(self) -> None:
        for name in ("packaging/linux-local/README.md", "docs/USER_GUIDE.md", "docs/USER_GUIDE_ZH.md",
                     "docs/DEPLOYMENT.md", "SECURITY.md"):
            text = _read(name)
            self.assertIsNone(re.search(r"origins are (already )?allowed by the local API", text), name)
            self.assertNotIn("NEXT_PUBLIC_VALUE_API_ORIGIN", text, name)


if __name__ == "__main__":
    unittest.main()
