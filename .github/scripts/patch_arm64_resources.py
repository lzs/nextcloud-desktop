#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compile GNU autotools Windows resources as native ARM64 COFF objects."""
import ast
from pathlib import Path
import shutil
import sys


ARM64_RESOURCE_BLOCK = '''        # ARM64 resource compiler override: GNU windres defaults to x64 COFF.
        from CraftCompiler import CraftCompiler
        from CraftCore import CraftCore
        if CraftCore.compiler.isWindows and CraftCore.compiler.architecture == CraftCompiler.Architecture.arm64:
            import sys
            python = self.shell.toNativePath(sys.executable)
            wrapper = self.shell.toNativePath(
                CraftCore.standardDirs.craftRoot() / "craft" / "bin" / "arm64_windres.py"
            )
            compiler = f'"{python}" "{wrapper}"'
            # Configure libtool consistently, and propagate to recursive make.
            for settings in (self.subinfo.options.configure, self.subinfo.options.make):
                settings.args += [f"RC={compiler}", f"WINDRES={compiler}"]
'''

PACKAGE = '''class Package(AutoToolsPackageBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.shell.useMSVCCompatEnv = True
''' + ARM64_RESOURCE_BLOCK


def _package_class(source: str, package_name: str) -> tuple[ast.Module, ast.ClassDef]:
    tree = ast.parse(source)
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Package"]
    if len(classes) != 1 or [ast.unparse(base) for base in classes[0].bases] != ["AutoToolsPackageBase"]:
        raise ValueError(f"{package_name} Package structure changed; review the patch")
    return tree, classes[0]


def patch(source: str) -> str:
    """Replace libunistring's minimal Package class with the ARM64-aware form."""
    _, node = _package_class(source, "libunistring")
    lines = source.splitlines(keepends=True)
    result = "".join(lines[:node.lineno - 1]) + PACKAGE + "".join(lines[node.end_lineno:])
    ast.parse(result)
    return result


def patch_gettext(source: str) -> str:
    """Inject the ARM64 resource compiler into gettext without replacing its recipe."""
    if "# ARM64 resource compiler override:" in source:
        return source

    _, package = _package_class(source, "gettext")
    initializers = [
        node for node in package.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "__init__"
    ]
    if len(initializers) != 1:
        raise ValueError("gettext Package.__init__ structure changed; review the patch")

    anchors = []
    for statement in initializers[0].body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        if ast.unparse(statement.targets[0]) != "self.shell.useMSVCCompatEnv":
            continue
        if isinstance(statement.value, ast.Constant) and statement.value.value is True:
            anchors.append(statement)
    if len(anchors) != 1:
        raise ValueError("gettext MSVC environment setup changed; review the patch")

    lines = source.splitlines(keepends=True)
    insertion = anchors[0].end_lineno
    result = "".join(lines[:insertion]) + ARM64_RESOURCE_BLOCK + "".join(lines[insertion:])
    ast.parse(result)
    return result


def apply(craft_clone: Path, helper_source: Path) -> None:
    libunistring_directory = craft_clone / "blueprints/libs/libunistring"
    libunistring = libunistring_directory / "libunistring.py"
    libunistring.write_text(patch(libunistring.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")

    gettext = craft_clone / "blueprints/libs/gettext/gettext.py"
    gettext.write_text(patch_gettext(gettext.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")

    helper_destination = craft_clone / "bin" / "arm64_windres.py"
    helper_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(helper_source, helper_destination)

    # Craft treats Python files inside blueprint package directories as recipe
    # candidates. Keep the helper in craft/bin so blueprint discovery cannot
    # mistake it for a second package recipe.
    for directory in (libunistring_directory, gettext.parent):
        (directory / "arm64_windres.py").unlink(missing_ok=True)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: patch_arm64_resources.py <craft-clone>")
    apply(Path(sys.argv[1]), Path(__file__).with_name("arm64_windres.py"))
    print("Patched libunistring/gettext: explicit RC/WINDRES using rc.exe and ARM64 cvtres.exe")


if __name__ == "__main__":
    main()
