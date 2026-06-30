@echo off
chcp 65001 >nul
title Build EXE — Preparación de Embarques NSG
echo.
echo ============================================================
echo   BUILD EXE — Preparación de Embarques NSG
echo   Empaqueta la aplicación como .exe standalone con PyInstaller
echo ============================================================
echo.

cd /d "%~dp0"

if not exist "venv\Scripts\pyinstaller.exe" (
    echo [ERROR] PyInstaller no encontrado. Ejecuta install.bat primero.
    pause
    exit /b 1
)

REM Localizar carpeta de Streamlit dentro del venv para incluir sus assets
for /f "delims=" %%i in ('venv\Scripts\python.exe -c "import streamlit; import os; print(os.path.dirname(streamlit.__file__))"') do set STREAMLIT_DIR=%%i

echo Streamlit encontrado en: %STREAMLIT_DIR%
echo.
echo Ejecutando PyInstaller...
echo.

call venv\Scripts\pyinstaller.exe ^
    --noconfirm ^
    --onedir ^
    --windowed ^
    --name "EmbarquesNSG" ^
    --icon "assets\logo.ico" ^
    --add-data "app.py;." ^
    --add-data "config.py;." ^
    --add-data "modules;modules" ^
    --add-data "pages;pages" ^
    --add-data "assets;assets" ^
    --add-data "%STREAMLIT_DIR%;streamlit" ^
    --hidden-import "streamlit" ^
    --hidden-import "streamlit.web.cli" ^
    --hidden-import "streamlit.runtime.scriptrunner" ^
    --hidden-import "pdfplumber" ^
    --hidden-import "reportlab" ^
    --hidden-import "pypdf" ^
    --hidden-import "sqlite3" ^
    --collect-all "streamlit" ^
    --collect-all "pdfplumber" ^
    --collect-all "reportlab" ^
    main.py

if errorlevel 1 (
    echo.
    echo [ERROR] El build falló. Revisa los mensajes anteriores.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Build completado. Ejecutable en: dist\EmbarquesNSG\
echo   Distribuye la carpeta "EmbarquesNSG" completa.
echo   El usuario ejecuta: EmbarquesNSG.exe
echo ============================================================
echo.
pause
