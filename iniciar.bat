@echo off
cd /d "%~dp0"
title Simulador de Presenca de Jogos

if exist "SimuladorPresencaJogos.exe" (
    start "" "SimuladorPresencaJogos.exe"
    exit /b
)

if exist "Release\SimuladorPresencaJogos.exe" (
    start "" "Release\SimuladorPresencaJogos.exe"
    exit /b
)

echo Iniciando via Python...
python app.py
