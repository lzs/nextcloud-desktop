#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Make Craft honor an explicitly selected legacy MSVC toolset on VS 2026."""

from pathlib import Path
import sys


SIGNATURE = "    def getMsvcPlatformToolset(self):\n"
MARKER = 'self.msvcToolset.startswith("14.44")'
INSERT = '''        # VS 2026 hosted runners also carry the 14.44 ARM64 toolset. When an
        # explicit 14.44 compiler is selected through vcvarsall, use the
        # matching MSBuild PlatformToolset instead of forcing the ABI default
        # back to v145.
        if self.msvcToolset and self.msvcToolset.startswith("14.44"):
            return 143
'''


def patch(source: str) -> str:
    if MARKER in source:
        return source
    if source.count(SIGNATURE) != 1:
        raise ValueError("CraftCompiler.getMsvcPlatformToolset changed upstream")
    return source.replace(SIGNATURE, SIGNATURE + INSERT, 1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: patch_msvc_toolset_arm64.py <CraftCompiler.py>")
    path = Path(sys.argv[1])
    path.write_text(patch(path.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    print(f"Patched {path}: explicit MSVC 14.44 maps to PlatformToolset v143")


if __name__ == "__main__":
    main()
