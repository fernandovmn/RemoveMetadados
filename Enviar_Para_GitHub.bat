@echo off
title Enviando ZeroMeta para o GitHub...
cd /d "c:\AJK Global\Projetos\RemoveMetadados"
set "PATH=%PATH%;C:\Program Files\Git\cmd"

echo ========================================================
echo   Enviando ZeroMeta para o GitHub (Compilacao do APK)
echo ========================================================
echo.
echo Se aparecer uma janela do navegador ou do Git, clique em:
echo    "Sign in with your browser" (ou autorize a conta).
echo.

git push -u origin main

echo.
if %ERRORLEVEL% EQU 0 (
    echo ========================================================
    echo   SUCESSO! O GitHub comecou a compilar seu APK!
    echo.
    echo   Acesse a aba Actions para acompanhar:
    echo   https://github.com/fernandovmn/RemoveMetadados/actions
    echo ========================================================
) else (
    echo [!] Se pediu token ou senha, certifique-se de autorizar no navegador.
)
echo.
pause
