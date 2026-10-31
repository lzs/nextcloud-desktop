# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch as mock_patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from arm64_windres import Options, compile_resource, parse_arguments, windows_path
from patch_arm64_resources import apply, patch, patch_gettext


class ResourceTests(unittest.TestCase):
    def test_actual_libunistring_flags(self):
        args = ['--target=pe-x86-64', '--preprocessor=cl', '--preprocessor-arg=-nologo',
                '--preprocessor-arg=-EP', '--preprocessor-arg=-DRC_INVOKED',
                '--preprocessor-arg=-DWINAPI_FAMILY=WINAPI_FAMILY_DESKTOP_APP',
                '-O', 'COFF', r'-DPACKAGE_VERSION_STRING=\"1.4.1\"',
                '-DPACKAGE_VERSION_MAJOR=1', '-i', '/c/source/libunistring.rc',
                '--output-format=coff', '-o', '.libs/libunistring.res.obj']
        options = parse_arguments(args)
        self.assertEqual(options.source, 'c:/source/libunistring.rc')
        self.assertIn('PACKAGE_VERSION_STRING="1.4.1"', options.defines)
        self.assertIn('RC_INVOKED', options.defines)
        self.assertEqual(options.output, '.libs/libunistring.res.obj')

    def test_actual_gettext_flags(self):
        args = ['--target=pe-x86-64', '--preprocessor=cl', '--preprocessor-arg=-nologo',
                '--preprocessor-arg=-EP', '--preprocessor-arg=-DRC_INVOKED',
                '--preprocessor-arg=-DWINAPI_FAMILY=WINAPI_FAMILY_DESKTOP_APP',
                '-O', 'COFF', r'-DPACKAGE_VERSION_STRING=\"0.22.3\"',
                '-DPACKAGE_VERSION_MAJOR=0', '-DPACKAGE_VERSION_MINOR=22',
                '-DPACKAGE_VERSION_SUBMINOR=3', '-i', './libintl.rc',
                '--output-format=coff', '-o', '.libs/libintl.res.obj']
        options = parse_arguments(args)
        self.assertEqual(options.source, './libintl.rc')
        self.assertIn('PACKAGE_VERSION_STRING="0.22.3"', options.defines)
        self.assertIn('RC_INVOKED', options.defines)
        self.assertEqual(options.output, '.libs/libintl.res.obj')

    def test_short_and_long_forms(self):
        options = parse_arguments(['--input=a.rc', '-ob.obj', '--define=V=1', '-I', '/d/inc'])
        self.assertEqual((options.source, options.output, options.includes), ('a.rc', 'b.obj', ['d:/inc']))

    def test_unsupported_flags_fail(self):
        for flags in (['--something=ignored'], ['-O', 'res'], ['--target=pe-i386'],
                      ['--preprocessor=gcc'], ['--preprocessor-arg=-strange'], ['-i']):
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                parse_arguments(flags)

    def test_stdin_rejected(self):
        with self.assertRaises(ValueError):
            parse_arguments(['-i', '-', '-o', 'a.obj'])

    def test_windows_paths(self):
        self.assertEqual(windows_path('/c/a b/test.rc'), 'c:/a b/test.rc')
        self.assertEqual(windows_path('C:/native/test.rc'), 'C:/native/test.rc')

    def test_patch_is_idempotent_and_retains_metadata(self):
        source = 'import info\n# target metadata preserved\nclass Package(AutoToolsPackageBase):\n    pass\n'
        result = patch(source)
        self.assertEqual(patch(result), result)
        self.assertIn('# target metadata preserved', result)
        self.assertIn('self.subinfo.options.make', result)
        self.assertIn('WINDRES={compiler}', result)

    def test_gettext_patch_is_idempotent_and_preserves_recipe(self):
        source = (
            'import info\nfrom CraftCore import CraftCore\n'
            'class Package(AutoToolsPackageBase):\n'
            '    def __init__(self, **kwargs):\n'
            '        super().__init__(**kwargs)\n'
            '        self.shell.useMSVCCompatEnv = True\n'
            '        self.subinfo.options.configure.args += ["--enable-nls"]\n'
            '    def configure(self):\n'
            '        return super().configure()\n'
        )
        result = patch_gettext(source)
        self.assertEqual(patch_gettext(result), result)
        self.assertIn('--enable-nls', result)
        self.assertIn('def configure(self):', result)
        self.assertIn('self.subinfo.options.make', result)
        self.assertIn('WINDRES={compiler}', result)

    def test_unexpected_blueprint_rejected(self):
        with self.assertRaises(ValueError):
            patch('class Package(CMakePackageBase):\n    pass\n')

    def test_unexpected_gettext_blueprint_rejected(self):
        with self.assertRaises(ValueError):
            patch_gettext('class Package(AutoToolsPackageBase):\n    def __init__(self):\n        pass\n')

    def test_helper_is_kept_outside_blueprint_recipe_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            craft = Path(directory) / "craft-clone"
            libunistring_dir = craft / "blueprints/libs/libunistring"
            libunistring_dir.mkdir(parents=True)
            libunistring = libunistring_dir / "libunistring.py"
            libunistring.write_text(
                "import info\nclass Package(AutoToolsPackageBase):\n    pass\n",
                encoding="utf-8",
            )
            gettext_dir = craft / "blueprints/libs/gettext"
            gettext_dir.mkdir(parents=True)
            gettext = gettext_dir / "gettext.py"
            gettext.write_text(
                "from CraftCore import CraftCore\n"
                "class Package(AutoToolsPackageBase):\n"
                "    def __init__(self, **kwargs):\n"
                "        super().__init__(**kwargs)\n"
                "        self.shell.useMSVCCompatEnv = True\n"
                "        self.subinfo.options.configure.args += ['--enable-nls']\n"
                "    def configure(self):\n"
                "        return super().configure()\n",
                encoding="utf-8",
            )
            helper = Path(directory) / "arm64_windres.py"
            helper.write_text("print('helper')\n", encoding="utf-8")

            apply(craft, helper)

            self.assertTrue((craft / "bin/arm64_windres.py").is_file())
            self.assertFalse((libunistring_dir / "arm64_windres.py").exists())
            self.assertFalse((gettext_dir / "arm64_windres.py").exists())
            patched = libunistring.read_text(encoding="utf-8")
            self.assertIn('CraftCore.standardDirs.craftRoot()', patched)
            self.assertIn('"craft" / "bin" / "arm64_windres.py"', patched)
            gettext_patched = gettext.read_text(encoding="utf-8")
            self.assertIn("--enable-nls", gettext_patched)
            self.assertIn("def configure(self):", gettext_patched)
            self.assertIn('WINDRES={compiler}', gettext_patched)

    def test_native_sdk_command_and_machine_check(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'a.rc'
            output = Path(directory) / 'a.obj'
            source.write_text('1 RCDATA { 1 }')
            commands = []
            def run(command, check):
                commands.append(command)
                if '/MACHINE:ARM64' in command:
                    output.write_bytes(struct.pack('<H', 0xAA64) + bytes(18))
            with mock_patch('arm64_windres.shutil.which', side_effect=lambda name: name), \
                 mock_patch('arm64_windres.subprocess.run', side_effect=run):
                compile_resource(Options(str(source), str(output)))
            self.assertEqual(commands[0][-1], str(source.resolve(strict=True)))
            self.assertNotIn('-', commands[0])
            self.assertIn('/MACHINE:ARM64', commands[1])

    def test_non_arm_object_rejected_and_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'a.rc'
            output = Path(directory) / 'a.obj'
            source.write_text('1 RCDATA { 1 }')
            def run(command, check):
                if '/MACHINE:ARM64' in command:
                    output.write_bytes(struct.pack('<H', 0x8664) + bytes(18))
            with mock_patch('arm64_windres.shutil.which', side_effect=lambda name: name), \
                 mock_patch('arm64_windres.subprocess.run', side_effect=run), self.assertRaises(RuntimeError):
                compile_resource(Options(str(source), str(output)))
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
