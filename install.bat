@echo off
chcp 65001 >nul
title Instalación — Preparación de Embarques NSG
echo.
echo ============================================================
echo   INSTALACIÓN — Preparación de Embarques NSG
echo ============================================================
echo.

REM Verificar que Python esté instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no está instalado o no está en el PATH.
    echo.
    echo Descarga Python 3.11 o superior desde: https://www.python.org/downloads/
    echo Asegúrate de marcar "Add Python to PATH" durante la instalación.
    echo.
    pause
    exit /b 1
)

echo [OK] Python encontrado.
echo.

REM Ir a la carpeta del script
cd /d "%~dp0"

REM Crear entorno virtual si no existe
if not exist "venv\" (
    echo Creando entorno virtual...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
    echo [OK] Entorno virtual creado.
) else (
    echo [OK] Entorno virtual existente encontrado.
)

echo.
echo Instalando dependencias...
call venv\Scripts\python.exe -m pip install --upgrade pip --quiet
call venv\Scripts\pip.exe install -r requirements.txt --quiet

if errorlevel 1 (
    echo [ERROR] Falló la instalación de dependencias.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Instalación completada correctamente.
echo   Usa "launcher.bat" para iniciar la aplicación.
echo ============================================================
echo.
pause
