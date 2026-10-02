@echo off
title ZeroMeta AI - Removedor de Metadados & C2PA
cd /d "%~dp0"
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Ocorreu um erro ao executar o aplicativo.
    pause
)
