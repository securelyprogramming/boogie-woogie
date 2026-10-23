#!/usr/bin/env python3
"""Prepare the unchanged, checksum-pinned EmulatorJS build-time runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
VERSION = "4.2.3"
DIGEST = "07d451bc06fa3ad04ab30d9b94eb63ac34ad0babee52d60357b002bde8f3850b"
URL = f"https://github.com/EmulatorJS/EmulatorJS/releases/download/v{VERSION}/{VERSION}.7z"
MAX_ARCHIVE = 512 * 1024 * 1024
MAX_EXTRACTED = 2 * 1024 * 1024 * 1024
CORE_PATH = "data/cores/fceumm-legacy-wasm.data"


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def verify_archive(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ARCHIVE:
        raise ValueError("Runtime archive must be a regular file within the size limit")
    if sha256(path) != DIGEST:
        raise ValueError("Runtime archive SHA-256 mismatch; existing runtime was not changed")
    return path


def validate_members(package):
    seen, size, count = set(), 0, 0
    for entry in package.files:
        name = entry.filename
        parts = PurePosixPath(name).parts
        if (not name or name.startswith("/") or "\\" in name or ":" in name or
                "\0" in name or ".." in parts or "." in name.split("/") or
                any(not part for part in name.rstrip("/").split("/"))):
            raise ValueError("Unsafe archive entry path")
        normalized = "/".join(parts).casefold()
        if normalized in seen:
            raise ValueError("Duplicate archive entry")
        seen.add(normalized)
        if entry.is_symlink or entry.is_junction or entry.is_socket:
            raise ValueError("Archive links and special files are not supported")
        size += entry.uncompressed or 0
        count += 1
        if size > MAX_EXTRACTED or count > 10000:
            raise ValueError("Archive extraction limit exceeded")


def regular_tree(root):
    for path in root.rglob("*"):
        mode = path.lstat().st_mode
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise ValueError("Extracted runtime contains a link or special file")


def validate_layout(runtime):
    for name in ("data/loader.js", "data/version.json", "data/cores/cores.json", CORE_PATH, "LICENSE"):
        path = runtime / name
        if path.is_symlink() or not path.is_file() or not path.stat().st_size:
            raise ValueError(f"Pinned runtime is missing {name}")
    if json.loads((runtime / "data/version.json").read_text())["version"] != VERSION:
        raise ValueError("Runtime version does not match the pinned release")


def stage_runtime(archive, destination, archive_type):
    """Fully validate a private staging tree before making it the build input."""
    verify_archive(archive)
    with archive_type(archive) as package:
        validate_members(package)
        package.extractall(destination)
    regular_tree(destination)
    validate_layout(destination)
    notices = destination / "third-party/fceumm"
    notices.mkdir(parents=True)
    with archive_type(destination / CORE_PATH) as core:
        validate_members(core)
        if not {"license.txt", "core.json", "build.json"}.issubset(core.getnames()):
            raise ValueError("FCEUmm archive is missing license/build provenance")
        core.extract(path=notices, targets=["license.txt", "core.json", "build.json"])
    regular_tree(destination)
    (destination / "UPSTREAM.json").write_text(json.dumps({
        "version": VERSION, "archive": URL, "sha256": DIGEST,
        "source": f"https://github.com/EmulatorJS/EmulatorJS/tree/v{VERSION}",
        "core": {"artifact": CORE_PATH, "sha256": sha256(destination / CORE_PATH),
                 "metadata": "third-party/fceumm/core.json", "build": "third-party/fceumm/build.json",
                 "sourceCommit": None,
                 "sourceStatus": "Exact WASM core source revision requires upstream provenance before binary release"},
    }, indent=2) + "\n")


def install_staged(staged, runtime):
    if runtime.is_symlink() or (runtime.exists() and not runtime.is_dir()):
        raise ValueError("Runtime output must be a directory, never a symlink")
    backup = staged.parent / "previous-runtime"
    existed = runtime.exists()
    if existed:
        runtime.rename(backup)
    try:
        staged.rename(runtime)
    except BaseException:
        if existed:
            backup.rename(runtime)
        raise
    if existed:
        shutil.rmtree(backup)


def download_archive(cache):
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / f"{VERSION}.7z"
    if archive.exists() or archive.is_symlink():
        return verify_archive(archive)
    descriptor, partial = tempfile.mkstemp(prefix="download-", suffix=".7z", dir=cache)
    partial = Path(partial)
    try:
        with os.fdopen(descriptor, "wb") as output:
            with urllib.request.urlopen(URL, timeout=60) as response:
                total = 0
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    total += len(block)
                    if total > MAX_ARCHIVE:
                        raise ValueError("Runtime download exceeds size limit")
                    output.write(block)
        verify_archive(partial)
        os.replace(partial, archive)
        return archive
    finally:
        partial.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Already downloaded official 4.2.3.7z; SHA-256 is always verified")
    args = parser.parse_args()
    try:
        import py7zr
    except ImportError:
        parser.exit(1, "Install build dependencies with: python -m pip install -r scripts/requirements-runtime.txt\n")
    if py7zr.__version__ != "1.0.0":
        parser.exit(1, "Use the pinned py7zr version from scripts/requirements-runtime.txt\n")
    lock = ROOT / ".runtime-prepare.lock"
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        parser.exit(1, "Another runtime preparation owns .runtime-prepare.lock; check it before retrying\n")
    os.close(descriptor)
    try:
        archive = verify_archive(args.archive) if args.archive else download_archive(Path.home() / ".cache/boogie-woogie/runtime")
        with tempfile.TemporaryDirectory(prefix=".runtime-stage-", dir=ROOT) as temporary:
            staged = Path(temporary) / "runtime"
            staged.mkdir()
            stage_runtime(archive, staged, py7zr.SevenZipFile)
            install_staged(staged, ROOT / "runtime")
        print(f"Verified EmulatorJS {VERSION} runtime ready; emulator/core bytes unchanged.")
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        parser.exit(1, f"Runtime preparation failed: {error}\n")
    finally:
        lock.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
