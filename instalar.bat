@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Cortes Gratis - instalador

echo.
echo  ==========================================
echo   Cortes Gratis - instalador
echo  ==========================================
echo.
echo  Tudo sera instalado DENTRO desta pasta:
echo    %CD%
echo  (nada vai para o disco C:, a nao ser o proprio Python se faltar)
echo.

rem ---------------------------------------------------------------- Python
rem Precisa ser 64 bits e entre 3.10 e 3.13: a biblioteca de transcricao
rem (ctranslate2) nao existe para Python 32 bits nem para versoes mais novas.
set "PY="
set "TESTE=import sys,struct; sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,13) and struct.calcsize('P')==8 else 1)"
where py >nul 2>nul
if %errorlevel%==0 (
  for %%V in (3.12 3.13 3.11 3.10) do (
    if not defined PY (
      py -%%V -c "%TESTE%" >nul 2>nul && set "PY=py -%%V"
    )
  )
)
if not defined PY (
  python -c "%TESTE%" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo  [!] Nao achei Python 64 bits entre 3.10 e 3.13.
  echo.
  echo  Instale com o comando abaixo e rode este instalador de novo:
  echo      winget install Python.Python.3.12
  echo  ou baixe em https://www.python.org/downloads/ ^(marque "Add python.exe to PATH"^)
  echo.
  pause
  exit /b 1
)
echo  [1/4] Python encontrado: & %PY% --version

rem ---------------------------------------------------------------- ambiente
if not exist ".venv\Scripts\python.exe" (
  echo  [2/4] Criando ambiente isolado em .venv ...
  %PY% -m venv .venv || goto :erro
) else (
  echo  [2/4] Ambiente .venv ja existe.
)
set "VPY=.venv\Scripts\python.exe"

rem Sem cache do pip: o cache ficaria no C: e ocuparia espaco a toa.
set "PIP_NO_CACHE_DIR=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"

echo  [3/4] Instalando bibliotecas (pode levar alguns minutos)...
"%VPY%" -m pip install --upgrade pip >nul
"%VPY%" -m pip install -r requirements.txt || goto :erro

where nvidia-smi >nul 2>nul
if %errorlevel%==0 (
  echo        Placa NVIDIA encontrada: instalando suporte a GPU ^(~1 GB^)...
  "%VPY%" -m pip install -r requirements-gpu.txt || echo        [!] Falhou; a transcricao vai pelo processador.
) else (
  echo        Sem placa NVIDIA: a transcricao vai pelo processador.
)

echo  [4/4] Baixando o ffmpeg...
"%VPY%" -m cortes_gratis --instalar || goto :erro

echo.
echo  ==========================================
echo   Pronto! Agora e so abrir o iniciar.bat
echo  ==========================================
echo.
echo  A IA local ^(opcional^) se instala pela tela de Configuracoes.
echo.
pause
exit /b 0

:erro
echo.
echo  [X] Algo deu errado. Leia a mensagem acima.
echo      Se nao entender, abra uma issue no GitHub com o print desta janela.
pause
exit /b 1
