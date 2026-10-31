# SPDX-FileCopyrightText: 2026 Dudiebug
# SPDX-License-Identifier: GPL-2.0-or-later

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "patch-kde-blueprints-arm64.py"
spec = spec_from_file_location("patch_kde_blueprints_arm64", SCRIPT)
module = module_from_spec(spec)
spec.loader.exec_module(module)


def _load_nsis_module():
    script = Path(__file__).resolve().parents[1] / "patch-nsis-and-blueprint.py"
    nsis_spec = spec_from_file_location("patch_nsis_and_blueprint", script)
    nsis_module = module_from_spec(nsis_spec)
    nsis_spec.loader.exec_module(nsis_module)
    return nsis_module

LIBJPEG = (
    "import info\n"
    "from Package.CMakePackageBase import CMakePackageBase\n"
    "from Utils import CraftHash\n\n"
    "class Package(CMakePackageBase):\n"
    "    def __init__(self, **kwargs):\n"
    "        super().__init__(**kwargs)\n"
    "        if self.subinfo.options.buildStatic:\n"
    "            self.subinfo.options.configure.args += [\"-DENABLE_SHARED=OFF\", \"-DENABLE_STATIC=ON\"]\n"
    "        else:\n"
    "            self.subinfo.options.configure.args += [\"-DENABLE_SHARED=ON\", \"-DENABLE_STATIC=OFF\"]\n"
)

PIXMAN = (
    "import info\n"
    "from CraftCore import CraftCore\n"
    "from Package.MesonPackageBase import MesonPackageBase\n\n"
    "class Package(MesonPackageBase):\n"
    "    def __init__(self, **kwargs):\n"
    "        super().__init__(**kwargs)\n"
    "        if CraftCore.compiler.isMacOS:\n"
    "            self.subinfo.options.configure.args += [\"-Da64-neon=disabled\"]\n"
)

LIBP11 = (
    "class PackageMake(MakeFilePackageBase):\n"
    "    def __init__(self, **kwargs):\n"
    "        super().__init__(**kwargs)\n"
    "        self.subinfo.options.make.args += f\"/f Makefile.mak OPENSSL_DIR=\" + str(CraftCore.standardDirs.craftRoot())\n"
    "        if CraftCore.compiler.architecture == CraftCompiler.Architecture.x86_64:\n"
    "             self.subinfo.options.make.args += f\" BUILD_FOR=WIN64\"\n"
    "\n"
    "    def install(self):\n"
    "        pass\n"
)


LIBP11_RULES = (
    "!IF \"$(BUILD_FOR)\" == \"WIN64\"\n"
    "MACHINE = /MACHINE:X64\n"
    "!ELSE\n"
    "MACHINE = /MACHINE:X86\n"
    "!ENDIF\n"
    "LINKFLAGS = /NOLOGO /INCREMENTAL:NO $(MACHINE) /MANIFEST:NO\n"
)


NEXTCLOUD_CLIENT = (
    "# SPDX-License-Identifier: BSD-2-Clause\n"
    "# SPDX-FileCopyrightText: 2021 Nextcloud GmbH and Nextcloud contributors\n"
    "\n"
    "import info\n"
    "from Package.CMakePackageBase import *\n"
    "\n"
    "class Package(CMakePackageBase):\n"
    "    def createPackage(self):\n"
    "        self.blacklist_file.append(os.path.join(self.packageDir(), 'blacklist.txt'))\n"
    "        self.defines[\"appname\"] = \"nextcloud\"\n"
    "        self.defines[\"company\"] = \"Nextcloud GmbH\"\n"
    "        self.applicationExecutable = \"nextcloud\"\n"
    "\n"
    "        self.ignoredPackages += [\"binary/mysql\"]\n"
    "        return super().createPackage()\n"
)


QTTOOLS = (
    "import info\n"
    "from Blueprints.CraftPackageObject import CraftPackageObject\n"
    "from CraftCore import CraftCore\n\n\n"
    "class subinfo(info.infoclass):\n"
    "    def setDependencies(self):\n"
    "        self.runtimeDependencies[\"virtual/base\"] = None\n"
    "        self.runtimeDependencies[\"libs/qt6/qtbase\"] = None\n"
    "        self.runtimeDependencies[\"libs/qt6/qtdeclarative\"] = None\n"
    "        self.runtimeDependencies[\"libs/llvm\"] = None\n"
    "        self.patchLevel[\"6.4.0\"] = 1\n\n\n"
    "class Package(CraftPackageObject.get(\"libs/qt6\").pattern):\n"
    "    def __init__(self, **kwargs):\n"
    "        super().__init__(**kwargs)\n"
    "        if CraftCore.compiler.isMSVC() and self.buildType() == \"Debug\":\n"
    "            self.subinfo.options.configure.args += [\"-DQT_FEATURE_clangcpp=OFF\", \"-DQT_FEATURE_clang=OFF\"]\n"
)


class KdeBlueprintPatchTests(unittest.TestCase):
    @staticmethod
    def _write(path, source, newline):
        path.write_bytes(source.replace("\n", newline).encode("utf-8"))

    def test_libjpeg_crlf_checkout_patches_and_preserves_crlf(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "libjpeg-turbo.py"
            self._write(path, LIBJPEG, "\r\n")
            module.patch_libjpeg(path)
            module.patch_libjpeg(path)
            data = path.read_bytes()
            self.assertIn(b"-DWITH_SIMD=OFF", data)
            self.assertIn(b"from CraftCompiler import CraftCompiler\r\n", data)
            self.assertNotIn(b"\n", data.replace(b"\r\n", b""))

    def test_pixman_crlf_checkout_patches_and_preserves_crlf(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pixman.py"
            self._write(path, PIXMAN, "\r\n")
            module.patch_pixman(path)
            module.patch_pixman(path)
            data = path.read_bytes()
            self.assertIn(b"-Dmmx=disabled", data)
            self.assertIn(b"-Dsse2=disabled", data)
            self.assertIn(b"-Dssse3=disabled", data)
            self.assertNotIn(b"\n", data.replace(b"\r\n", b""))

    def test_lf_checkout_remains_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            libjpeg = Path(directory) / "libjpeg-turbo.py"
            pixman = Path(directory) / "pixman.py"
            self._write(libjpeg, LIBJPEG, "\n")
            self._write(pixman, PIXMAN, "\n")
            module.patch_libjpeg(libjpeg)
            module.patch_pixman(pixman)
            self.assertNotIn(b"\r\n", libjpeg.read_bytes())
            self.assertNotIn(b"\r\n", pixman.read_bytes())

    @staticmethod
    def _load_libp11_package(text, architecture, base_make_result=True):
        """Execute a patched libp11 blueprint against minimal Craft stubs."""
        import os
        import types

        arch = types.SimpleNamespace(x86_64="x86_64", arm64="arm64")
        errors = []
        compiler = types.SimpleNamespace(architecture=architecture)
        craft_core = types.SimpleNamespace(
            compiler=compiler,
            log=types.SimpleNamespace(error=errors.append),
            standardDirs=types.SimpleNamespace(craftRoot=lambda: "C:/craft"),
        )

        class MakeFilePackageBase:
            def __init__(self, **kwargs):
                self.subinfo = types.SimpleNamespace(
                    options=types.SimpleNamespace(make=types.SimpleNamespace(args=""))
                )

            def make(self):
                return base_make_result

        namespace = {
            "os": os,
            "CraftCore": craft_core,
            "CraftCompiler": types.SimpleNamespace(Architecture=arch),
            "MakeFilePackageBase": MakeFilePackageBase,
        }
        exec(text.replace("\r\n", "\n"), namespace)
        return namespace["PackageMake"], errors

    def test_libp11_links_arm64_instead_of_x86(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "libp11.py"
            self._write(path, LIBP11, "\r\n")
            module.patch_libp11(path)
            module.patch_libp11(path)
            text = path.read_bytes().decode("utf-8")
            self.assertEqual(text.count(module.LIBP11_MARKER), 1)
            self.assertNotIn("MACHINE=/MACHINE:ARM64", text)
            self.assertIn("BUILD_FOR=WIN64", text)
            self.assertNotIn("\n", text.replace("\r\n", ""))
            compile(text.replace("\r\n", "\n"), str(path), "exec")

    def test_libp11_upgrades_legacy_command_line_machine_patch(self):
        legacy = LIBP11.replace(
            "             self.subinfo.options.make.args += f\" BUILD_FOR=WIN64\"\n",
            "             self.subinfo.options.make.args += f\" BUILD_FOR=WIN64\"\n"
            + module.LIBP11_LEGACY_PATCH,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "libp11.py"
            self._write(path, legacy, "\r\n")
            module.patch_libp11(path)
            text = path.read_bytes().decode("utf-8")
            self.assertNotIn("MACHINE=/MACHINE:ARM64", text)
            self.assertEqual(text.count(module.LIBP11_MARKER), 1)

    def test_libp11_arm64_make_rewrites_rules_used_by_recursive_nmake(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "libp11.py"
            self._write(path, LIBP11, "\n")
            module.patch_libp11(path)
            source = Path(directory) / "src"
            source.mkdir()
            rules = source / "make.rules.mak"
            rules.write_text(LIBP11_RULES)
            package, errors = self._load_libp11_package(path.read_text(), "arm64")
            instance = package()
            instance.sourceDir = lambda: str(source)
            self.assertTrue(instance.make())
            self.assertTrue(instance.make())
            content = rules.read_text()
            self.assertIn("MACHINE = /MACHINE:X64", content)
            self.assertIn("MACHINE = /MACHINE:ARM64", content)
            self.assertNotIn("/MACHINE:X86", content)
            self.assertEqual(errors, [])

    def test_libp11_make_leaves_x64_rules_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "libp11.py"
            self._write(path, LIBP11, "\n")
            module.patch_libp11(path)
            rules = Path(directory) / "make.rules.mak"
            rules.write_text(LIBP11_RULES)
            package, _ = self._load_libp11_package(path.read_text(), "x86_64")
            instance = package()
            instance.sourceDir = lambda: directory
            self.assertTrue(instance.make())
            self.assertEqual(rules.read_text(), LIBP11_RULES)
            self.assertIn("BUILD_FOR=WIN64", instance.subinfo.options.make.args)

    def test_libp11_arm64_make_fails_on_unexpected_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "libp11.py"
            self._write(path, LIBP11, "\n")
            module.patch_libp11(path)
            (Path(directory) / "make.rules.mak").write_text("LINKFLAGS = /NOLOGO\n")
            package, errors = self._load_libp11_package(path.read_text(), "arm64")
            instance = package()
            instance.sourceDir = lambda: directory
            self.assertFalse(instance.make())
            self.assertEqual(len(errors), 1)

    def test_libp11_unexpected_upstream_layout_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "libp11.py"
            self._write(path, "class PackageMake:\n    pass\n", "\n")
            with self.assertRaises(RuntimeError):
                module.patch_libp11(path)

    def test_qttools_drops_llvm_only_for_windows_arm64(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qttools.py"
            self._write(path, QTTOOLS, "\r\n")
            module.patch_qttools(path)
            module.patch_qttools(path)
            text = path.read_bytes().decode("utf-8")
            self.assertNotIn("\n", text.replace("\r\n", ""))
            text = text.replace("\r\n", "\n")
            compile(text, str(path), "exec")
            self.assertEqual(text.count('self.runtimeDependencies["libs/llvm"] = None'), 1)
            self.assertIn(
                "        if not (CraftCore.compiler.isWindows and CraftCore.compiler.architecture == CraftCompiler.Architecture.arm64):\n"
                '            self.runtimeDependencies["libs/llvm"] = None\n',
                text,
            )
            self.assertEqual(text.count('"-DFEATURE_clang=OFF", "-DFEATURE_clangcpp=OFF"'), 1)

    def test_qttools_unexpected_upstream_layout_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qttools.py"
            self._write(path, QTTOOLS.replace('libs/llvm', 'libs/clang'), "\n")
            with self.assertRaises(RuntimeError):
                module.patch_qttools(path)


    @staticmethod
    def _run_create_package(text, directory):
        """Run createPackage() with Craft stubs; the star import provides no os."""

        class CMakePackageBase:
            def createPackage(self):
                return True

        source = text.replace("import info\n", "").replace("from Package.CMakePackageBase import *\n", "")
        scope = {"__name__": "nextcloud_client_blueprint", "CMakePackageBase": CMakePackageBase}
        exec(source, scope)
        package = scope["Package"]()
        package.blacklist_file = []
        package.defines = {}
        package.ignoredPackages = []
        package.packageDir = lambda: directory
        package.buildDir = lambda: directory
        package.sourceDir = lambda: directory
        return package, package.createPackage()

    def test_nextcloud_client_create_package_has_os_after_both_patches(self):
        nsis = _load_nsis_module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nextcloud-client.py"
            self._write(path, NEXTCLOUD_CLIENT, "\n")
            with self.assertRaises(NameError):
                self._run_create_package(path.read_text(), directory)
            nsis.patch_blueprint(str(path))
            module.patch_nextcloud_client_imports(path)
            module.patch_nextcloud_client_imports(path)
            text = path.read_text()
            self.assertEqual(text.count("import os\n"), 1)
            Path(directory, "VERSION.cmake").write_text(
                "set( MIRALL_VERSION_MAJOR 34 )\nset( MIRALL_VERSION_MINOR 0 )\nset( MIRALL_VERSION_PATCH 5 )\n"
            )
            package, result = self._run_create_package(text, directory)
            self.assertTrue(result)
            self.assertEqual(package.defines["executable"], "bin\\nextcloud.exe")
            self.assertEqual(package.defines["version"], "34.0.5")

    def test_nextcloud_client_import_patch_reaches_previously_patched_crlf_blueprints(self):
        nsis = _load_nsis_module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nextcloud-client.py"
            self._write(path, NEXTCLOUD_CLIENT, "\n")
            nsis.patch_blueprint(str(path))
            # patch_blueprint() writes in text mode, so the file already has CRLF
            # on Windows and LF elsewhere; normalise before converting to CRLF.
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
            module.patch_nextcloud_client_imports(path)
            data = path.read_bytes()
            self.assertIn(b"import info\r\nimport os\r\n", data)
            self.assertNotIn(b"\n", data.replace(b"\r\n", b""))

    def test_nextcloud_client_unexpected_imports_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nextcloud-client.py"
            self._write(path, NEXTCLOUD_CLIENT.replace("import info\n", "from info import infoclass\n"), "\n")
            with self.assertRaises(RuntimeError):
                module.patch_nextcloud_client_imports(path)

if __name__ == "__main__":
    unittest.main()
