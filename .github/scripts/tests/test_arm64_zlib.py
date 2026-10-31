# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm64_zlib import import_library  # noqa: E402


class Arm64ZlibTests(unittest.TestCase):
    def test_craft_with_zlib_1_3_1_links_zlib_lib(self):
        source = '            addLib("SSL", "libssl")\n            addLib("ZLIB", "zlib")\n'
        self.assertEqual(import_library(source), "zlib.lib")

    def test_craft_with_zlib_1_3_2_links_zlib1_lib(self):
        source = '            addLib("EXPAT", "libexpat", "libexpatd")\n            addLib("ZLIB", "zlib1")\n'
        self.assertEqual(import_library(source), "zlib1.lib")

    def test_missing_zlib_library_is_an_error(self):
        with self.assertRaises(ValueError):
            import_library('addLib("SSL", "libssl")\n')

    def test_conflicting_zlib_libraries_are_an_error(self):
        with self.assertRaises(ValueError):
            import_library('addLib("ZLIB", "zlib")\naddLib("ZLIB", "zlib1")\n')


if __name__ == "__main__":
    unittest.main()
