@echo off
chcp 65001 >nul
title Preparación de Embarques NSG

cd /d "%~dp0"

REM El venv se guarda en ruta corta para evitar el limite de 260 chars de Windows
set VENV=C:\NSG_Embarques_venv

if not exist "%VENV%\Scripts\streamlit.exe" (
    echo [!] Entorno no encontrado en %VENV%
    echo     Ejecuta install.bat primero.
    pause
    exit /b 1
)

echo Iniciando Preparación de Embarques NSG...
echo El navegador se abrirá en unos segundos.
echo Para cerrar la aplicación cierra esta ventana.
echo.

start "" http://localhost:8501
"%VENV%\Scripts\streamlit.exe" run app.py ^
    --server.port=8501 ^
    --server.headless=true ^
    --browser.gatherUsageStats=false ^
    --browser.serverAddress=localhost
