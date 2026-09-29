import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from check_macos_build_python import check_python
from verify_macos_bundle import inspect_bundle, load_commands, version_tuple


def commands(version="15.0", dependencies=(), rpaths=()):
    blocks = ["cmd LC_BUILD_VERSION\n platform 1\n minos " + version]
    blocks += ["cmd LC_RPATH\n path {} (offset 12)".format(p) for p in rpaths]
    blocks += ["cmd LC_LOAD_DYLIB\n name {} (offset 24)\n current version 999.0.0".format(p)
               for p in dependencies]
    return "\n".join("Load command {}\n {}".format(i, b) for i, b in enumerate(blocks))


class BundleCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = Path(self.temp.name) / "Example.app"
        (self.app / "Contents/MacOS").mkdir(parents=True)
        self.info = {"LSMinimumSystemVersion": "15.0", "CFBundleExecutable": "example"}
        self.write_info()
        self.outputs = {}
        self.add_binary("Contents/MacOS/example")

    def write_info(self):
        (self.app / "Contents/Info.plist").write_bytes(plistlib.dumps(self.info))

    def add_binary(self, relative, text=None, arch="arm64"):
        path = self.app / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        self.outputs[str(path.resolve())] = (arch, commands() if text is None else text)

    def run_tool(self, args, **_kwargs):
        path = str(Path(args[-1]).resolve())
        if args[0] == "file":
            value = "Mach-O" if path in self.outputs else "data"
        elif args[0] == "lipo":
            value = self.outputs[path][0]
        else:
            self.assertEqual(args[:4], ["otool", "-arch", "arm64", "-l"])
            value = self.outputs[path][1]
        return SimpleNamespace(stdout=value)

    def inspect(self):
        return inspect_bundle(self.app, run=self.run_tool)

    def test_numeric_version_comparison(self):
        self.assertLess(version_tuple("15.5"), version_tuple("15.10"))
        self.assertEqual(version_tuple("15.5"), version_tuple("15.5.0"))
        with self.assertRaises(ValueError):
            version_tuple("15.bad")

    def test_valid_bundle_and_system_dependency(self):
        self.add_binary("Contents/MacOS/example", commands(dependencies=["/usr/lib/libSystem.B.dylib"]))
        self.assertEqual(self.inspect(), [])

    def test_universal_library_uses_only_arm64_load_commands(self):
        self.add_binary("Contents/Frameworks/universal.dylib", arch="x86_64 arm64")
        self.assertEqual(self.inspect(), [])

    def test_python_framework_dependency_is_bundled(self):
        self.add_binary("Contents/MacOS/example", commands(
            dependencies=["@rpath/Python.framework/Versions/3.12/Python"],
            rpaths=["@executable_path/../Frameworks"]))
        self.add_binary("Contents/Frameworks/Python.framework/Versions/3.12/Python")
        self.assertEqual(self.inspect(), [])

    def test_external_python_framework_rejected(self):
        self.add_binary("Contents/MacOS/example", commands(dependencies=[
            "/Library/Frameworks/Python.framework/Versions/3.12/Python"]))
        self.assertTrue(any("external dependency" in e for e in self.inspect()))

    def test_rejects_newer_binary_and_external_homebrew_library(self):
        self.add_binary("Contents/MacOS/example", commands("26.0", ["/opt/homebrew/lib/a.dylib"]))
        errors = self.inspect()
        self.assertTrue(any("requires macOS 26.0" in e for e in errors))
        self.assertTrue(any("/opt/homebrew/" in e for e in errors))

    def test_macos_15_5_library_cannot_ship_to_all_macos_15(self):
        self.add_binary("Contents/Frameworks/newer.dylib", commands("15.5"))
        self.assertTrue(any("requires macOS 15.5, target is 15.0" in e for e in self.inspect()))

    def test_wrong_architecture_and_missing_version(self):
        self.add_binary("Contents/Frameworks/wrong", arch="x86_64")
        self.add_binary("Contents/Frameworks/unknown", "Load command 0\n cmd LC_SEGMENT_64")
        errors = self.inspect()
        self.assertTrue(any("arm64 architecture missing" in e for e in errors))
        self.assertTrue(any("minimum macOS version unavailable" in e for e in errors))

    def test_rpath_must_match_real_path_not_basename(self):
        self.add_binary("Contents/MacOS/example", commands(dependencies=["@rpath/sub/a.dylib"],
                        rpaths=["@executable_path/../Frameworks"]))
        self.add_binary("Contents/Frameworks/a.dylib")
        self.assertTrue(any("@rpath/sub/a.dylib" in e for e in self.inspect()))
        self.add_binary("Contents/Frameworks/sub/a.dylib")
        self.assertEqual(self.inspect(), [])

    def test_loader_path_and_inherited_rpath(self):
        self.add_binary("Contents/MacOS/example", commands(dependencies=["@rpath/a.dylib"],
                        rpaths=["@executable_path/../Frameworks"]))
        self.add_binary("Contents/Frameworks/a.dylib", commands(dependencies=["@rpath/b.dylib"]))
        self.add_binary("Contents/Frameworks/b.dylib", commands(dependencies=["@loader_path/a.dylib"]))
        self.assertEqual(self.inspect(), [])

    def test_external_symlink_and_unknown_relative_dependency(self):
        outside = Path(self.temp.name) / "outside.dylib"
        outside.touch()
        (self.app / "Contents/MacOS/escape.dylib").symlink_to(outside)
        self.add_binary("Contents/MacOS/example", commands(dependencies=["@loader_path/escape.dylib", "other.dylib"]))
        errors = self.inspect()
        self.assertTrue(any("external or broken symlink" in e for e in errors))
        self.assertTrue(any("other.dylib" in e for e in errors))

    def test_minimum_plist_must_match(self):
        self.info["LSMinimumSystemVersion"] = "26.0"
        self.write_info()
        self.assertTrue(any("LSMinimumSystemVersion" in e for e in self.inspect()))

    def test_old_load_command_and_dylib_id_not_dependency(self):
        text = ("Load command 0\n cmd LC_VERSION_MIN_MACOSX\n version 11.0\n sdk 26.0\n"
                "Load command 1\n cmd LC_ID_DYLIB\n name /old/build/lib.dylib (offset 24)\n current version 999.0.0")
        self.assertEqual(load_commands(text), (["11.0"], [], []))

    def test_wrong_platform_and_tool_error_fail_closed(self):
        self.add_binary("Contents/MacOS/example", commands().replace("platform 1", "platform 2"))
        self.assertTrue(any("non-macOS" in e for e in self.inspect()))
        def fail(args, **kwargs):
            raise subprocess.CalledProcessError(1, args)
        self.assertTrue(any("inspection failed" in e for e in inspect_bundle(self.app, run=fail)))


class PythonPreflightTests(unittest.TestCase):
    def test_valid_interpreter(self):
        self.assertEqual(check_python((3, 12, 10), "arm64", lambda name: None), [])

    def test_wrong_version_and_architecture(self):
        errors = check_python((3, 11, 9), "x86_64", lambda name: None)
        self.assertEqual(len(errors), 2)

    def test_missing_tk(self):
        def missing(name):
            raise ModuleNotFoundError("No module named '_tkinter'")
        self.assertIn("Tk unavailable", check_python((3, 12, 10), "arm64", missing)[0])


if __name__ == "__main__":
    unittest.main()
