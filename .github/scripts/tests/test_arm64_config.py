# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: GPL-2.0-or-later
import configparser
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from arm64_config import COMPILER_ABI, MSVC_TOOLSET, QT_COMPILER, TARGET, configure

SOURCE = """[General]
CraftUrl = https://github.com/nextcloud/craft.git
CraftRevision = 6d812696a6aa025dc3c545d8feb954f23be9446e
Branch = stable-34.0-qt-6.10.2
[Variables]
UseCache = True
[GeneralSettings]
Packager/UseCache = ${Variables:UseCache}
[BlueprintSettings]
libs/qt6.version = 6.10.2
libs/openssl.version = 3.6.3
craft/craft-blueprints-kde.revision = stable-34.0
[windows-msvc2022_64-cl]
General/ABI = windows-msvc2022_64-cl
Paths/Python = C:\\Python312-x64
[Env]
SIGN_PACKAGE = False
"""
REVISION = "a" * 40
PYTHON_DIRECTORY = r"C:\hostedtoolcache\windows\Python\3.12.10\arm64"


def parse(text):
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read_string(text)
    return config


class Arm64ConfigTests(unittest.TestCase):
    def setUp(self):
        self.generated = configure(SOURCE, REVISION, PYTHON_DIRECTORY)
        self.config = parse(self.generated)

    def test_missing_arm_target_is_added(self):
        self.assertNotIn(TARGET, parse(SOURCE))
        self.assertEqual(self.config[TARGET]["General/ABI"], COMPILER_ABI)
        self.assertEqual(self.config[TARGET]["QtSDK/Compiler"], QT_COMPILER)

    def test_migrated_runner_uses_vs2026_compiler(self):
        self.assertEqual(COMPILER_ABI, "windows-msvc2026_arm64-cl")
        self.assertEqual(QT_COMPILER, "msvc2026_arm64")
        self.assertNotEqual(self.config[TARGET]["General/ABI"], TARGET)

    def test_vs2026_host_uses_installed_14_44_arm64_toolset(self):
        self.assertEqual(MSVC_TOOLSET, "14.44")
        self.assertEqual(self.config[TARGET]["General/MSVCToolset"], MSVC_TOOLSET)

    def test_uses_active_python_not_x64_path(self):
        self.assertEqual(self.config[TARGET]["Paths/Python"], PYTHON_DIRECTORY)
        self.assertEqual(self.config["windows-msvc2022_64-cl"]["Paths/Python"], r"C:\Python312-x64")

    def test_unavailable_binary_cache_disabled_only_for_arm(self):
        self.assertEqual(self.config[TARGET]["Packager/UseCache"], "False")
        self.assertEqual(self.config["GeneralSettings"]["Packager/UseCache"], "${Variables:UseCache}")

    def test_local_committed_patches_remain_pinned(self):
        self.assertEqual(self.config["General"]["CraftRevision"], REVISION)
        self.assertEqual(self.config["BlueprintSettings"]["libs/openssl.version"], "3.6.3")
        self.assertEqual(self.config["BlueprintSettings"]["libs/qt6.version"], "6.10.2")

    def test_tests_enabled_and_webengine_disabled(self):
        self.assertEqual(self.config["BlueprintSettings"]["nextcloud-client.buildTests"], "True")
        self.assertEqual(self.config["BlueprintSettings"]["nextcloud-client.buildWithWebEngine"], "False")

    def test_pip_uses_legacy_certs_without_overwriting_upstream_env(self):
        self.assertEqual(self.config["Env"]["PIP_USE_DEPRECATED"], "legacy-certs")
        self.assertEqual(self.config["Env"]["SIGN_PACKAGE"], "False")

    def test_second_configuration_is_idempotent(self):
        self.assertEqual(configure(self.generated, REVISION, PYTHON_DIRECTORY), self.generated)

    def test_line_endings(self):
        self.assertEqual(configure(SOURCE.replace("\n", "\r\n"), REVISION, PYTHON_DIRECTORY), self.generated)

    def test_invalid_revision_rejected(self):
        for revision in ("master", "abcd", "z" * 40, "a" * 40 + "\n"):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                configure(SOURCE, revision, PYTHON_DIRECTORY)

    def test_missing_upstream_pin_rejected(self):
        with self.assertRaises(ValueError):
            configure(SOURCE.replace("CraftRevision = 6d812696a6aa025dc3c545d8feb954f23be9446e\n", ""), REVISION, PYTHON_DIRECTORY)

    def test_invalid_python_directory_rejected(self):
        for directory in ("", "C:\\Python\nOther = value"):
            with self.assertRaises(ValueError):
                configure(SOURCE, REVISION, directory)


if __name__ == "__main__":
    unittest.main()
