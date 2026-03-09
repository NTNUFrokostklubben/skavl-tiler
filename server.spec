# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_dynamic_libs

# Collect GDAL libraries from the conda environment
binaries = collect_dynamic_libs("gdal")

# Linux-specific dependency (required by GDAL stack)
if sys.platform.startswith("linux"):
    conda_lib = Path(os.environ["CONDA_PREFIX"]) / "lib"
    binaries += [
        (str(conda_lib / "libnsl.so.3"), "."),
    ]


a = Analysis(
    [str(Path("src") / "server.py")],
    pathex=[],
    binaries=binaries,
    datas=[],
    hiddenimports=[],
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
    name="server",
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