#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Patch Craft's MSVC runtime recipe for VS 2026 and native Windows ARM64."""

from pathlib import Path
import sys


def patch(source: str) -> str:
    old_compiler = '''                    if CraftCore.compiler.isMSVC2026():
                        flavor = "2026"
                    if CraftCore.compiler.isMSVC2022():
                        flavor = "2022"
'''
    new_compiler = '''                    if CraftCore.compiler.isMSVC2026():
                        flavor = "2026"
                    elif CraftCore.compiler.isMSVC2022():
                        flavor = "2022"
'''
    if old_compiler in source:
        source = source.replace(old_compiler, new_compiler, 1)
    elif new_compiler not in source:
        raise ValueError("Craft runtime compiler-selection block changed upstream")

    old_arch = '''                    redistDir = os.path.join(redistDir, "x86" if CraftCore.compiler.architecture == CraftCompiler.Architecture.x86_32 else "x64")
'''
    new_arch = '''                    redistArch = {
                        CraftCompiler.Architecture.x86_32: "x86",
                        CraftCompiler.Architecture.x86_64: "x64",
                        CraftCompiler.Architecture.arm64: "arm64",
                    }.get(CraftCore.compiler.architecture)
                    if not redistArch:
                        raise Exception(f"Unsupported MSVC runtime architecture {CraftCore.compiler.architecture}")
                    redistDir = os.path.join(redistDir, redistArch)
'''
    if old_arch in source:
        source = source.replace(old_arch, new_arch, 1)
    elif new_arch not in source:
        raise ValueError("Craft runtime redistributable architecture block changed upstream")

    return source


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: patch_runtime_arm64.py <runtime.py>")
    path = Path(sys.argv[1])
    path.write_text(patch(path.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    print(f"Patched {path}: VS 2026 compiler selection and ARM64 runtime redistributables")


if __name__ == "__main__":
    main()
