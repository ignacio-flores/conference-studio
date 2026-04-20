from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from runtime_compat import install_hashlib_usedforsecurity_compat


class RuntimeCompatTests(unittest.TestCase):
    def test_hashlib_constructors_accept_usedforsecurity_after_compat_install(self) -> None:
        install_hashlib_usedforsecurity_compat()

        for name in ("md5", "sha1", "sha224", "sha256", "sha384", "sha512"):
            digest = getattr(hashlib, name)(usedforsecurity=False)
            self.assertTrue(hasattr(digest, "hexdigest"))

        digest = hashlib.new("md5", usedforsecurity=False)
        self.assertTrue(hasattr(digest, "hexdigest"))


if __name__ == "__main__":
    unittest.main()
