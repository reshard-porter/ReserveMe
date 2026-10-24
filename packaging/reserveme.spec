# PyInstaller build recipe for Windows and macOS.
#   pyinstaller packaging/reserveme.spec --noconfirm
# Output: dist/ReserveMe/ (Windows) or dist/ReserveMe.app (macOS)
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))
from reserveme import __version__  # noqa: E402

hidden = (
    collect_submodules("sqlalchemy.dialects")
    + ["psycopg", "psycopg_binary", "pymysql", "argon2", "_cffi_backend"]
    + collect_submodules("keyring.backends")
    + ["platformdirs", "openpyxl"]
)

a = Analysis(
    [str(ROOT / "reserveme" / "__main__.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "reserveme" / "resources"), "reserveme/resources"),
           (str(ROOT / "sql"), "sql")],
    hiddenimports=hidden,
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts",
              "PySide6.QtDataVisualization", "pytest", "numpy", "PIL", "lxml", "pandas", "matplotlib", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

icon = str(ROOT / "packaging" / ("icon.icns" if sys.platform == "darwin" else "icon.ico"))
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ReserveMe",
    console=False,
    icon=icon,
    version=str(ROOT / "packaging" / "version_info.txt") if sys.platform == "win32" else None,
    codesign_identity=None,  # macOS signing is done afterwards by build_macos.sh
)
coll = COLLECT(exe, a.binaries, a.datas, name="ReserveMe")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="ReserveMe.app",
        icon=icon,
        bundle_identifier="com.reserveme.pms",
        version=__version__,
        info_plist={
            "CFBundleName": "ReserveMe",
            "CFBundleDisplayName": "ReserveMe",
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "NSHumanReadableCopyright": "ReserveMe",
        },
    )
