# -*- mode: python ; coding: utf-8 -*-
# seeSRT 打包配置（PyInstaller spec）
#
# 用法（在项目根目录执行）：
#   pyinstaller seeSRT.spec --noconfirm --clean
#
# 产物：dist/seeSRT/ 文件夹（内含 seeSRT.exe + 依赖）。
# 把整个 dist/seeSRT 文件夹拷给其他 Windows 用户即可运行。

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

# 前端静态资源（app/static → 打包后 app/static）
datas += [("app/static", "app/static")]

# pywebview 及其 Windows WebView2 依赖（pythonnet / clr_loader）
for pkg in ("webview", "clr_loader", "pythonnet", "clr"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "ollama", "openai"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="seeSRT",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI 应用，不弹出控制台窗口
    disable_windowed_traceback=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="seeSRT",
)
