# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patch_runtime_arm64 import patch


SOURCE = '''                    if CraftCore.compiler.isMSVC2026():
                        flavor = "2026"
                    if CraftCore.compiler.isMSVC2022():
                        flavor = "2022"
                    elif CraftCore.compiler.isMSVC2019():
                        flavor = "2019"
                    else:
                        raise Exception("Unknown compiler")
                    redistDir = os.path.join(redistDir, "x86" if CraftCore.compiler.architecture == CraftCompiler.Architecture.x86_32 else "x64")
'''


class RuntimePatchTests(unittest.TestCase):
    def test_vs2026_does_not_fall_through_to_unknown_compiler(self):
        result = patch(SOURCE)
        self.assertIn('elif CraftCore.compiler.isMSVC2022():', result)
        self.assertNotIn('                    if CraftCore.compiler.isMSVC2022():', result)

    def test_arm64_uses_arm64_redistributable_directory(self):
        result = patch(SOURCE)
        self.assertIn('CraftCompiler.Architecture.arm64: "arm64"', result)
        self.assertIn('redistDir = os.path.join(redistDir, redistArch)', result)

    def test_patch_is_idempotent(self):
        once = patch(SOURCE)
        self.assertEqual(patch(once), once)

    def test_unexpected_runtime_structure_is_rejected(self):
        with self.assertRaises(ValueError):
            patch("class Package: pass\n")


if __name__ == "__main__":
    unittest.main()
