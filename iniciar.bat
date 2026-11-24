@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Cortes Gratis
if not exist ".venv\Scripts\python.exe" (
  echo Rode primeiro o instalar.bat
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m cortes_gratis %*
if errorlevel 1 pause
