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
from arm64_verify import microsoft_runtime_candidates, verify_directory, verify_pe


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

    def test_gettext_documentation_example_is_not_an_application_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('nextcloud.exe', 'Qt6Core.dll'):
                (root / name).write_bytes(pe())
            examples = root / 'data/doc/gettext/examples/build-aux'
            examples.mkdir(parents=True)
            (examples / 'csharpexec-test.exe').write_bytes(pe(0x14c))
            verify_directory(root)

    def test_packaging_excluded_build_utility_is_not_an_application_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('nextcloud.exe', 'Qt6Core.dll'):
                (root / name).write_bytes(pe())
            (root / 'build-utility.exe').write_bytes(pe(0x14c))
            verify_directory(root)

    def test_packaged_application_executables_remain_checked(self):
        for name in ('nextcloudcmd.exe', 'QtWebEngineProcess.exe'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for required in ('nextcloud.exe', 'Qt6Core.dll'):
                    (root / required).write_bytes(pe())
                (root / name).write_bytes(pe(0x14c))
                with self.assertRaisesRegex(ValueError, name):
                    verify_directory(root)

    def test_microsoft_companion_runtime_must_match_arm64_distribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'bin'
            root.mkdir()
            for name in ('nextcloud.exe', 'Qt6Core.dll'):
                (root / name).write_bytes(pe())
            companion = pe(0x8664)
            (root / 'vcruntime140_1.dll').write_bytes(companion)
            official = Path(tmp) / 'arm64/Microsoft.VC143.CRT/vcruntime140_1.dll'
            official.parent.mkdir(parents=True)
            official.write_bytes(companion)
            report = Path(tmp) / 'binary-validation.json'
            with patch('arm64_verify.microsoft_runtime_candidates', return_value=[official], create=True):
                verify_directory(root, report)
                proof = next(entry for entry in json.loads(report.read_text()) if entry['path'] == 'vcruntime140_1.dll')
                self.assertEqual(proof['machine'], '0x8664')
                self.assertEqual(proof['microsoft_arm64_redist_source'], str(official))
                (root / 'vcruntime140_1.dll').write_bytes(companion + b'changed')
                with self.assertRaisesRegex(ValueError, 'vcruntime140_1.dll'):
                    verify_directory(root)

    def test_companion_runtime_requires_an_official_source_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('nextcloud.exe', 'Qt6Core.dll'):
                (root / name).write_bytes(pe())
            (root / 'vcruntime140_1.dll').write_bytes(pe(0x8664))
            with patch('arm64_verify.microsoft_runtime_candidates', return_value=[], create=True):
                with self.assertRaisesRegex(ValueError, 'vcruntime140_1.dll'):
                    verify_directory(root)

    def test_companion_exception_does_not_apply_to_nested_plugins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'bin'
            root.mkdir()
            for name in ('nextcloud.exe', 'Qt6Core.dll'):
                (root / name).write_bytes(pe())
            plugin = root / 'plugins/vcruntime140_1.dll'
            plugin.parent.mkdir()
            plugin.write_bytes(pe(0x8664))
            with patch('arm64_verify.microsoft_runtime_candidates', return_value=[plugin], create=True):
                with self.assertRaisesRegex(ValueError, 'vcruntime140_1.dll'):
                    verify_directory(root)

    def test_companion_discovery_uses_only_arm64_redist_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / 'Microsoft Visual Studio/18/Enterprise/VC/Redist/MSVC/14.44.35112'
            official = base / 'arm64/Microsoft.VC143.CRT/vcruntime140_1.dll'
            wrong = base / 'x64/Microsoft.VC143.CRT/vcruntime140_1.dll'
            for path in (official, wrong):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(pe(0x8664))
            with patch.dict('os.environ', {'ProgramFiles': tmp, 'ProgramFiles(x86)': tmp}):
                self.assertEqual(microsoft_runtime_candidates(), [official])


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
