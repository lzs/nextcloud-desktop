#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Print the zlib import library that Craft's MSVC Python build links.

The ARM64 workflow bootstraps libs/zlib before libs/python and then checks the
import library exists. Its name depends on the pinned Craft revision: zlib 1.3.1
installed lib/zlib.lib, while zlib 1.3.2 with Craft's "really goes back to
zlib1.dll name" patch installs lib/zlib1.lib. Reading the name from the Python
blueprint keeps the check tied to what the next package actually links.
"""

from pathlib import Path
import re
import sys

ADD_LIB = re.compile(r'addLib\(\s*"ZLIB"\s*,\s*"(?P<name>[A-Za-z0-9_.-]+)"')


def import_library(python_blueprint: str) -> str:
    names = {match.group("name") for match in ADD_LIB.finditer(python_blueprint)}
    if len(names) != 1:
        raise ValueError(f"Expected one zlib library in the Python blueprint, found {sorted(names)}")
    return f"{names.pop()}.lib"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: arm64_zlib.py <blueprints/libs/python/python.py>")
    print(import_library(Path(sys.argv[1]).read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
