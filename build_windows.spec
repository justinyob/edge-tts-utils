# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Windows.
#
# Before building:
#   1. Place a static ffmpeg.exe in the project root.
#   2. Activate the venv and: pip install -r requirements.txt
# Build:
#   pyinstaller build_windows.spec
import os

from PyInstaller.utils.hooks import collect_all

ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all("customtkinter")

_icon_path = "assets/icon.ico"
_icon_arg = _icon_path if os.path.exists(_icon_path) else None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[("ffmpeg.exe", ".")] + ctk_binaries,
    datas=[("_updater.py", ".")] + ctk_datas,
    hiddenimports=ctk_hiddenimports,
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
