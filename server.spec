# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks.conda import collect_dynamic_libs as collect_conda_dynamic_libs

binaries = []
hiddenimports = []

# Collect Conda-shared DLLs from env/Library/bin for Windows (shared lib for Unix)
binaries += collect_conda_dynamic_libs("gdal", dependencies=True)
binaries += collect_conda_dynamic_libs("grpcio", dependencies=True)
binaries += collect_conda_dynamic_libs("pillow", dependencies=True)

# Optional: grpc sometimes benefits from explicit submodule collection.
hiddenimports += collect_submodules("grpc")

# Linux-specific dependency (required by GDAL stack)
if sys.platform.startswith("linux"):
    conda_lib = Path(sys.prefix) / "lib"
    binaries += [(str(conda_lib / "libnsl.so.3"), ".")]

a = Analysis(
    [str(Path("src") / "server.py")],
    pathex=[],
    binaries=binaries,
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="skavl-tiler",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory=".",
    icon=str(Path("res") / "tiler-icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="server",
)