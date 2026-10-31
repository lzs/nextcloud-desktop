#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Make Craft source downloads survive transient mirror outages.

Craft's ArchiveSource.fetch() aborts the whole dependency checkpoint on the
first failed GetFiles.getFile() call; its own retry loop only covers digest
mismatches. A single connect timeout to ftp.gnu.org therefore costs a full
rebuild on the ARM64 runner. This wraps getFile() so each download is retried
with backoff and GNU tarballs fall back to the official GNU mirror network.
Craft still verifies every archive against the blueprint's SHA-256 digest.
"""

from pathlib import Path
import sys


SIGNATURE = 'def getFile(url, destdir, filename="", quiet=None) -> bool:\n'
RENAMED = 'def _getFileOnce(url, destdir, filename="", quiet=None) -> bool:\n'
MARKER = "def _getFileOnce("
WRAPPER = '''

# Windows ARM64 build: retry transient download failures and use GNU mirrors.
_GNU_PRIMARY = (
    "https://ftp.gnu.org/gnu/", "http://ftp.gnu.org/gnu/",
    "https://ftp.gnu.org/pub/gnu/", "http://ftp.gnu.org/pub/gnu/",
)
_GNU_MIRRORS = ("https://ftpmirror.gnu.org/", "https://mirrors.kernel.org/gnu/")
_DOWNLOAD_ROUNDS = 3


def _downloadCandidates(url):
    candidates = [url]
    for prefix in _GNU_PRIMARY:
        if url.startswith(prefix):
            candidates += [mirror + url[len(prefix):] for mirror in _GNU_MIRRORS]
            break
    return candidates


def getFile(url, destdir, filename="", quiet=None) -> bool:
    import time
    import urllib.parse

    if not url or urllib.parse.urlparse(url).scheme == "s3":
        return _getFileOnce(url, destdir, filename, quiet)
    if not filename:
        filename = os.path.basename(urllib.parse.urlparse(url).path)
    for attempt in range(_DOWNLOAD_ROUNDS):
        for candidate in _downloadCandidates(url):
            if _getFileOnce(candidate, destdir, filename, quiet):
                return True
            CraftCore.log.warning(f"Download attempt {attempt + 1} failed: {candidate}")
        if attempt + 1 < _DOWNLOAD_ROUNDS:
            time.sleep(30 * (attempt + 1))
    return False
'''


def patch(source: str) -> str:
    if MARKER in source:
        return source
    if source.count(SIGNATURE) != 1:
        raise ValueError("Craft GetFiles.getFile signature changed upstream")
    return source.replace(SIGNATURE, RENAMED, 1).rstrip("\n") + "\n" + WRAPPER


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: patch_download_retry_arm64.py <GetFiles.py>")
    path = Path(sys.argv[1])
    path.write_text(patch(path.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    print(f"Patched {path}: retry downloads and fall back to GNU mirrors")


if __name__ == "__main__":
    main()
