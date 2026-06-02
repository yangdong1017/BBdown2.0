# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import collect_all


block_cipher = None
PROJECT_ROOT = os.path.abspath(os.path.dirname(SPEC))

APP_SCRIPT = os.path.join(PROJECT_ROOT, "app.py")
EXE_NAME = "BBDown"
TOOLS_DIR = os.path.join(PROJECT_ROOT, "tools")

qfw_datas, qfw_binaries, qfw_hiddenimports = collect_all("qfluentwidgets")

datas = []
datas += qfw_datas
if os.path.isdir(TOOLS_DIR):
    for name in os.listdir(TOOLS_DIR):
        src = os.path.join(TOOLS_DIR, name)
        if os.path.isfile(src):
            datas.append((src, "tools"))

binaries = []
binaries += qfw_binaries

hiddenimports = []
hiddenimports += qfw_hiddenimports
hiddenimports += [
    "PyQt5.sip",
    "bk_asr",
    "bk_asr.ASRData",
    "bk_asr.BaseASR",
    "bk_asr.BcutASR",
    "bk_asr.JianYingASR",
    "bk_asr.KuaiShouASR",
]

a = Analysis(
    [APP_SCRIPT],
    pathex=[PROJECT_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "unittest", "openai"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=EXE_NAME,
)
