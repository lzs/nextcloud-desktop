#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Dudiebug
# SPDX-License-Identifier: GPL-2.0-or-later

"""Apply Windows ARM64 fixes to stable Nextcloud/KDE Craft blueprints."""

import re
import sys


def _read_normalized(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        source = f.read()
    line_ending = "\r\n" if "\r\n" in source else "\n"
    return source.replace("\r\n", "\n"), line_ending


def _write_preserving_line_endings(path, source, line_ending):
    if line_ending == "\r\n":
        source = source.replace("\n", "\r\n")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(source)


def patch_libjpeg(path):
    s, line_ending = _read_normalized(path)

    if "-DWITH_SIMD=OFF" in s:
        print(f"SKIP {path}: ARM64 SIMD patch already present")
        return

    old_imports = "import info\nfrom Package.CMakePackageBase import CMakePackageBase\nfrom Utils import CraftHash\n"
    new_imports = "import info\nfrom CraftCompiler import CraftCompiler\nfrom CraftCore import CraftCore\nfrom Package.CMakePackageBase import CMakePackageBase\nfrom Utils import CraftHash\n"
    if old_imports not in s:
        raise RuntimeError("libjpeg-turbo import block changed upstream")
    s = s.replace(old_imports, new_imports)

    needle = (
        '        else:\n'
        '            self.subinfo.options.configure.args += ["-DENABLE_SHARED=ON", "-DENABLE_STATIC=OFF"]\n'
    )
    replacement = needle + (
        '        if CraftCore.compiler.isWindows and CraftCore.compiler.architecture == CraftCompiler.Architecture.arm64:\n'
        '            self.subinfo.options.configure.args += ["-DWITH_SIMD=OFF"]\n'
    )
    if needle not in s:
        raise RuntimeError("libjpeg-turbo Package block changed upstream")
    s = s.replace(needle, replacement, 1)

    _write_preserving_line_endings(path, s, line_ending)
    print(f"Patched {path}: disabled x86 SIMD for Windows ARM64")


def patch_pixman(path):
    s, line_ending = _read_normalized(path)

    if "-Dmmx=disabled" in s and "-Dsse2=disabled" in s and "-Dssse3=disabled" in s:
        print(f"SKIP {path}: Windows ARM64 SIMD patch already present")
        return

    needle = (
        'class Package(MesonPackageBase):\n'
        '    def __init__(self, **kwargs):\n'
        '        super().__init__(**kwargs)\n'
    )
    replacement = needle + (
        '        from CraftCompiler import CraftCompiler\n'
        '        if CraftCore.compiler.isWindows and CraftCore.compiler.architecture == CraftCompiler.Architecture.arm64:\n'
        '            self.subinfo.options.configure.args += [\n'
        '                "-Da64-neon=disabled",\n'
        '                "-Dmmx=disabled",\n'
        '                "-Dsse2=disabled",\n'
        '                "-Dssse3=disabled",\n'
        '            ]\n'
    )
    if needle not in s:
        raise RuntimeError("pixman Package block changed upstream")
    s = s.replace(needle, replacement, 1)

    _write_preserving_line_endings(path, s, line_ending)
    print(f"Patched {path}: disabled unsupported SIMD paths for Windows ARM64")


LIBP11_MARKER = "# Windows ARM64: libp11 make.rules.mak machine"

# Earlier tooling passed MACHINE on the nmake command line. libp11's top-level
# Makefile.mak re-invokes nmake in src/ without forwarding it, so the child only
# sees it as an inherited macro, which make.rules.mak's unconditional
# "MACHINE = /MACHINE:X86" overrides (run 37476929089). Restored dependency
# workspaces may still carry that blueprint edit, so remove it on upgrade.
LIBP11_LEGACY_PATCH = (
    '        elif CraftCore.compiler.architecture == CraftCompiler.Architecture.arm64:\n'
    '             self.subinfo.options.make.args += " MACHINE=/MACHINE:ARM64"\n'
)


def patch_libp11(path):
    s, line_ending = _read_normalized(path)

    if LIBP11_MARKER in s:
        print(f"SKIP {path}: Windows ARM64 linker machine patch already present")
        return

    s = s.replace(LIBP11_LEGACY_PATCH, "", 1)

    # make.rules.mak only knows x64 (BUILD_FOR=WIN64) and otherwise hardcodes
    # /MACHINE:X86. Rewrite that default in the unpacked sources before nmake
    # runs, so every recursive nmake and every DLL link uses /MACHINE:ARM64.
    needle = (
        '        if CraftCore.compiler.architecture == CraftCompiler.Architecture.x86_64:\n'
        '             self.subinfo.options.make.args += f" BUILD_FOR=WIN64"\n'
        '\n'
        '    def install(self):\n'
    )
    replacement = (
        '        if CraftCore.compiler.architecture == CraftCompiler.Architecture.x86_64:\n'
        '             self.subinfo.options.make.args += f" BUILD_FOR=WIN64"\n'
        '\n'
        '    def make(self):\n'
        f'        {LIBP11_MARKER}\n'
        '        if CraftCore.compiler.architecture == CraftCompiler.Architecture.arm64:\n'
        '            rules = os.path.join(self.sourceDir(), "make.rules.mak")\n'
        '            with open(rules, "rt") as f:\n'
        '                content = f.read()\n'
        '            if "MACHINE = /MACHINE:ARM64" not in content:\n'
        '                if content.count("MACHINE = /MACHINE:X86") != 1:\n'
        '                    CraftCore.log.error(f"Unexpected libp11 machine settings in {rules}")\n'
        '                    return False\n'
        '                with open(rules, "wt") as f:\n'
        '                    f.write(content.replace("MACHINE = /MACHINE:X86", "MACHINE = /MACHINE:ARM64"))\n'
        '        return super().make()\n'
        '\n'
        '    def install(self):\n'
    )
    if s.count(needle) != 1:
        raise RuntimeError("libp11 nmake architecture block changed upstream")
    s = s.replace(needle, replacement, 1)

    _write_preserving_line_endings(path, s, line_ending)
    print(f"Patched {path}: link libp11 for Windows ARM64")


def patch_qttools(path):
    s, line_ending = _read_normalized(path)

    if "-DFEATURE_clang=OFF\", \"-DFEATURE_clangcpp=OFF\"]  # Windows ARM64" in s:
        print(f"SKIP {path}: Windows ARM64 LLVM patch already present")
        return

    # qttools only needs libs/llvm for qdoc and the clang-based lupdate parser,
    # which the client does not use. x64 gets LLVM from the binary cache, but
    # ARM64 has no cache and building LLVM from source consumes most of a
    # six-hour runner window (run 37434281380). Lupdate, lrelease and the
    # other Linguist tools do not need clang.
    dep_needle = '        self.runtimeDependencies["libs/llvm"] = None\n'
    dep_replacement = (
        '        from CraftCompiler import CraftCompiler\n'
        '        if not (CraftCore.compiler.isWindows and CraftCore.compiler.architecture == CraftCompiler.Architecture.arm64):\n'
        '            self.runtimeDependencies["libs/llvm"] = None\n'
    )
    if s.count(dep_needle) != 1:
        raise RuntimeError("qttools libs/llvm dependency changed upstream")
    s = s.replace(dep_needle, dep_replacement, 1)

    init_needle = (
        'class Package(CraftPackageObject.get("libs/qt6").pattern):\n'
        '    def __init__(self, **kwargs):\n'
        '        super().__init__(**kwargs)\n'
    )
    init_replacement = init_needle + (
        '        from CraftCompiler import CraftCompiler\n'
        '        if CraftCore.compiler.isWindows and CraftCore.compiler.architecture == CraftCompiler.Architecture.arm64:\n'
        '            self.subinfo.options.configure.args += ["-DFEATURE_clang=OFF", "-DFEATURE_clangcpp=OFF"]  # Windows ARM64\n'
    )
    if init_needle not in s:
        raise RuntimeError("qttools Package block changed upstream")
    s = s.replace(init_needle, init_replacement, 1)

    _write_preserving_line_endings(path, s, line_ending)
    print(f"Patched {path}: build qttools without LLVM for Windows ARM64")


def patch_nextcloud_client_imports(path):
    s, line_ending = _read_normalized(path)

    if re.search(r"(?m)^import os$", s):
        print(f"SKIP {path}: os import already present")
        return

    # createPackage() calls os.path.join(), but the blueprint relies on
    # "from Package.CMakePackageBase import *" for os, which the pinned Craft
    # revision no longer re-exports (run 37515196377: NameError: name 'os' is
    # not defined). The packaging fixes from patch-nsis-and-blueprint.py also
    # use os. This runs on restored workspaces too, unlike that one-time patch.
    needle = "import info\n"
    if not s.startswith(needle) and f"\n{needle}" not in s:
        raise RuntimeError("nextcloud-client import block changed upstream")
    s = re.sub(r"(?m)^import info$", "import info\nimport os", s, count=1)

    _write_preserving_line_endings(path, s, line_ending)
    print(f"Patched {path}: import os for createPackage()")


if __name__ == "__main__":
    if len(sys.argv) != 6:
        print("Usage: patch-kde-blueprints-arm64.py <libjpeg-turbo.py> <pixman.py> <libp11.py> <qttools.py> <nextcloud-client.py>")
        sys.exit(2)
    patch_libjpeg(sys.argv[1])
    patch_pixman(sys.argv[2])
    patch_libp11(sys.argv[3])
    patch_qttools(sys.argv[4])
    patch_nextcloud_client_imports(sys.argv[5])
