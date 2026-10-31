# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: GPL-2.0-or-later
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import arm64_prepare
from arm64_verify import verify_directory, verify_pe


def pe(machine=0xAA64):
    data = bytearray(256)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 128)
    data[128:132] = b'PE\0\0'
    struct.pack_into('<H', data, 132, machine)
    return data


class BinaryTests(unittest.TestCase):
    def test_arm64_accepted(self):
        verify_pe(pe())

    def test_other_architectures_rejected(self):
        for machine in (0x8664, 0x14c, 0xA641):
            with self.subTest(machine=machine), self.assertRaises(ValueError):
                verify_pe(pe(machine))

    def test_malformed_headers_rejected(self):
        invalid_offset = pe()
        struct.pack_into('<I', invalid_offset, 0x3c, 0xFFFFFFFF)
        invalid_signature = pe()
        invalid_signature[128] = 0
        for data in (b'', b'MZ', bytes(256), invalid_offset, invalid_signature):
            with self.assertRaises(ValueError):
                verify_pe(data)

    def test_nested_plugin_architecture_is_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('nextcloud.exe', 'Qt6Core.dll'):
                (root / name).write_bytes(pe())
            verify_directory(root)
            (root / 'plugins').mkdir()
            (root / 'plugins/platform.dll').write_bytes(pe(0x8664))
            with self.assertRaisesRegex(ValueError, 'platform.dll'):
                verify_directory(root)

    def test_required_binaries_cannot_be_missing(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            verify_directory(Path(tmp))


class SourceTests(unittest.TestCase):
    def test_build_metadata_allowed_but_source_changes_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            (root / 'source.cpp').write_text('original\n')
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(root), '-c', 'user.name=Test',
                            '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture'], check=True)
            revision = arm64_prepare.git(root, 'rev-parse', 'HEAD')
            (root / '.github').mkdir()
            (root / '.github/build.yml').write_text('metadata\n')
            subprocess.run(['git', '-C', str(root), 'add', '.github'], check=True)
            arm64_prepare.verify_source(root, revision)
            (root / 'source.cpp').write_text('modified\n')
            with self.assertRaises(subprocess.CalledProcessError):
                arm64_prepare.verify_source(root, revision)

    def test_pins_reject_a_third_party_download_origin(self):
        pins = arm64_prepare.load_pins()
        pins['craft']['url'] = 'https://example.invalid/craft.git'
        with patch.object(Path, 'read_text', return_value=json.dumps(pins)):
            with self.assertRaises(ValueError):
                arm64_prepare.load_pins()

    def test_config_freezes_blueprint_revisions_and_disables_binary_cache(self):
        pins = arm64_prepare.load_pins()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'generated.ini'
            revisions = {name: pin['revision'] for name, pin in pins.items() if name.startswith('craft-blueprints')}
            arm64_prepare.write_config(target, pins['craft']['revision'], revisions)
            text = target.read_text()
            for revision in revisions.values():
                self.assertIn(revision, text)
            self.assertIn('Packager/UseCache = False', text)


if __name__ == '__main__':
    unittest.main()
