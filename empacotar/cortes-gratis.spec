# Receita do PyInstaller: junta o Python e as bibliotecas numa pasta com o
# "Cortes Gratis.exe". Rodar com:  pyinstaller empacotar/cortes-gratis.spec
#
# As bibliotecas da NVIDIA (2 GB) NÃO entram aqui: o programa baixa sozinho
# se achar uma placa NVIDIA (ver cortes_gratis/cuda.py).
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

RAIZ = SPECPATH + "/.."

datas = [(RAIZ + "/cortes_gratis/web", "cortes_gratis/web")]
datas += collect_data_files("faster_whisper")      # modelo de detecção de voz (VAD)
binaries = collect_dynamic_libs("ctranslate2")     # motor do Whisper (+ cudnn64_9.dll)
hiddenimports = (
    collect_submodules("yt_dlp.extractor")         # um módulo por site
    + collect_submodules("uvicorn")
    + ["cortes_gratis.servidor"]
)

a = Analysis(
    [RAIZ + "/empacotar/entrada.py"],
    pathex=[RAIZ],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    # Coisas que vêm de carona e não são usadas: deixam o instalador menor.
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "torch", "nvidia"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Cortes Gratis",
    icon=RAIZ + "/empacotar/icone.ico",
    console=True,   # a janela preta mostra o endereço e, fechando, desliga o programa
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Cortes Gratis")
