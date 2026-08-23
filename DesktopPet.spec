# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src/pet.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/cat.png', 'assets'),
        ('assets/_tianmao_frames', 'assets/_tianmao_frames'),
        ('assets/_walkleft_frames', 'assets/_walkleft_frames'),
        ('assets/_action1_frames', 'assets/_action1_frames'),
        ('assets/_action2_frames', 'assets/_action2_frames'),
        ('assets/_walk_offsets.json', 'assets'),
    ],
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
    a.binaries,
    a.datas,
    [],
    name='danta1.1',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.ico'],
)
