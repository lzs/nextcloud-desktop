# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reject malformed or non-ARM64 application binaries before packaging."""
from pathlib import Path
import struct
import sys


def verify_pe(data):
    if len(data) < 64 or data[:2] != b'MZ':
        raise ValueError('Invalid DOS header')
    offset = struct.unpack_from('<I', data, 0x3c)[0]
    if offset < 64 or offset + 24 > len(data) or data[offset:offset + 4] != b'PE\0\0':
        raise ValueError('Invalid PE header')
    machine = struct.unpack_from('<H', data, offset + 4)[0]
    if machine != 0xAA64:
        raise ValueError(f'Expected ARM64 (0xAA64), found 0x{machine:04X}')


def verify_directory(directory):
    for name in ('nextcloud.exe', 'Qt6Core.dll'):
        if not (directory / name).is_file():
            raise ValueError(f'Missing required binary: {name}')
    files = []
    for path in sorted(directory.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in ('.exe', '.dll'):
            continue
        relative = path.relative_to(directory)
        if tuple(part.casefold() for part in relative.parts[:2]) == ('data', 'doc'):
            continue
        # Match the executable selection in the Nextcloud Craft blacklist:
        # bin/(?!(nextcloud|nextcloudcmd|QtWebEngineProcess)).*\.exe
        if path.suffix.lower() == '.exe' and not relative.as_posix().casefold().startswith(('nextcloud', 'qtwebengineprocess')):
            continue
        files.append(path)
    for path in files:
        try:
            verify_pe(path.read_bytes())
        except ValueError as error:
            raise ValueError(f'{path}: {error}') from error
    print(f'Validated {len(files)} ARM64 executables and DLLs in {directory}')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: arm64_verify.py <installed-bin-directory>')
    verify_directory(Path(sys.argv[1]))
