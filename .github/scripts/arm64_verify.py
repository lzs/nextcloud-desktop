# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reject malformed or non-ARM64 application binaries before packaging."""
from pathlib import Path
import hashlib
import json
import os
import struct
import sys


def pe_machine(data):
    if len(data) < 64 or data[:2] != b'MZ':
        raise ValueError('Invalid DOS header')
    offset = struct.unpack_from('<I', data, 0x3c)[0]
    if offset < 64 or offset + 24 > len(data) or data[offset:offset + 4] != b'PE\0\0':
        raise ValueError('Invalid PE header')
    machine = struct.unpack_from('<H', data, offset + 4)[0]
    return machine


def verify_pe(data):
    machine = pe_machine(data)
    if machine != 0xAA64:
        raise ValueError(f'Expected ARM64 (0xAA64), found 0x{machine:04X}')


def microsoft_runtime_candidates():
    # Microsoft includes an x64 companion vcruntime140_1.dll in its ARM64 CRT
    # distribution. Accept only an exact copy from an installed ARM64 redist.
    candidates = set()
    for variable in ('ProgramFiles', 'ProgramFiles(x86)'):
        value = os.environ.get(variable)
        if not value:
            continue
        base = Path(value) / 'Microsoft Visual Studio'
        candidates.update(base.glob('*/VC/Redist/MSVC/*/arm64/Microsoft.VC*.CRT/vcruntime140_1.dll'))
        candidates.update(base.glob('*/*/VC/Redist/MSVC/*/arm64/Microsoft.VC*.CRT/vcruntime140_1.dll'))
    return sorted(path for path in candidates if path.is_file())


def verify_directory(directory, report_path=None):
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
    report = []
    for path in files:
        try:
            data = path.read_bytes()
            machine = pe_machine(data)
            entry = {'path': path.relative_to(directory).as_posix(),
                     'machine': f'0x{machine:04X}', 'sha256': hashlib.sha256(data).hexdigest()}
            if machine == 0x8664 and path.parent == directory and path.name.casefold() == 'vcruntime140_1.dll':
                sources = [source for source in microsoft_runtime_candidates() if source.read_bytes() == data]
                if not sources:
                    raise ValueError('Microsoft companion runtime does not match an installed ARM64 redistributable')
                entry['microsoft_arm64_redist_source'] = str(sources[0])
                print(f'{path.name}: byte-identical to Microsoft ARM64 redistributable companion {sources[0]}')
            else:
                verify_pe(data)
            report.append(entry)
        except ValueError as error:
            raise ValueError(f'{path}: {error}') from error
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'Validated {len(files)} application binaries; non-ARM64 exceptions require a matching Microsoft ARM64 redist source.')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: arm64_verify.py <installed-bin-directory>')
    report_path = Path(__file__).resolve().parents[2] / 'release-output/binary-validation.json'
    verify_directory(Path(sys.argv[1]), report_path)
