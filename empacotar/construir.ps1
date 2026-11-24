# Gera o instalador do Cortes Grátis: dist\CortesGratis-<versao>-instalador.exe
#
# Precisa de: Python 3.12 64 bits e Inno Setup 6 (winget install JRSoftware.InnoSetup).
# Uso, na pasta do projeto:   powershell -ExecutionPolicy Bypass -File empacotar\construir.ps1
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

# 1) Ambiente de build separado (sem as libs da NVIDIA, que o .exe baixa sozinho)
$venv = Join-Path $raiz "build\venv"
if (-not (Test-Path "$venv\Scripts\python.exe")) {
    Write-Host "Criando ambiente de build..."
    # No GitHub Actions o Python vem do setup-python (variável PYTHON).
    if ($env:PYTHON) { & $env:PYTHON -m venv $venv } else { & py -3.12 -m venv $venv }
}
$py = "$venv\Scripts\python.exe"
$env:PIP_NO_CACHE_DIR = "1"
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -r requirements.txt pyinstaller --quiet
if ($LASTEXITCODE) { throw "pip falhou" }

$versao = & $py -c "import cortes_gratis; print(cortes_gratis.__version__)"
Write-Host "Versão $versao"

# 2) PyInstaller: pasta com o Cortes Gratis.exe + Python embutido
& $py -m PyInstaller empacotar\cortes-gratis.spec --noconfirm --clean `
    --distpath build\pyinstaller\dist --workpath build\pyinstaller\work
if ($LASTEXITCODE) { throw "PyInstaller falhou" }

# 3) Inno Setup: transforma a pasta num instalador
$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 não encontrado. Instale: winget install JRSoftware.InnoSetup" }
& $iscc "/DVersao=$versao" empacotar\instalador.iss
if ($LASTEXITCODE) { throw "Inno Setup falhou" }

Get-ChildItem dist\*.exe | ForEach-Object { "{0}  ({1:N0} MB)" -f $_.FullName, ($_.Length / 1MB) }
