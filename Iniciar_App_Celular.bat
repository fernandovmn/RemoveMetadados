@echo off
title ZeroMeta AI - Servidor Mobile (Android)
cd /d "%~dp0"
python mobile_server.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Ocorreu um erro ao iniciar o servidor mobile.
    pause
)
