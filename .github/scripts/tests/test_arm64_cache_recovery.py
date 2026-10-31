# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from arm64_cache_recovery import build_plan, compatible_changes, select_fingerprint

ORIGINAL = '''name: Build
      - name: Fingerprint the dependency build inputs
        run: original hash
      - name: Build dependencies
        run: original dependency command
'''
UPDATED = ORIGINAL.replace('run: original hash', 'run: validated recovery hash')


class CacheRecoveryTests(unittest.TestCase):
    def test_validation_only_changes_reuse_dependencies(self):
        changed = ['.github/scripts/arm64_verify.py', '.github/scripts/arm64_cache_recovery.py',
                   '.github/scripts/tests/test_arm64_build.py', '.github/workflows/arm64-release.yml']
        self.assertTrue(compatible_changes(changed, ORIGINAL, UPDATED))

    def test_dependency_recipe_changes_require_new_cache(self):
        for path in ('.github/arm64-pins.json', 'craftmaster.ini',
                     '.github/scripts/arm64_prepare.py', '.github/scripts/new-recipe.py',
                     'src/libsync/filesystem.cpp'):
            with self.subTest(path=path):
                self.assertFalse(compatible_changes([path], ORIGINAL, UPDATED))

    def test_dependency_command_changes_require_new_cache(self):
        changed = UPDATED.replace('original dependency command', 'different dependency command')
        self.assertFalse(compatible_changes(['.github/workflows/arm64-release.yml'], ORIGINAL, changed))

    def test_missing_fingerprint_step_rejected(self):
        with self.assertRaises(ValueError):
            build_plan('name: unknown workflow')

    def test_crlf_is_normalized(self):
        self.assertEqual(build_plan(ORIGINAL), build_plan(ORIGINAL.replace('\n', '\r\n')))

    def test_malformed_fingerprints_rejected_before_git(self):
        with patch('arm64_cache_recovery.subprocess.check_output') as git:
            for current, saved in (('short', 'a' * 64), ('a' * 64, 'b' * 64 + '\n')):
                with self.assertRaises(ValueError):
                    select_fingerprint(current, saved)
            git.assert_not_called()

    def test_selects_saved_key_only_for_compatible_changes(self):
        for changed, expected in (('.github/scripts/arm64_verify.py\n', 'b' * 64),
                                  ('.github/arm64-pins.json\n', 'a' * 64)):
            with self.subTest(changed=changed), \
                    patch('arm64_cache_recovery.subprocess.check_output', side_effect=[changed, ORIGINAL]), \
                    patch.object(Path, 'read_text', return_value=UPDATED):
                self.assertEqual(select_fingerprint('a' * 64, 'b' * 64), expected)


if __name__ == '__main__':
    unittest.main()
