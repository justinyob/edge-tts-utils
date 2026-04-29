# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Windows.
#
# Before building:
#   1. Place a static ffmpeg.exe and ffprobe.exe in the project root.
#   2. Activate the venv and: pip install -r requirements.txt
# Build:
#   pyinstaller build_windows.spec
import os
import sys

from PyInstaller.utils.hooks import collect_all

ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all("customtkinter")
pg_datas, pg_binaries, pg_hiddenimports = collect_all("pygame")

# Belt-and-suspenders Tcl/Tk collection: explicitly grab the Tcl/Tk DLLs and
# data directories from the building Python install. PyInstaller's _tkinter
# hook normally handles this, but a recent pyinstaller-hooks-contrib release
# regressed it on Windows (manifested as: "DLL load failed while importing
# _tkinter" at startup). Doing it ourselves removes the dependency on the
# auto-hook for our most critical runtime binary.
_tk_binaries = []
_tk_datas = []
if sys.platform == "win32":
    _py_base = sys.base_prefix
    _dlls_dir = os.path.join(_py_base, "DLLs")
    for _name in ("tcl86t.dll", "tk86t.dll", "_tkinter.pyd"):
        _path = os.path.join(_dlls_dir, _name)
        if os.path.exists(_path):
            _tk_binaries.append((_path, "."))

    _tcl_root = os.path.join(_py_base, "tcl")
    if os.path.isdir(_tcl_root):
        for _entry in os.listdir(_tcl_root):
            _full = os.path.join(_tcl_root, _entry)
            if os.path.isdir(_full):
                _tk_datas.append((_full, os.path.join("tcl", _entry)))

_icon_path = "assets/icon.ico"
_icon_arg = _icon_path if os.path.exists(_icon_path) else None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=(
        [("ffmpeg.exe", "."), ("ffprobe.exe", ".")]
        + ctk_binaries
        + pg_binaries
        + _tk_binaries
    ),
    datas=[("_updater.py", ".")] + ctk_datas + pg_datas + _tk_datas,
    hiddenimports=ctk_hiddenimports + pg_hiddenimports + ["tkinter", "_tkinter"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VoiceStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon_arg,
)
