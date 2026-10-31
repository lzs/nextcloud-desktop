# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patch_download_retry_arm64 import patch


SOURCE = '''import os
import urllib


def getFile(url, destdir, filename="", quiet=None) -> bool:
    """download file from 'url' into 'destdir'"""
    return fetchOnce(url, destdir, filename, quiet)


def curlFile(url, destdir, filename, quiet):
    return False
'''

LIBUNISTRING = "https://ftp.gnu.org/gnu/libunistring/libunistring-1.4.1.tar.xz"


def load(source, results):
    """Execute the patched module with a scripted fetchOnce and no sleeping."""
    calls = []

    def fetchOnce(url, destdir, filename, quiet):
        calls.append((url, filename))
        return results.pop(0) if results else False

    log = types.SimpleNamespace(warning=lambda message: None)
    namespace = {"fetchOnce": fetchOnce, "CraftCore": types.SimpleNamespace(log=log)}
    exec(compile(source, "GetFiles.py", "exec"), namespace)
    return namespace, calls


class DownloadRetryPatchTests(unittest.TestCase):
    def test_first_success_downloads_once(self):
        module, calls = load(patch(SOURCE), [True])
        self.assertTrue(module["getFile"](LIBUNISTRING, "dl"))
        self.assertEqual(calls, [(LIBUNISTRING, "libunistring-1.4.1.tar.xz")])

    def test_gnu_download_falls_back_to_mirrors_with_same_filename(self):
        module, calls = load(patch(SOURCE), [False, True])
        self.assertTrue(module["getFile"](LIBUNISTRING, "dl"))
        self.assertEqual(
            calls[1],
            ("https://ftpmirror.gnu.org/libunistring/libunistring-1.4.1.tar.xz", "libunistring-1.4.1.tar.xz"),
        )

    def test_gnu_pub_prefix_also_falls_back_to_mirrors(self):
        url = "https://ftp.gnu.org/pub/gnu/gettext/gettext-0.22.3.tar.gz"
        module, calls = load(patch(SOURCE), [False, False, True])
        self.assertTrue(module["getFile"](url, "dl", "gettext-0.22.3.tar.gz"))
        self.assertEqual(
            [c[0] for c in calls],
            [
                url,
                "https://ftpmirror.gnu.org/gettext/gettext-0.22.3.tar.gz",
                "https://mirrors.kernel.org/gnu/gettext/gettext-0.22.3.tar.gz",
            ],
        )

    def test_non_gnu_download_is_retried_after_backoff(self):
        url = "https://github.com/OpenSC/libp11/releases/download/libp11-0.4.17/libp11-0.4.17.tar.gz"
        with mock.patch("time.sleep") as sleep:
            module, calls = load(patch(SOURCE), [False, False, True])
            self.assertTrue(module["getFile"](url, "dl", "p11.tgz"))
        self.assertEqual([c[0] for c in calls], [url, url, url])
        self.assertEqual({c[1] for c in calls}, {"p11.tgz"})
        self.assertEqual(sleep.call_count, 2)

    def test_persistent_failure_still_fails(self):
        with mock.patch("time.sleep"):
            module, calls = load(patch(SOURCE), [])
            self.assertFalse(module["getFile"](LIBUNISTRING, "dl"))
        self.assertEqual(len(calls), 9)

    def test_patch_is_idempotent(self):
        once = patch(SOURCE)
        self.assertEqual(patch(once), once)
        self.assertEqual(once.count("def getFile("), 1)

    def test_unexpected_structure_is_rejected(self):
        with self.assertRaises(ValueError):
            patch("def getFile(url):\n    pass\n")

    def test_workflow_applies_patch_to_pinned_craft(self):
        from unittest.mock import patch as mock_patch
        import arm64_prepare
        root = Path('pinned-craft')
        with mock_patch.object(arm64_prepare, 'patch_script') as invoke:
            arm64_prepare.patch_craft(root)
        invoke.assert_any_call('patch_download_retry_arm64.py', root / 'bin/Utils/GetFiles.py')


if __name__ == "__main__":
    unittest.main()
