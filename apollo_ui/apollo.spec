# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['launch_apollo.pyw'],
    pathex=[],
    binaries=[],
    datas=[('modules', 'modules'), ('pending_modules', 'pending_modules'), ('config.json', '.'), ('modules_state.json', '.'), ('openjarvis_worker.py', '.'), ('vendor/openjarvis.lock.json', 'vendor'), ('tools/setup_openjarvis.py', 'tools'), ('third_party', 'third_party'), ('Setup/19_SETUP_OPENJARVIS.bat', 'Setup')],
    hiddenimports=['apollo_openjarvis', 'apollo_openjarvis_ui', 'apollo_openjarvis_chat'],
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
    name='Apollo',
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
    version='version_info.txt',
    icon=['apollo_logo.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Apollo',
)
