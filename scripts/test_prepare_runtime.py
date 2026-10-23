"""Runtime preparation policy tests need no download or extraction dependency."""
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("prepare_runtime", Path(__file__).with_name("prepare-runtime.py"))
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def member(name, **changes):
    return SimpleNamespace(filename=name, is_symlink=False, is_junction=False,
                           is_socket=False, uncompressed=0, **changes)


class RuntimeTests(unittest.TestCase):
    def test_checksum_rejection_does_not_touch_existing_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "wrong.7z"
            archive.write_bytes(b"untrusted archive")
            existing = root / "runtime"
            existing.mkdir()
            (existing / "keep").write_bytes(b"previous valid runtime")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                runtime.stage_runtime(archive, existing, None)
            self.assertEqual((existing / "keep").read_bytes(), b"previous valid runtime")

    def test_archive_rejects_traversal_windows_paths_links_duplicates_and_bombs(self):
        for name in ("/absolute", "../escape", "data/../../escape", "C:/file", "data\\file", "data/./file", "data//file", "\0bad"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                runtime.validate_members(SimpleNamespace(files=[member(name)]))
        for attribute in ("is_symlink", "is_junction", "is_socket"):
            entry = member("data/file")
            setattr(entry, attribute, True)
            with self.assertRaises(ValueError):
                runtime.validate_members(SimpleNamespace(files=[entry]))
        with self.assertRaises(ValueError):
            runtime.validate_members(SimpleNamespace(files=[member("Data/file"), member("data/FILE")]))
        entry = member("data/file")
        entry.uncompressed = runtime.MAX_EXTRACTED + 1
        with self.assertRaises(ValueError):
            runtime.validate_members(SimpleNamespace(files=[entry]))

    def test_validated_install_rolls_back_if_final_rename_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            current, staged = root / "runtime", root / "stage/runtime"
            current.mkdir()
            staged.mkdir(parents=True)
            (current / "marker").write_text("old")
            (staged / "marker").write_text("new")
            rename = Path.rename

            def fail_new(source, target):
                if source == staged:
                    raise OSError("simulated installation failure")
                return rename(source, target)

            with patch.object(Path, "rename", fail_new), self.assertRaises(OSError):
                runtime.install_staged(staged, current)
            self.assertEqual((current / "marker").read_text(), "old")
            runtime.install_staged(staged, current)
            self.assertEqual((current / "marker").read_text(), "new")
            self.assertFalse((staged.parent / "previous-runtime").exists())

    def test_extracted_links_and_incomplete_layout_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "link").symlink_to(root / "missing")
            with self.assertRaises(ValueError):
                runtime.regular_tree(root)
            with self.assertRaises(ValueError):
                runtime.validate_layout(root)


if __name__ == "__main__":
    unittest.main()
