#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Gökdeniz G.
"""BlockFall Windows sürümünü tek bir .exe olarak derler.

Kullanım (windows klasöründe):
    python -m venv .venv
    .venv\\Scripts\\python -m pip install -r requirements.txt
    .venv\\Scripts\\python build_exe.py      ->  dist\\BlockFall.exe
"""

import hashlib
import io
import os
import re
import shutil
import struct
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

import cairo  # noqa: E402
import PyInstaller.__main__  # noqa: E402

import blockfall  # noqa: E402

BUILD = os.path.join(ROOT, "build")
DIST = os.path.join(ROOT, "dist")
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def version():
    with open(os.path.join(ROOT, "src", "blockfall.py"), encoding="utf-8") as f:
        return re.search(r'^VERSION = "([^"]+)"', f.read(), re.M).group(1)


def make_icon(path):
    """Oyunun kendi simge çiziminden çok boyutlu .ico (PNG gömülü) üretir."""
    images = []
    for size in ICON_SIZES:
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
        blockfall.draw_app_icon(cairo.Context(surf), size)
        buf = io.BytesIO()
        surf.write_to_png(buf)
        images.append((size, buf.getvalue()))
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, png in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        blobs += png
        offset += len(png)
    with open(path, "wb") as f:
        f.write(header + entries + blobs)


def make_version_file(path, ver):
    """Dosya özellikleri penceresinde görünen sürüm bilgisi."""
    nums = [int(n) for n in re.findall(r"\d+", ver)][:4]
    nums += [0] * (4 - len(nums))
    tup = tuple(nums)
    text = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers={tup}, prodvers={tup}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041F04B0', [
      StringStruct('CompanyName', 'Gökdeniz G.'),
      StringStruct('FileDescription', 'Blok yerleştirme oyunu'),
      StringStruct('FileVersion', '{ver}'),
      StringStruct('InternalName', 'BlockFall'),
      StringStruct('LegalCopyright', 'Copyright (c) 2026 Gökdeniz G. - MIT'),
      StringStruct('OriginalFilename', 'BlockFall.exe'),
      StringStruct('ProductName', 'BlockFall'),
      StringStruct('ProductVersion', '{ver}')])]),
    VarFileInfo([VarStruct('Translation', [0x041F, 1200])])
  ]
)
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    ver = version()
    os.makedirs(BUILD, exist_ok=True)
    icon = os.path.join(BUILD, "blockfall.ico")
    vfile = os.path.join(BUILD, "version.txt")
    make_icon(icon)
    make_version_file(vfile, ver)
    fonts = os.path.join(ROOT, "assets", "fonts")

    PyInstaller.__main__.run([
        os.path.join(ROOT, "src", "blockfall.py"),
        "--name", "BlockFall",
        "--onefile",
        "--windowed",  # konsol penceresi açılmasın
        "--noconfirm",
        "--clean",
        "--icon", icon,
        "--version-file", vfile,
        "--add-data", f"{fonts}{os.pathsep}assets/fonts",
        "--distpath", DIST,
        "--workpath", os.path.join(BUILD, "work"),
        "--specpath", BUILD,
        # Kullanılmayan büyük modüller pakete girmesin
        "--exclude-module", "tkinter",
        "--exclude-module", "numpy",
        "--exclude-module", "unittest",
        "--exclude-module", "pydoc",
    ])

    exe = os.path.join(DIST, "BlockFall.exe")
    with open(exe, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    with open(os.path.join(DIST, "SHA256SUMS"), "w", encoding="utf-8", newline="\n") as f:
        f.write(f"{digest}  BlockFall.exe\n")
    shutil.rmtree(os.path.join(BUILD, "work"), ignore_errors=True)
    print(f"{exe}  ({os.path.getsize(exe) / 1024 / 1024:.1f} MB)\nSHA-256: {digest}")


if __name__ == "__main__":
    main()
