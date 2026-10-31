#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Generate a native Windows ARM64 Craft configuration from upstream settings."""

import argparse
import configparser
import io
from pathlib import Path
import re
import sys

# Keep the CraftMaster target key stable so existing workflow paths/caches and
# command lines continue to resolve, but select the compiler ABI actually
# installed on GitHub's migrated Windows 11 ARM64 runner.
TARGET = "windows-msvc2022_arm64-cl"
COMPILER_ABI = "windows-msvc2026_arm64-cl"
QT_COMPILER = "msvc2026_arm64"
MSVC_TOOLSET = "14.44"


def configure(source: str, revision: str, python_directory: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        raise ValueError("A full, locally committed Craft revision is required")
    if not python_directory or "\n" in python_directory or "\r" in python_directory:
        raise ValueError("A single Python directory is required")
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read_string(source)
    for key in ("CraftUrl", "CraftRevision"):
        if not config.get("General", key, fallback="").strip():
            raise ValueError(f"Upstream configuration is missing General/{key}")
    config["General"]["CraftRevision"] = revision
    if not config.has_section(TARGET):
        config.add_section(TARGET)
    config[TARGET].update({
        "Packager/PackageType": "NullsoftInstallerPackager",
        "QtSDK/Compiler": QT_COMPILER,
        "General/ABI": COMPILER_ABI,
        "General/MSVCToolset": MSVC_TOOLSET,
        "Paths/Python": python_directory,
        "ShortPath/DriveLetter": "Q:",
        "Packager/UseCache": "False",
        "Packager/CreateCache": "False",
    })
    if not config.has_section("BlueprintSettings"):
        config.add_section("BlueprintSettings")
    config["BlueprintSettings"]["nextcloud-client.buildTests"] = "True"
    config["BlueprintSettings"]["nextcloud-client.buildWithWebEngine"] = "False"
    if not config.has_section("Env"):
        config.add_section("Env")
    # pip 24.2+ reads the Windows certificate store through truststore by
    # default. The hosted Windows ARM64 image exposes a malformed certificate
    # that CPython rejects before pip can fall back to its bundled CA store.
    # Keep TLS verification enabled while opting this generated ARM64 build out
    # of the system certificate store.
    config["Env"]["PIP_USE_DEPRECATED"] = "legacy-certs"
    output = io.StringIO()
    config.write(output)
    return output.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("revision")
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("Generated configuration must not overwrite upstream settings")
    result = configure(args.source.read_text(encoding="utf-8-sig"), args.revision,
                       str(Path(sys.executable).parent))
    args.output.write_text(result, encoding="utf-8", newline="\n")
    print(f"Configured {TARGET} for {COMPILER_ABI} at Craft revision {args.revision}")


if __name__ == "__main__":
    main()
