#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compile the RC-to-COFF subset used by libunistring with Windows SDK tools.

Unlike a windres --preprocessor=cl pipeline, rc.exe accepts an explicit .rc
filename. cvtres then creates a real ARM64 object, without header rewriting.
"""
from dataclasses import dataclass, field
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile


@dataclass
class Options:
    source: str = ""
    output: str = ""
    defines: list[str] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)


def windows_path(value: str) -> str:
    match = re.match(r"^/([a-zA-Z])/(.*)$", value)
    return f"{match[1]}:/{match[2]}" if match else value


def parse_arguments(arguments: list[str]) -> Options:
    options = Options()
    index = 0
    value_flags = {"-i", "--input", "-o", "--output", "-I", "--include-dir",
                   "-D", "--define", "-J", "--input-format", "-O", "--output-format",
                   "-F", "--target", "--preprocessor", "--preprocessor-arg"}
    while index < len(arguments):
        flag = arguments[index]
        index += 1
        if flag == "--use-temp-file":
            continue
        if flag.startswith("--") and "=" in flag:
            flag, value = flag.split("=", 1)
        elif flag in value_flags:
            if index == len(arguments):
                raise ValueError(f"Missing value for {flag}")
            value = arguments[index]
            index += 1
        elif flag[:2] in ("-D", "-I", "-i", "-o") and len(flag) > 2:
            flag, value = flag[:2], flag[2:]
        else:
            raise ValueError(f"Unsupported resource compiler argument: {flag}")
        if flag in ("-i", "--input"):
            options.source = windows_path(value)
        elif flag in ("-o", "--output"):
            options.output = windows_path(value)
        elif flag in ("-D", "--define"):
            options.defines.append(re.sub(r'\\+"', '"', value))
        elif flag in ("-I", "--include-dir"):
            options.includes.append(windows_path(value))
        elif flag in ("-J", "--input-format"):
            if value.lower() != "rc":
                raise ValueError("Only RC input is supported")
        elif flag in ("-O", "--output-format"):
            if value.lower() != "coff":
                raise ValueError("Only COFF output is supported")
        elif flag in ("-F", "--target"):
            if value not in ("pe-x86-64", "pe-arm64-little", "pe-aarch64-little"):
                raise ValueError(f"Unexpected windres target: {value}")
        elif flag == "--preprocessor":
            if Path(value.replace("\\", "/")).name.lower() not in ("cl", "cl.exe"):
                raise ValueError("Only the MSVC preprocessor convention is supported")
        elif flag == "--preprocessor-arg":
            if value.lower() in ("-nologo", "/nologo", "-ep", "/ep"):
                continue
            if value[:2].lower() in ("-d", "/d"):
                options.defines.append(re.sub(r'\\+"', '"', value[2:]))
            elif value[:2].lower() in ("-i", "/i"):
                options.includes.append(windows_path(value[2:]))
            else:
                raise ValueError(f"Unsupported preprocessor argument: {value}")
        else:
            raise ValueError(f"Unsupported resource compiler option: {flag}")
    if not options.source or not options.output or "-" in (options.source, options.output):
        raise ValueError("Explicit input and output filenames are required")
    return options


def compile_resource(options: Options) -> None:
    rc = shutil.which("rc.exe")
    cvtres = shutil.which("cvtres.exe")
    if not rc or not cvtres:
        raise RuntimeError("rc.exe and cvtres.exe must be available in the MSVC ARM64 environment")
    source = Path(options.source).resolve(strict=True)
    output = Path(options.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nextcloud-arm64-resource-") as directory:
        res = str(Path(directory) / "resource.res")
        command = [rc, "/nologo", "/fo", res, "/I", str(source.parent)]
        for include in options.includes:
            command.extend(["/I", include])
        for define in options.defines:
            command.extend(["/D", define])
        command.append(str(source))
        subprocess.run(command, check=True)
        subprocess.run([cvtres, "/NOLOGO", "/MACHINE:ARM64", f"/OUT:{output}", res], check=True)
    with output.open("rb") as stream:
        header = stream.read(20)
    if len(header) != 20 or struct.unpack_from("<H", header)[0] != 0xAA64:
        output.unlink(missing_ok=True)
        raise RuntimeError("Resource compiler did not produce an ARM64 COFF object")


if __name__ == "__main__":
    try:
        compile_resource(parse_arguments(sys.argv[1:]))
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"ARM64 resource compilation failed: {error}", file=sys.stderr)
        sys.exit(1)
