# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Linux.
#
# System ffmpeg is expected (sudo pacman -S ffmpeg / sudo apt install ffmpeg).
# Build:
#   pyinstaller build_linux.spec
from PyInstaller.utils.hooks import collect_all

ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all("customtkinter")
pg_datas, pg_binaries, pg_hiddenimports = collect_all("pygame")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=ctk_binaries + pg_binaries,
    datas=ctk_datas + pg_datas,
    hiddenimports=ctk_hiddenimports + pg_hiddenimports,
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
)
