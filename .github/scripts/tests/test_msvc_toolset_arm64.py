# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patch_msvc_toolset_arm64 import patch


SOURCE = '''class CraftCompiler:
    class Abi:
        msvc2019 = 1
        msvc2022 = 2
        msvc2026 = 3

    def getMsvcPlatformToolset(self):
        versions = {
            CraftCompiler.Abi.msvc2019: 142,
            CraftCompiler.Abi.msvc2022: 143,
            # Microsoft skipped v144, see https://stackoverflow.com/a/72951716
            CraftCompiler.Abi.msvc2026: 145,
        }
        if self.signature.abi not in versions:
            CraftCore.log.critical(f"Unknown MSVC Compiler {self.signature.abi}")
        return versions[self.signature.abi]
'''


class MsvcToolsetPatchTests(unittest.TestCase):
    def test_explicit_14_44_maps_to_v143_before_abi_default(self):
        result = patch(SOURCE)
        self.assertIn('self.msvcToolset.startswith("14.44")', result)
        self.assertIn('return 143', result)
        self.assertLess(
            result.index('self.msvcToolset.startswith("14.44")'),
            result.index('CraftCompiler.Abi.msvc2026: 145'),
        )

    def test_real_upstream_comment_does_not_break_patch(self):
        result = patch(SOURCE)
        self.assertIn('# Microsoft skipped v144', result)

    def test_default_msvc2026_mapping_is_preserved(self):
        result = patch(SOURCE)
        self.assertIn('CraftCompiler.Abi.msvc2026: 145', result)

    def test_patch_is_idempotent(self):
        once = patch(SOURCE)
        self.assertEqual(patch(once), once)

    def test_unexpected_structure_is_rejected(self):
        with self.assertRaises(ValueError):
            patch("class CraftCompiler:\n    pass\n")


if __name__ == "__main__":
    unittest.main()
