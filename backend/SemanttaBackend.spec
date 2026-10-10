from pathlib import Path

from PyInstaller.building.build_main import Analysis
from PyInstaller.building.api import PYZ, EXE
from PyInstaller.utils.hooks import collect_submodules, copy_metadata


ROOT = Path(SPECPATH).resolve()

datas = [
    (str(ROOT / "vocab" / "owl.ttl"), "vocab"),
]

datas += copy_metadata("owlrl")

hiddenimports = []

hiddenimports += collect_submodules("rdflib.plugins.parsers")
hiddenimports += collect_submodules("rdflib.plugins.serializers")
hiddenimports += collect_submodules("pyshacl")
hiddenimports += collect_submodules("owlrl")
hiddenimports += collect_submodules("httpx")
hiddenimports += collect_submodules("httpcore")


a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="SemanttaBackend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)