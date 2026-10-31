#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Dudiebug
# SPDX-License-Identifier: GPL-2.0-or-later
"""
Patch Craft's NSIS packager and Nextcloud blueprint for ARM64 installer parity.

Fixes:
1. NullsoftInstallerPackager.py: treat ARM64 as 64-bit (PROGRAMFILES64)
2. NullsoftInstaller.nsi: add "Launch after install" checkbox
3. nextcloud-client.py blueprint: set executable, icon, and version
"""
import sys
import os
import re


def patch_nsis_packager(path):
    """Treat ARM64 as 64-bit for install directory and add finishpage_run support."""
    with open(path, "r", encoding="utf-8") as f:
        s = f.read()

    # Replace single x86_64 checks with (x86_64 or arm64)
    s = s.replace(
        "CraftCore.compiler.architecture == CraftCompiler.Architecture.x86_64 else \"$PROGRAMFILES\"",
        "CraftCore.compiler.architecture in (CraftCompiler.Architecture.x86_64, CraftCompiler.Architecture.arm64) else \"$PROGRAMFILES\"",
    )
    s = s.replace(
        'CraftCore.compiler.architecture == CraftCompiler.Architecture.x86_64 else ""',
        'CraftCore.compiler.architecture in (CraftCompiler.Architecture.x86_64, CraftCompiler.Architecture.arm64) else ""',
    )

    # Add finishpage_run_define after shortcut creation
    old = '            shortcuts.append(self._createShortcut(defines["productname"], defines["executable"]))\n            del defines["executable"]'
    new = (
        '            shortcuts.append(self._createShortcut(defines["productname"], defines["executable"]))\n'
        '            # Pass executable to NSIS for "Launch after install" checkbox\n'
        '            defines["finishpage_run_define"] = f\'!define FINISHPAGE_RUN_EXECUTABLE "{OsUtils.toNativePath(defines["executable"])}"\'\n'
        '            del defines["executable"]'
    )
    if old in s:
        s = s.replace(old, new)
    # Add the else branch for when no executable is set
    if 'finishpage_run_define' in s and 'defines["finishpage_run_define"] = ""' not in s:
        s = s.replace(
            '        for short in defines["shortcuts"]:',
            '        if "finishpage_run_define" not in defines:\n'
            '            defines["finishpage_run_define"] = ""\n'
            '        for short in defines["shortcuts"]:',
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write(s)
    print(f"Patched {path}")


def patch_nsis_template(path):
    """Add MUI_FINISHPAGE_RUN support to the NSIS template."""
    with open(path, "r", encoding="utf-8") as f:
        s = f.read()

    if "FINISHPAGE_RUN_EXECUTABLE" in s:
        print(f"Skipping {path}: already patched")
        return

    old = '!insertmacro MUI_PAGE_FINISH'
    new = (
        '@{finishpage_run_define}\n'
        '!ifdef FINISHPAGE_RUN_EXECUTABLE\n'
        '!define MUI_FINISHPAGE_RUN "$INSTDIR\\${FINISHPAGE_RUN_EXECUTABLE}"\n'
        '!define MUI_FINISHPAGE_RUN_TEXT "Launch @{productname}"\n'
        '!endif\n'
        '!insertmacro MUI_PAGE_FINISH'
    )
    s = s.replace(old, new, 1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(s)
    print(f"Patched {path}")


def patch_blueprint(path):
    """Fix createPackage() to set executable, icon, and version."""
    with open(path, "r", encoding="utf-8") as f:
        s = f.read()

    if 'self.applicationExecutable' not in s:
        print(f"Skipping {path}: applicationExecutable not found (already patched?)")
        return

    # Replace applicationExecutable with defines["executable"]
    s = s.replace(
        'self.applicationExecutable = "nextcloud"',
        'self.defines["executable"] = "bin\\\\nextcloud.exe"',
    )

    # Inject icon and version logic after the executable line
    inject = '''
        # Use the Nextcloud icon if available
        ncIcon = os.path.join(self.buildDir(), "src", "gui", "Nextcloud.ico")
        if os.path.isfile(ncIcon):
            self.defines["icon"] = ncIcon
        # Read version from VERSION.cmake
        versionCmake = os.path.join(self.sourceDir(), "VERSION.cmake")
        if os.path.isfile(versionCmake):
            import re as _re
            with open(versionCmake, "r") as _f:
                _txt = _f.read()
            _major = _re.search(r"MIRALL_VERSION_MAJOR\\s+(\\d+)", _txt)
            _minor = _re.search(r"MIRALL_VERSION_MINOR\\s+(\\d+)", _txt)
            _patch = _re.search(r"MIRALL_VERSION_PATCH\\s+(\\d+)", _txt)
            if _major and _minor and _patch:
                self.defines["version"] = f"{_major.group(1)}.{_minor.group(1)}.{_patch.group(1)}"
'''
    s = s.replace(
        'self.defines["executable"] = "bin\\\\nextcloud.exe"\n',
        'self.defines["executable"] = "bin\\\\nextcloud.exe"\n' + inject,
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(s)
    print(f"Patched {path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: patch-nsis-and-blueprint.py <craft-clone-dir> [blueprint-path]")
        sys.exit(1)

    craft_dir = sys.argv[1]

    packager_path = os.path.join(craft_dir, "bin", "Packager", "NullsoftInstallerPackager.py")
    template_path = os.path.join(craft_dir, "bin", "Packager", "Nsis", "NullsoftInstaller.nsi")

    if os.path.isfile(packager_path):
        patch_nsis_packager(packager_path)
    else:
        print(f"WARN: {packager_path} not found")

    if os.path.isfile(template_path):
        patch_nsis_template(template_path)
    else:
        print(f"WARN: {template_path} not found")

    if len(sys.argv) >= 3:
        blueprint_path = sys.argv[2]
        if os.path.isfile(blueprint_path):
            patch_blueprint(blueprint_path)
        else:
            print(f"WARN: {blueprint_path} not found")
